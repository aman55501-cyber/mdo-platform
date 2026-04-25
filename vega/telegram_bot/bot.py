"""Telegram bot lifecycle and handler registration.

Commands are registered from a single source of truth: mdo_config.json.
Any command entry with a 3rd element (handler name) is auto-registered:

    ["/tenders", "Live tender pipeline", "cmd_tenders"]
     ^^^^^^^^^^   ^^^^^^^^^^^^^^^^^^^^^   ^^^^^^^^^^^^
     cmd name     Telegram menu label     VegaHandlers method

To add a new Telegram command:
  1. Write the handler method in handlers.py  (e.g. cmd_myreport)
  2. Add it to the right MDO node in mdo_config.json with the handler field
  3. Done — no changes needed here.
"""

from __future__ import annotations

from telegram import BotCommand, BotCommandScopeAllPrivateChats
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from ..config import TelegramConfig
from ..telegram_bot.mdo_store import get_store
from ..utils.logging import get_logger
from .handlers import VegaHandlers

log = get_logger("telegram_bot")

# Commands always present — not in MDO tree (navigation meta-commands)
_STATIC_COMMANDS = [
    ("/start",   "cmd_start",  "MDO mind map — tap to explore"),
    ("/help",    "cmd_help",   "Show MDO mind map"),
    ("/holdings","cmd_holdings","Equity holdings"),
]


class VegaTelegramBot:
    """Manages the Telegram bot lifecycle."""

    def __init__(self, config: TelegramConfig, engine) -> None:
        self._config = config
        self._handlers = VegaHandlers(engine)
        self._app: Application | None = None

    def build(self) -> Application:
        self._app = ApplicationBuilder().token(self._config.bot_token).build()
        h = self._handlers

        registered: set[str] = set()

        # 1. Register static commands that aren't in the MDO tree
        for cmd, method, _ in _STATIC_COMMANDS:
            fn = getattr(h, method, None)
            if fn and cmd not in registered:
                self._app.add_handler(CommandHandler(cmd.lstrip("/"), fn))
                registered.add(cmd)

        # 2. Walk MDO tree and register every command with a handler field
        store = get_store()
        for node_id in store.all_ids():
            node = store.get(node_id) or {}
            for entry in node.get("commands", []):
                if len(entry) < 3:
                    continue  # display-only row, no handler
                cmd_raw, _desc, handler_name = entry[0], entry[1], entry[2]
                # Extract base command name (/level TICKER … → "level")
                cmd_base = cmd_raw.lstrip("/").split()[0]
                if not cmd_base or cmd_base in registered:
                    continue
                fn = getattr(h, handler_name, None)
                if fn is None:
                    log.warning("mdo_handler_missing", handler=handler_name, cmd=cmd_base)
                    continue
                self._app.add_handler(CommandHandler(cmd_base, fn))
                registered.add(cmd_base)
                log.debug("cmd_registered", cmd=cmd_base, handler=handler_name)

        # 3. Fallback callbacks and text
        self._app.add_handler(CallbackQueryHandler(h.handle_callback))
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, h.handle_text)
        )

        log.info("telegram_bot_configured", commands=len(registered))
        return self._app

    async def register_commands(self) -> None:
        """Push the command menu to Telegram (the '/' popup list).

        Menu is built from MDO tree + static commands — same single source.
        """
        if self._app is None:
            return

        menu: list[BotCommand] = []
        seen: set[str] = set()

        # Static first
        for cmd, _method, desc in _STATIC_COMMANDS:
            cmd_base = cmd.lstrip("/")
            if cmd_base not in seen:
                menu.append(BotCommand(cmd_base, desc[:256]))
                seen.add(cmd_base)

        # Then walk MDO tree in tree order (breadth-first via root children)
        store = get_store()
        order = _bfs_node_order(store)
        for node_id in order:
            node = store.get(node_id) or {}
            for entry in node.get("commands", []):
                if len(entry) < 3:
                    continue
                cmd_raw, desc = entry[0], entry[1]
                cmd_base = cmd_raw.lstrip("/").split()[0]
                if not cmd_base or cmd_base in seen:
                    continue
                # Use the display text as the menu description, trimmed
                menu_desc = desc[:256] if desc else cmd_raw[:256]
                menu.append(BotCommand(cmd_base, menu_desc))
                seen.add(cmd_base)

        try:
            await self._app.bot.set_my_commands(
                menu, scope=BotCommandScopeAllPrivateChats()
            )
            log.info("telegram_commands_registered", count=len(menu))
        except Exception as exc:
            log.warning("telegram_commands_register_failed", error=str(exc))

    @property
    def app(self) -> Application | None:
        return self._app


# ── helpers ──────────────────────────────────────────────────────────── #

def _bfs_node_order(store) -> list[str]:
    """Return all node IDs in breadth-first tree order starting from root."""
    from collections import deque
    visited: list[str] = []
    queue: deque[str] = deque(["root"])
    seen: set[str] = set()
    while queue:
        nid = queue.popleft()
        if nid in seen:
            continue
        seen.add(nid)
        visited.append(nid)
        node = store.get(nid) or {}
        for child in node.get("children", []):
            queue.append(child)
    return visited
