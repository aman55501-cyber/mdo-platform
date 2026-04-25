"""Zee Business YouTube live stream monitor.

Downloads 2-minute audio chunks from the Zee Business live stream every 10 minutes,
transcribes them with faster-whisper, then asks Grok to extract stock calls made
by Anil Singhvi. Only calls where Singhvi is explicitly named are used for trading.

Dependencies (add to pyproject.toml):
  yt-dlp>=2024.1
  faster-whisper>=1.0

NOTE: faster-whisper uses ~500 MB RAM. Railway Starter plan ($5/month) is recommended.
      The monitor degrades gracefully if dependencies are missing.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass

from ..utils.logging import get_logger
from ..utils.time import should_poll_sentiment, now_ist
from .client import GrokClient

log = get_logger("youtube_monitor")

ZEE_BUSINESS_CHANNEL = "UCHGDmHfHBR1hJIKwH6_O9vA"  # Zee Business official
ZEE_BUSINESS_URL = f"https://www.youtube.com/channel/{ZEE_BUSINESS_CHANNEL}/live"
POLL_INTERVAL_SECONDS = 600     # 10 minutes
AUDIO_DURATION_SECONDS = 120    # 2-minute chunks
WHISPER_MODEL = "small"         # small = ~460MB; tiny = ~75MB (less accurate)

EXTRACT_PROMPT = """You are a financial intelligence extractor for Indian equity markets.
The following text is a transcript from Zee Business TV.
Extract ONLY stock-specific calls made by Anil Singhvi (he introduces himself or is introduced by name).
Ignore calls from other anchors, guests, or callers.

Return a JSON array. Each item:
{
  "ticker": "NSE ticker (e.g. RELIANCE, NIFTY, BANKNIFTY)",
  "direction": "BUY" | "SELL" | "AVOID" | "WATCH",
  "price_level": <float or null>,
  "stop_loss": <float or null>,
  "target": <float or null>,
  "confidence": <float 0.0-1.0>,
  "summary": "<one-line summary>"
}

If Anil Singhvi makes no stock-specific calls, return [].
If the transcript has no mention of Anil Singhvi, return []."""


@dataclass
class TranscriptCall:
    ticker: str
    direction: str
    price_level: float | None
    stop_loss: float | None
    target: float | None
    confidence: float
    summary: str
    source: str = "zee_business_youtube"


class ZeeBusinessMonitor:
    """Downloads Zee Business live audio, transcribes, extracts Singhvi calls."""

    def __init__(self, grok_client: GrokClient) -> None:
        self._grok = grok_client
        self._running = False
        self._latest_calls: list[TranscriptCall] = []
        self._whisper_model = None
        self._deps_ok = False
        self._check_dependencies()

    def _check_dependencies(self) -> None:
        try:
            import yt_dlp  # noqa: F401
            import faster_whisper  # noqa: F401
            self._deps_ok = True
            log.info("youtube_monitor_deps_ok")
        except ImportError as exc:
            log.warning(
                "youtube_monitor_deps_missing",
                missing=str(exc),
                hint="pip install yt-dlp faster-whisper",
            )

    def _load_whisper(self):
        if self._whisper_model is None and self._deps_ok:
            from faster_whisper import WhisperModel
            self._whisper_model = WhisperModel(
                WHISPER_MODEL, device="cpu", compute_type="int8"
            )
            log.info("whisper_model_loaded", model=WHISPER_MODEL)
        return self._whisper_model

    async def _get_live_url(self) -> str | None:
        """Get the actual stream URL for the Zee Business live broadcast."""
        if not self._deps_ok:
            return None
        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "format": "bestaudio[ext=m4a]/bestaudio/best",
                "noplaylist": True,
            }
            loop = asyncio.get_running_loop()

            def _extract():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(ZEE_BUSINESS_URL, download=False)
                    return info.get("url") or info.get("manifest_url")

            return await loop.run_in_executor(None, _extract)
        except Exception as exc:
            log.error("zee_live_url_error", error=str(exc))
            return None

    async def _download_audio_chunk(self, stream_url: str, out_path: str) -> bool:
        """Download AUDIO_DURATION_SECONDS of audio from live stream."""
        if not self._deps_ok:
            return False
        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", stream_url,
                "-t", str(AUDIO_DURATION_SECONDS),
                "-vn",
                "-ar", "16000",
                "-ac", "1",
                "-f", "wav",
                out_path,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=AUDIO_DURATION_SECONDS + 30)
            return proc.returncode == 0
        except (asyncio.TimeoutError, FileNotFoundError) as exc:
            log.error("ffmpeg_error", error=str(exc))
            return False

    def _transcribe(self, audio_path: str) -> str:
        """Transcribe audio file using faster-whisper. Returns text."""
        model = self._load_whisper()
        if model is None:
            return ""
        segments, _ = model.transcribe(
            audio_path,
            language="hi",      # Hindi + English (Zee Business is bilingual)
            task="transcribe",
            vad_filter=True,
        )
        return " ".join(seg.text for seg in segments).strip()

    async def _extract_calls(self, transcript: str) -> list[TranscriptCall]:
        """Ask Grok to extract Singhvi's stock calls from transcript."""
        if not transcript.strip():
            return []
        try:
            raw = await self._grok.query(
                EXTRACT_PROMPT,
                f"Transcript:\n{transcript[:4000]}",
            )
            return _parse_transcript_calls(raw)
        except Exception as exc:
            log.error("zee_extract_error", error=str(exc))
            return []

    async def poll_once(self) -> list[TranscriptCall]:
        """Full pipeline: get URL → download audio → transcribe → extract calls."""
        if not self._deps_ok:
            log.debug("youtube_monitor_skipped_no_deps")
            return []

        stream_url = await self._get_live_url()
        if not stream_url:
            log.warning("zee_no_live_stream")
            return []

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            audio_path = tmp.name

        try:
            downloaded = await self._download_audio_chunk(stream_url, audio_path)
            if not downloaded:
                return []

            loop = asyncio.get_running_loop()
            transcript = await loop.run_in_executor(None, self._transcribe, audio_path)
            log.info("zee_transcribed", chars=len(transcript))

            calls = await self._extract_calls(transcript)
            self._latest_calls = calls
            log.info("zee_calls_extracted", count=len(calls))
            return calls
        finally:
            try:
                os.unlink(audio_path)
            except OSError:
                pass

    async def poll_loop(self) -> None:
        self._running = True
        log.info("zee_monitor_started", deps_ok=self._deps_ok)
        while self._running:
            if not should_poll_sentiment():
                await asyncio.sleep(30)
                continue
            await self.poll_once()
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._running = False

    @property
    def latest_calls(self) -> list[TranscriptCall]:
        return list(self._latest_calls)

    @property
    def is_available(self) -> bool:
        return self._deps_ok


def _parse_transcript_calls(text: str) -> list[TranscriptCall]:
    import json
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        start = text.find("[")
        end = text.rfind("]") + 1
        if start < 0 or end <= start:
            return []
        items = json.loads(text[start:end])
    except (json.JSONDecodeError, ValueError):
        return []

    calls = []
    for item in items:
        try:
            ticker = str(item.get("ticker", "")).upper().strip()
            direction = str(item.get("direction", "")).upper().strip()
            if not ticker or direction not in ("BUY", "SELL", "AVOID", "WATCH"):
                continue
            calls.append(TranscriptCall(
                ticker=ticker,
                direction=direction,
                price_level=_float_or_none(item.get("price_level")),
                stop_loss=_float_or_none(item.get("stop_loss")),
                target=_float_or_none(item.get("target")),
                confidence=max(0.0, min(1.0, float(item.get("confidence", 0.5)))),
                summary=str(item.get("summary", ""))[:200],
            ))
        except (TypeError, ValueError):
            continue
    return calls


def _float_or_none(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
