"""Optional LLM narration over the rule-based deep-analysis brief.

Turns the structured pillars (stance, bull/bear factors, news, macro) into a tight
analyst paragraph. Entirely optional: if ANTHROPIC_API_KEY isn't set, or the call
fails, narrate() returns None and the app falls back to the structured view — the
deep analysis works fully without it.

Calls the Anthropic Messages API directly over httpx (no SDK dependency). Synchronous
on purpose — callers must run it via asyncio.to_thread so it never blocks the loop.
The key is read from the environment only and is never logged.
"""

from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("shares_cfo.llm")

API_URL = "https://api.anthropic.com/v1/messages"


def enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def _prompt(brief: dict) -> str:
    sym = brief.get("symbol", "?")
    stance = brief.get("stance", "neutral")
    pos = brief.get("position_bias", "neutral")
    align = brief.get("alignment", "neutral")
    bull = brief.get("bull") or []
    bear = brief.get("bear") or []
    news = [n.get("title", "") for n in (brief.get("news") or [])[:4]]
    sector = brief.get("sector", "")
    macro = (brief.get("macro") or {}).get("regime", "")
    lines = [
        f"Underlying: {sym}  (sector: {sector})",
        f"Rule-based stance: {stance}; you are positioned {pos}; alignment: {align}.",
        f"Market regime: {macro}.",
        "Bullish factors:",
    ]
    lines += [f"  + {b}" for b in bull] or ["  (none)"]
    lines.append("Bearish factors:")
    lines += [f"  - {b}" for b in bear] or ["  (none)"]
    lines.append("Recent headlines:")
    lines += [f"  • {h}" for h in news] or ["  (none)"]
    facts = "\n".join(lines)
    return (
        "You are a disciplined Indian-markets analyst. Using ONLY the facts below, write a "
        "tight 3-4 sentence take on this F&O underlying for a trader who already holds a "
        "position. Cover: what the fundamentals+technicals+news together imply, the sector/"
        "macro backdrop, and — plainly — whether the evidence supports or argues against the "
        "trader's current position, with a concrete next action (hold/trim/hedge/cut). Do not "
        "invent numbers or facts beyond those given. No preamble, no bullet points.\n\n"
        f"{facts}"
    )


def narrate(brief: dict, timeout: float = 20.0) -> str | None:
    """A short analyst narrative for one deep-analysis brief, or None if unavailable."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None
    model = os.environ.get("CFO_LLM_MODEL", "claude-sonnet-5").strip() or "claude-sonnet-5"
    try:
        r = httpx.post(
            API_URL,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model, "max_tokens": 500,
                  "messages": [{"role": "user", "content": _prompt(brief)}]},
            timeout=timeout,
        )
        if r.status_code >= 400:
            log.info("llm narrate HTTP %s", r.status_code)  # never log the body/key
            return None
        blocks = (r.json() or {}).get("content") or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        return text or None
    except Exception as exc:
        log.info("llm narrate failed: %s", exc)
        return None
