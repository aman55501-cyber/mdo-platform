"""Life OS — scoped item store + the two-token security guard.

One flat item store (tasks, events, bills, lists, notes) that two people work
from over the SAME endpoints, separated only by which token they hold:

    CFO_API_TOKEN    → owner  · sees & edits everything (private + shared)
    CFO_SHARE_TOKEN  → share  · sees & edits ONLY items flagged `shared`

The core invariant lives here, not in the UI: the share token's view of the
store is filtered SERVER-SIDE before any response leaves the process. A private
item is never serialised into a share-scope response, so the partner cannot see
it even by inspecting the wire. And because this project only mounts /life
routes, the share token has no path to trading or business data at all.

This module was reconstructed from the DESIGN_EXPORT handoff (the original
life.py was not carried across in the extraction). Behaviour matches the
documented /life/* contract exactly.
"""

from __future__ import annotations

import hmac
import json
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

# ── storage ──────────────────────────────────────────────────────────────────
# A JSON list on the persistent volume. LIFE_STATE_DIR defaults to
# data/state/life next to this project; Railway/containers mount a volume there.
STATE_DIR = Path(os.environ.get("LIFE_STATE_DIR", Path(__file__).parent / "data" / "state" / "life"))
ITEMS_PATH = STATE_DIR / "items.json"

_LOCK = threading.RLock()

# Item "kinds" — the one flat store holds all of them.
KIND = Literal["task", "event", "bill", "list", "note"]
VALID_KINDS = ("task", "event", "bill", "list", "note")

# Fields the share scope is allowed to write on POST/PATCH. Notably absent:
# `shared` — the partner can never flip an item's shared flag.
SHARE_WRITABLE = frozenset({"kind", "title", "notes", "due", "amount", "category", "done", "items"})
# Fields the owner may write. `shared` included — only the owner toggles sharing.
OWNER_WRITABLE = SHARE_WRITABLE | {"shared"}


# ── the two-token guard ──────────────────────────────────────────────────────
Scope = Literal["owner", "share"]


@dataclass(frozen=True)
class LifeScope:
    """Resolved caller identity. Returned by `_life_scope`, threaded through
    every route so filtering/authorisation decisions read off one object."""
    scope: Scope

    @property
    def is_owner(self) -> bool:
        return self.scope == "owner"

    @property
    def is_share(self) -> bool:
        return self.scope == "share"

    @property
    def name(self) -> str:
        return "owner" if self.is_owner else "Jahnavi"


class LifeAuthError(Exception):
    """Raised when no token, or an unrecognised token, is presented. The caller
    (app.py) maps this to 401. Deliberately carries no token material."""


def _tokens() -> tuple[str, str]:
    """Read the two secrets from the environment. Never logged, never returned
    to a client, never written anywhere but the process env (loaded from .env)."""
    owner = os.environ.get("CFO_API_TOKEN", "")
    share = os.environ.get("CFO_SHARE_TOKEN", "")
    if not owner or not share:
        raise RuntimeError(
            "CFO_API_TOKEN and CFO_SHARE_TOKEN must both be set (see .env.example)."
        )
    if hmac.compare_digest(owner, share):
        # A shared secret would collapse the two scopes into one — refuse to run.
        raise RuntimeError("CFO_API_TOKEN and CFO_SHARE_TOKEN must be distinct.")
    return owner, share


def _life_scope(presented: Optional[str]) -> LifeScope:
    """The guard. Constant-time-match the presented token against the two
    secrets and resolve a scope. Owner is checked first, but both comparisons
    always run so timing does not leak which token matched.

    `presented` is whatever the transport extracted (header or share-link query
    param). Matching is constant-time via hmac.compare_digest; a miss raises
    LifeAuthError. The token value is never logged here or anywhere upstream.
    """
    owner_token, share_token = _tokens()
    tok = presented or ""
    is_owner = hmac.compare_digest(tok, owner_token)
    is_share = hmac.compare_digest(tok, share_token)
    if is_owner:
        return LifeScope("owner")
    if is_share:
        return LifeScope("share")
    raise LifeAuthError("invalid or missing token")


# ── item model ───────────────────────────────────────────────────────────────
def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_item(payload: dict[str, Any], *, forced_shared: Optional[bool] = None,
              created_by: Scope = "owner") -> dict[str, Any]:
    """Build a fully-formed item from a (already scope-filtered) payload.

    `forced_shared`, when not None, overrides the shared flag regardless of
    payload — this is how a partner add is forced shared."""
    kind = payload.get("kind", "task")
    if kind not in VALID_KINDS:
        raise ValueError(f"kind must be one of {VALID_KINDS}")
    ts = _now()
    shared = bool(payload.get("shared", False)) if forced_shared is None else forced_shared
    return {
        "id": uuid.uuid4().hex,
        "kind": kind,
        "title": (payload.get("title") or "").strip(),
        "notes": payload.get("notes", ""),
        "shared": shared,
        "done": bool(payload.get("done", False)),
        "due": payload.get("due"),                # ISO date/datetime or None
        "amount": payload.get("amount"),          # for bills; else None
        "category": payload.get("category"),      # for future category lanes
        "items": payload.get("items", []),        # for `list` kind — flat for now
        "created_at": ts,
        "updated_at": ts,
        "created_by": created_by,
    }


# ── persistence ──────────────────────────────────────────────────────────────
def _load() -> list[dict[str, Any]]:
    with _LOCK:
        if not ITEMS_PATH.exists():
            return []
        try:
            data = json.loads(ITEMS_PATH.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return data if isinstance(data, list) else []


def _save(items: list[dict[str, Any]]) -> None:
    with _LOCK:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = ITEMS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(ITEMS_PATH)  # atomic swap so a crash can't leave a half file


# ── scoped CRUD — every path enforces the invariant ──────────────────────────
def _visible(items: Iterable[dict[str, Any]], scope: LifeScope) -> list[dict[str, Any]]:
    """The single server-side filter. Owner sees all; share sees only shared."""
    if scope.is_owner:
        return list(items)
    return [it for it in items if it.get("shared")]


def list_items(scope: LifeScope) -> list[dict[str, Any]]:
    """GET /life/items — owner: all · share: only shared (filtered here)."""
    return _visible(_load(), scope)


def create_item(scope: LifeScope, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /life/items — a partner add is forced shared; owner add honours the
    payload's `shared`. Only scope-writable fields are read off the payload."""
    if scope.is_share:
        clean = {k: v for k, v in payload.items() if k in SHARE_WRITABLE}
        item = _new_item(clean, forced_shared=True, created_by="share")
    else:
        clean = {k: v for k, v in payload.items() if k in OWNER_WRITABLE}
        item = _new_item(clean, created_by="owner")
    with _LOCK:
        items = _load()
        items.append(item)
        _save(items)
    return item


def _find(items: list[dict[str, Any]], item_id: str) -> Optional[int]:
    for i, it in enumerate(items):
        if it.get("id") == item_id:
            return i
    return None


def update_item(scope: LifeScope, item_id: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
    """PATCH /life/items/{id} — share may edit shared items but NOT the `shared`
    flag; owner may edit anything. Returns None when the item isn't visible to
    the caller (mapped to 404 — existence of private items is never revealed)."""
    with _LOCK:
        items = _load()
        idx = _find(items, item_id)
        if idx is None:
            return None
        item = items[idx]

        if scope.is_share:
            # Partner can only touch shared items, and cannot un/re-share.
            if not item.get("shared"):
                return None  # invisible → 404, no leak
            allowed = SHARE_WRITABLE
        else:
            allowed = OWNER_WRITABLE

        for k, v in patch.items():
            if k in allowed:
                item[k] = v
        item["updated_at"] = _now()
        items[idx] = item
        _save(items)
    return item


def delete_item(scope: LifeScope, item_id: str) -> bool:
    """DELETE /life/items/{id} — share may delete shared items only; owner any.
    Returns False when not visible to the caller (mapped to 404)."""
    with _LOCK:
        items = _load()
        idx = _find(items, item_id)
        if idx is None:
            return False
        if scope.is_share and not items[idx].get("shared"):
            return False  # invisible → 404, no leak
        items.pop(idx)
        _save(items)
    return True
