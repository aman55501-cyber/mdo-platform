"""Angel SmartWebSocketV2 live tick stream — true real-time LTP / OI / volume.

The broker pushes a binary tick every time a subscribed contract trades, so instead
of polling a quote endpoint we hold one WebSocket open and decode ticks as they land.
The decoded values flow into the SAME in-memory cache the positions view reads, so the
app shows live P&L / OI the instant the market moves — no request-time broker call.

Fully optional and self-healing: shares the book's Angel session (JWT + feed token),
reconnects on drop, only runs in market hours, and never raises into the app. If it
can't connect (no Angel login yet, network, or the lib is missing), the REST warm-tick
loop keeps everything working — this just makes it faster when it's up.

Binary layout (little-endian) per SmartWebSocketV2:
  byte 0 mode · byte 1 exchange · [2:27] token · [43:51] LTP(paise)
  mode>=2: [67:75] volume · [115:123] close(paise)
  mode 3 : [131:139] open interest
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
import time
from datetime import datetime, timedelta, timezone

log = logging.getLogger("shares_cfo.angel_ws")

WS_URL = "wss://smartapisocket.angelone.in/smart-stream"
_EXCH_NFO = 2      # exchangeType for NSE F&O
_MODE_SNAPQUOTE = 3  # LTP + volume + OI

STATE = {"connected": False, "last_tick": 0.0, "reason": "starting"}


def _market_open() -> bool:
    now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    if now.weekday() > 4:
        return False
    m = now.hour * 60 + now.minute
    return 555 <= m <= 930  # 09:15–15:30 IST


async def _ws_connect(websockets, headers):
    # websockets>=13 renamed extra_headers -> additional_headers; support both.
    try:
        return await websockets.connect(WS_URL, additional_headers=headers,
                                        open_timeout=15, ping_interval=None)
    except TypeError:
        return await websockets.connect(WS_URL, extra_headers=headers,
                                        open_timeout=15, ping_interval=None)


class Feed:
    """Owns the WebSocket. Reads the live token set + writes into the shared tick cache."""

    def __init__(self, ticks: dict, stream_tokens: set):
        self.ticks = ticks              # {"ts": float, "q": {token: {...}}}
        self.stream = stream_tokens     # shared set of Angel tokens currently on screen
        self._corr = 0

    def _tokens(self) -> list:
        return [str(t) for t in list(self.stream) if t]

    def _creds(self):
        from . import token_store
        from .config import get_accounts, load_account
        key = next((k for k in get_accounts() if k.upper().startswith("ANGEL")), None)
        if not key:
            STATE["reason"] = "no Angel account"
            return None
        jwt, feed = token_store.get_token(key), token_store.get_feed(key)
        if not (jwt and feed):
            STATE["reason"] = "Angel not logged in (no jwt/feed token yet)"
            return None
        acc = load_account(key)
        return {"jwt": jwt, "feed": feed, "api_key": acc.api_key, "client": acc.client_code}

    async def run(self) -> None:
        await asyncio.sleep(20)  # let the first Angel login + a positions load populate tokens
        while True:
            try:
                await self._session()
            except Exception as exc:
                STATE.update(connected=False, reason=str(exc)[:120])
                log.info("angel ws session ended: %s", str(exc)[:120])
            await asyncio.sleep(5)

    async def _session(self) -> None:
        if not _market_open():
            STATE.update(connected=False, reason="market closed")
            await asyncio.sleep(30)
            return
        c = self._creds()
        if not c:
            await asyncio.sleep(20)
            return
        try:
            import websockets
        except ImportError:
            STATE["reason"] = "websockets lib missing"
            await asyncio.sleep(60)
            return
        headers = [("Authorization", c["jwt"]), ("x-api-key", c["api_key"]),
                   ("x-client-code", c["client"]), ("x-feed-token", c["feed"])]
        ws = await _ws_connect(websockets, headers)
        STATE.update(connected=True, reason="connected")
        log.info("angel ws connected")
        hb = asyncio.create_task(self._heartbeat(ws))
        try:
            await self._subscribe(ws)
            sent = set(self._tokens())
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=45)
                if isinstance(msg, (bytes, bytearray)):
                    self._parse(bytes(msg))
                cur = set(self._tokens())
                if cur and cur != sent:      # a leg opened/closed -> resubscribe
                    await self._subscribe(ws)
                    sent = cur
                if not _market_open():
                    break
        finally:
            hb.cancel()
            STATE.update(connected=False)
            try:
                await ws.close()
            except Exception:
                pass

    async def _heartbeat(self, ws) -> None:
        while True:
            await asyncio.sleep(25)
            try:
                await ws.send("ping")   # Angel keep-alive; server replies "pong"
            except Exception:
                return

    async def _subscribe(self, ws) -> None:
        toks = self._tokens()
        if not toks:
            return
        self._corr += 1
        await ws.send(json.dumps({
            "correlationID": f"cfo{self._corr}", "action": 1,
            "params": {"mode": _MODE_SNAPQUOTE,
                       "tokenList": [{"exchangeType": _EXCH_NFO, "tokens": toks}]},
        }))

    def _parse(self, b: bytes) -> None:
        if len(b) < 51:
            return
        try:
            mode = b[0]
            token = b[2:27].split(b"\x00", 1)[0].decode("ascii", "ignore")
            if not token:
                return
            ltp = struct.unpack_from("<q", b, 43)[0] / 100.0
            rec = self.ticks["q"].setdefault(token, {})
            rec["ltp"] = ltp
            if mode >= 2 and len(b) >= 123:
                rec["volume"] = struct.unpack_from("<q", b, 67)[0]
                close = struct.unpack_from("<q", b, 115)[0] / 100.0
                rec["change_pct"] = round((ltp / close - 1) * 100, 2) if close else None
            if mode == _MODE_SNAPQUOTE and len(b) >= 139:
                rec["oi"] = struct.unpack_from("<q", b, 131)[0]
            now = time.time()
            rec["ts"] = now
            self.ticks["ts"] = now
            STATE["last_tick"] = now
        except Exception:
            pass


_FEED: Feed | None = None


def start(ticks: dict, stream_tokens: set) -> None:
    """Launch the live feed as a background task (no-op if CFO_WS_ENABLED=0)."""
    import os
    if os.environ.get("CFO_WS_ENABLED", "1").strip() == "0":
        STATE["reason"] = "disabled (CFO_WS_ENABLED=0)"
        log.info("angel ws disabled")
        return
    global _FEED
    _FEED = Feed(ticks, stream_tokens)
    try:
        asyncio.get_event_loop().create_task(_FEED.run())
    except RuntimeError:
        asyncio.ensure_future(_FEED.run())
    log.info("angel ws scheduled")
