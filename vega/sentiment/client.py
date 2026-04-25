"""Grok/xAI API client — supports both /v1/chat/completions and /v1/responses (Agent Tools).

Two endpoints:
  /v1/chat/completions  — standard queries, no live search (used for non-search calls)
  /v1/responses         — live search via Agent Tools (x_search + web_search tools)

search_parameters was deprecated Jan 12 2026. All live search now uses the tools array
on the /v1/responses endpoint.

Tool types:
  x_search   — live X/Twitter search; use allowed_x_handles to filter to specific accounts
  web_search — live web + news search

Three model tiers (configurable via GROK_MODEL, GROK_MODEL_FAST, GROK_MODEL_DEEP):
  fast  — grok-3-mini-fast   high-frequency polls (Singhvi every 5 min)
  std   — grok-3             watchlist sentiment every 3 min
  deep  — grok-4             on-demand /grok queries, morning overview, portfolio watch
"""

from __future__ import annotations

import json
from datetime import date
from typing import Literal

import httpx

from ..config import GrokConfig
from ..exceptions import SentimentError
from ..utils.logging import get_logger
from ..utils.retry import async_retry

log = get_logger("grok_client")

SourceType = Literal["x", "news", "web"]

# Base URL without version path so we can address v1/* explicitly
_API_BASE = "https://api.x.ai/"


class GrokClient:
    """Async client for xAI Grok API.

    Uses /v1/chat/completions for plain queries and /v1/responses (Agent Tools)
    for all live X/news/web search queries.
    """

    def __init__(self, config: GrokConfig) -> None:
        self._config = config
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        self._http = httpx.AsyncClient(
            base_url=_API_BASE,
            headers=headers,
            timeout=90.0,
        )

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    @async_retry(max_attempts=2, backoff_base=2.0, exceptions=(httpx.HTTPError,))
    async def analyze_ticker(
        self,
        ticker: str,
        system_prompt: str,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict:
        """Analyze X + news sentiment for a ticker. Returns parsed JSON dict.

        Uses x_search + web_search tools for real-time data.
        """
        today = date.today().isoformat()
        fd = from_date or today
        td = to_date or today
        user_msg = (
            f"Analyze current X/Twitter sentiment and news for ${ticker} on NSE India "
            f"today {today}. Search for recent posts, news articles, analyst calls, and "
            f"any market discussion about ${ticker}. Return JSON as instructed."
        )
        tools = [
            {"type": "x_search", "from_date": fd, "to_date": td},
            {"type": "web_search"},
        ]
        raw_text = await self._post_responses(
            model=self._config.model,
            instructions=system_prompt,
            user=user_msg,
            tools=tools,
        )
        return self._parse_json(raw_text)

    @async_retry(max_attempts=2, backoff_base=2.0, exceptions=(httpx.HTTPError,))
    async def search_x_handle(
        self,
        system_prompt: str,
        user_message: str,
        handles: list[str],
        model: str | None = None,
    ) -> str:
        """Search X posts from specific handles only. Returns raw text.

        Uses allowed_x_handles to scope the x_search tool to those accounts.
        Used by SinghviMonitor to read only @AnilSinghvi_ posts.
        """
        today = date.today().isoformat()
        tools = [
            {
                "type": "x_search",
                "allowed_x_handles": handles,
                "from_date": today,
                "to_date": today,
            }
        ]
        return await self._post_responses(
            model=model or self._config.model_fast,
            instructions=system_prompt,
            user=user_message,
            tools=tools,
        )

    @async_retry(max_attempts=2, backoff_base=2.0, exceptions=(httpx.HTTPError,))
    async def market_overview(self, system_prompt: str, user_message: str) -> dict:
        """Morning market overview + portfolio watch queries.

        Uses deep model + x_search + web_search for comprehensive coverage.
        Returns parsed JSON dict.
        """
        today = date.today().isoformat()
        tools = [
            {"type": "x_search", "from_date": today, "to_date": today},
            {"type": "web_search"},
        ]
        raw_text = await self._post_responses(
            model=self._config.model_deep,
            instructions=system_prompt,
            user=user_message,
            tools=tools,
        )
        return self._parse_json(raw_text)

    @async_retry(max_attempts=2, backoff_base=2.0, exceptions=(httpx.HTTPError,))
    async def ask(self, question: str, context: str = "") -> str:
        """Direct question with live X + web search. Used by /grok command.

        Uses deep model for best quality. Returns plain text.
        """
        system = (
            "You are a financial intelligence assistant for Indian stock markets (NSE/BSE). "
            "Use live X/Twitter and web search to give accurate, current answers. "
            "Focus on NSE-listed equities and derivatives. "
            "Be concise — your answer will be displayed in Telegram."
            + (f"\n\nUser context: {context}" if context else "")
        )
        today = date.today().isoformat()
        tools = [
            {"type": "x_search", "from_date": today, "to_date": today},
            {"type": "web_search"},
        ]
        return await self._post_responses(
            model=self._config.model_deep,
            instructions=system,
            user=question,
            tools=tools,
        )

    @async_retry(max_attempts=2, backoff_base=2.0, exceptions=(httpx.HTTPError,))
    async def query(
        self,
        system_prompt: str,
        user_message: str,
        live_search: bool = True,
        model: str | None = None,
    ) -> str:
        """Generic Grok query. Returns raw text.

        live_search=True (default) uses x_search + web_search tools.
        live_search=False uses plain /chat/completions (faster, no live data).
        """
        if live_search:
            today = date.today().isoformat()
            tools = [
                {"type": "x_search", "from_date": today, "to_date": today},
                {"type": "web_search"},
            ]
            return await self._post_responses(
                model=model or self._config.model,
                instructions=system_prompt,
                user=user_message,
                tools=tools,
            )
        else:
            return await self._post_completions(
                model=model or self._config.model,
                system=system_prompt,
                user=user_message,
            )

    @async_retry(max_attempts=2, backoff_base=2.0, exceptions=(httpx.HTTPError,))
    async def web_search(self, system_prompt: str, user_message: str) -> str:
        """Web-only search (no X). For external feeds: Tender247, GeM, NCLT, etc.

        Uses deep model for best web comprehension. Returns raw text.
        """
        tools = [{"type": "web_search"}]
        return await self._post_responses(
            model=self._config.model_deep,
            instructions=system_prompt,
            user=user_message,
            tools=tools,
        )

    async def close(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------ #
    #  Internal: /v1/responses (Agent Tools API)                          #
    # ------------------------------------------------------------------ #

    async def _post_responses(
        self,
        model: str,
        instructions: str,
        user: str,
        tools: list[dict],
        temperature: float = 0.2,
    ) -> str:
        """POST to /v1/responses with Agent Tools. Returns extracted text."""
        payload = {
            "model": model,
            "instructions": instructions,
            "input": [{"role": "user", "content": user}],
            "tools": tools,
            "temperature": temperature,
        }
        try:
            resp = await self._http.post("v1/responses", json=payload)
            resp.raise_for_status()
            return self._extract_responses_text(resp.json())
        except httpx.HTTPStatusError as exc:
            raise SentimentError(
                f"Grok responses API {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SentimentError(f"Grok network error: {exc}") from exc

    def _extract_responses_text(self, data: dict) -> str:
        """Extract the final assistant text from a /v1/responses response."""
        # Output is a list; find the last message item with output_text content
        for item in reversed(data.get("output", [])):
            if item.get("type") == "message":
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        return part.get("text", "")
        # Fallback: some responses put content directly
        text = data.get("output_text", data.get("text", ""))
        if text:
            return text
        log.warning("grok_responses_parse_failed", keys=list(data.keys()))
        return ""

    # ------------------------------------------------------------------ #
    #  Internal: /v1/chat/completions (plain, no live search)             #
    # ------------------------------------------------------------------ #

    async def _post_completions(
        self,
        model: str,
        system: str,
        user: str,
        temperature: float = 0.2,
    ) -> str:
        """POST to /v1/chat/completions. No live search. Returns text."""
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        try:
            resp = await self._http.post("v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise SentimentError("Empty response from Grok")
            return choices[0].get("message", {}).get("content", "")
        except httpx.HTTPStatusError as exc:
            raise SentimentError(
                f"Grok completions {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SentimentError(f"Grok network error: {exc}") from exc

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _parse_json(self, text: str) -> dict:
        """Parse JSON from Grok text response, stripping markdown fences."""
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        for start_ch, end_ch in [("{", "}"), ("[", "]")]:
            s = text.find(start_ch)
            e = text.rfind(end_ch) + 1
            if s >= 0 and e > s:
                try:
                    return json.loads(text[s:e])
                except json.JSONDecodeError:
                    pass

        log.warning("grok_json_parse_failed", preview=text[:300])
        return {
            "score": 0.0,
            "confidence": 0.1,
            "themes": [],
            "summary": text[:200] if text else "Parse failed",
            "post_count": 0,
            "notable_accounts": [],
        }
