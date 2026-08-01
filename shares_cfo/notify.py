"""Push notifications — deliver critical alerts to your phone.

Two zero-fuss channels, pick either (or both) via .env:
  * ntfy:     CFO_NTFY_TOPIC=<a long random string>   (install the ntfy app, subscribe)
  * Telegram: CFO_TELEGRAM_BOT_TOKEN=... + CFO_TELEGRAM_CHAT_ID=...
Web-push needs a service worker + VAPID + per-device subscription and is flaky on a
server; these are reliable and work from a headless VPS. Sending is best-effort and
never raises into the caller.
"""

from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("shares_cfo.notify")


def configured() -> list[str]:
    ch = []
    if os.environ.get("CFO_NTFY_TOPIC"):
        ch.append("ntfy")
    if os.environ.get("CFO_TELEGRAM_BOT_TOKEN") and os.environ.get("CFO_TELEGRAM_CHAT_ID"):
        ch.append("telegram")
    return ch


def send(title: str, body: str) -> list[str]:
    """Send to every configured channel; return the ones that accepted it."""
    sent = []
    topic = os.environ.get("CFO_NTFY_TOPIC", "").strip()
    if topic:
        try:
            # ntfy's Title header must be ASCII (HTTP headers are latin-1). Emoji live
            # in the body (UTF-8); the header gets an ASCII-stripped title, and if that
            # dropped anything we prepend the full title to the body so nothing is lost.
            ascii_title = title.encode("ascii", "ignore").decode("ascii").strip() or "Shares CFO"
            msg = body if ascii_title == title.strip() else f"{title}\n{body}"
            r = httpx.post(f"https://ntfy.sh/{topic}", data=msg.encode("utf-8"),
                           headers={"Title": ascii_title[:120], "Priority": "high"},
                           timeout=10.0)
            if r.status_code < 400:
                sent.append("ntfy")
        except Exception as exc:
            log.warning("ntfy send failed: %s", exc)
    tok = os.environ.get("CFO_TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("CFO_TELEGRAM_CHAT_ID", "").strip()
    if tok and chat:
        try:
            r = httpx.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                           json={"chat_id": chat, "text": f"{title}\n{body}"}, timeout=10.0)
            if r.status_code < 400:
                sent.append("telegram")
        except Exception as exc:
            log.warning("telegram send failed: %s", exc)
    return sent
