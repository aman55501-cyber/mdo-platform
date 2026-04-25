"""Persistent MDO mind map tree.

The tree is stored in mdo_config.json next to the project root.
On first run it seeds from MDO_DEFAULTS. Every edit is written back immediately.

Node schema:
  {
    "label": "Aditi Investments",
    "icon":  "📊",
    "children": ["vega_trading", "vega_levels", ...],   # parent nodes
    "commands": [["/cmd", "description"], ...],          # leaf nodes (one or the other)
    "locked": false                                      # locked nodes can't be removed
  }
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any

_DEFAULT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "mdo_config.json"
)

# ------------------------------------------------------------------ #
#  Default tree (seed data — written to file on first run)            #
# ------------------------------------------------------------------ #

MDO_DEFAULTS: dict[str, Any] = {
    "root": {
        "label": "MDO — Aman Agrawal",
        "icon": "🗺",
        "children": ["aditi", "vwlr", "hotel", "compliance", "brief"],
        "locked": True,
    },
    "aditi": {
        "label": "Aditi Investments",
        "icon": "📊",
        "children": ["vega_trading", "vega_levels", "vega_singhvi", "vega_portfolio"],
    },
    "vega_trading": {
        "label": "VEGA — Trading Engine",
        "icon": "🤖",
        "commands": [
            ["/testbroker",  "Connect HDFC Securities"],
            ["/positions",   "Open positions"],
            ["/funds",       "Available funds & margin"],
            ["/pnl",         "Today P&L summary"],
            ["/health",      "System health"],
        ],
    },
    "vega_levels": {
        "label": "Price Levels",
        "icon": "📐",
        "commands": [
            ["/level TICKER BUY price SL x TGT y", "Add level"],
            ["/levels",       "List active levels"],
            ["/removelevel",  "Remove level by ID"],
        ],
    },
    "vega_singhvi": {
        "label": "Anil Singhvi Signals",
        "icon": "📡",
        "commands": [
            ["/singhvi",         "Latest calls (live X)"],
            ["/autosinghvi on",  "Enable auto-execute"],
            ["/autosinghvi off", "Disable auto-execute"],
            ["/autosinghvi status", "Current setting"],
        ],
    },
    "vega_portfolio": {
        "label": "Sentiment & Watchlist",
        "icon": "🔍",
        "commands": [
            ["/sentiment TICKER", "Live X sentiment"],
            ["/brief",            "Morning market brief"],
            ["/grok <question>",  "Ask Grok anything"],
            ["/watchlist",        "View watchlist"],
            ["/add TICKER",       "Add to watchlist"],
            ["/remove TICKER",    "Remove from watchlist"],
        ],
    },
    "vwlr": {
        "label": "VWLR — Washery",
        "icon": "🏭",
        "commands": [
            ["(Tenders module — coming L5)", ""],
        ],
    },
    "hotel": {
        "label": "Hotel ANS",
        "icon": "🏨",
        "commands": [
            ["(Hotel ops module — coming L5)", ""],
        ],
    },
    "compliance": {
        "label": "Compliance & Legal",
        "icon": "⚖",
        "commands": [
            ["(Compliance watcher — coming L3)", ""],
        ],
    },
    "brief": {
        "label": "Daily / Weekly Brief",
        "icon": "📋",
        "commands": [
            ["/brief",          "Morning brief (Grok live)"],
            ["/grok <question>","Ask Grok anything"],
            ["/status",         "VEGA engine status"],
        ],
    },
}


# ------------------------------------------------------------------ #
#  Store                                                               #
# ------------------------------------------------------------------ #

class MdoStore:
    """In-memory MDO tree with JSON persistence.

    Usage (singleton):
        store = MdoStore()
        node  = store.get("aditi")
        store.rename("aditi", "Aditi Capital")
        store.add_command("vega_trading", "/newcmd", "description")
        store.remove_command("vega_trading", 0)
    """

    def __init__(self, path: str = _DEFAULT_PATH) -> None:
        self._path = os.path.abspath(path)
        self._tree: dict[str, Any] = {}
        self._load()

    # -- Read ----------------------------------------------------------

    def get(self, node_id: str) -> dict | None:
        return self._tree.get(node_id)

    def all_ids(self) -> list[str]:
        return list(self._tree.keys())

    def root_children(self) -> list[str]:
        root = self._tree.get("root", {})
        return list(root.get("children", []))

    # -- Write ---------------------------------------------------------

    def rename(self, node_id: str, new_label: str) -> bool:
        node = self._tree.get(node_id)
        if not node:
            return False
        node["label"] = new_label.strip()[:60]
        self._save()
        return True

    def set_icon(self, node_id: str, icon: str) -> bool:
        node = self._tree.get(node_id)
        if not node:
            return False
        node["icon"] = icon.strip()[:4]
        self._save()
        return True

    def add_command(self, node_id: str, cmd: str, desc: str) -> bool:
        """Add a command entry to a leaf node."""
        node = self._tree.get(node_id)
        if not node or "children" in node:
            return False
        if "commands" not in node:
            node["commands"] = []
        node["commands"].append([cmd.strip()[:80], desc.strip()[:80]])
        self._save()
        return True

    def remove_command(self, node_id: str, index: int) -> bool:
        """Remove command at index from a leaf node."""
        node = self._tree.get(node_id)
        if not node:
            return False
        cmds = node.get("commands", [])
        if index < 0 or index >= len(cmds):
            return False
        cmds.pop(index)
        self._save()
        return True

    def add_section(self, parent_id: str, node_id: str, label: str, icon: str = "📌") -> bool:
        """Add a new child section under a parent node."""
        parent = self._tree.get(parent_id)
        if not parent or "commands" in parent:
            return False
        if node_id in self._tree:
            return False
        self._tree[node_id] = {
            "label": label.strip()[:60],
            "icon": icon.strip()[:4],
            "commands": [],
        }
        parent.setdefault("children", []).append(node_id)
        self._save()
        return True

    def remove_section(self, node_id: str) -> bool:
        """Remove a section node (not root, not locked)."""
        node = self._tree.get(node_id)
        if not node or node.get("locked") or node_id == "root":
            return False
        # Remove from any parent's children list
        for nid, n in self._tree.items():
            if node_id in n.get("children", []):
                n["children"].remove(node_id)
        del self._tree[node_id]
        self._save()
        return True

    def reset_to_defaults(self) -> None:
        self._tree = deepcopy(MDO_DEFAULTS)
        self._save()

    # -- Persistence ---------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    self._tree = json.load(f)
            else:
                self._tree = deepcopy(MDO_DEFAULTS)
                self._save()
        except (json.JSONDecodeError, OSError):
            self._tree = deepcopy(MDO_DEFAULTS)
            self._save()

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._tree, f, indent=2, ensure_ascii=False)
        except OSError as exc:
            pass  # non-fatal — changes stay in memory


# Module-level singleton
_store: MdoStore | None = None


def get_store() -> MdoStore:
    global _store
    if _store is None:
        _store = MdoStore()
    return _store
