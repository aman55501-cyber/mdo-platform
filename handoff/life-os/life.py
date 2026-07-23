"""Life OS data layer — a shared household cockpit, scoped so Jahnavi sees only what's shared.

Two audiences, one store:
  • Owner (full CFO_API_TOKEN)  — sees & edits everything (private + shared).
  • Partner (CFO_SHARE_TOKEN)   — read-mostly; sees only items flagged `shared`,
    and may tick a shared task done or leave a note. Never reaches the trading /
    business book — the share token authenticates ONLY the /life endpoints.

Editable (not import-driven) because a life OS is lived-in: quick add, tick off,
share/unshare. Stored as plain JSON on the state volume so it survives rebuilds.
Nothing here touches money, brokers or business secrets.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

LIFE_DIR = Path(__file__).resolve().parent / "data" / "state" / "life"
_STORE = LIFE_DIR / "items.json"
_LOCK = threading.Lock()

# What a life item can be. Free-form categories, but a small kind vocabulary keeps
# the console tidy (icons/columns) without constraining the user.
KINDS = ("task", "event", "list", "bill", "note", "goal")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> list[dict]:
    if not _STORE.exists():
        return []
    try:
        data = json.loads(_STORE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _write(items: list[dict]) -> None:
    LIFE_DIR.mkdir(parents=True, exist_ok=True)
    _STORE.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")


def _clean(it: dict) -> dict:
    """Public shape of an item (drops nothing sensitive — there is nothing sensitive)."""
    return {
        "id": it.get("id"),
        "title": it.get("title", ""),
        "kind": it.get("kind", "task"),
        "category": it.get("category", ""),
        "due": it.get("due", ""),
        "done": bool(it.get("done", False)),
        "shared": bool(it.get("shared", False)),
        "priority": it.get("priority", ""),
        "notes": it.get("notes", ""),
        "owner": it.get("owner", "aman"),
        "created_at": it.get("created_at"),
        "updated_at": it.get("updated_at"),
    }


def _sort_key(it: dict):
    # Open first, then by due date (empty due sorts last), then newest.
    due = it.get("due") or "9999-12-31"
    return (bool(it.get("done")), due, it.get("created_at") or "")


def list_items(scope: str = "full") -> dict:
    """All items for the owner; only shared items for the partner scope."""
    items = _load()
    if scope == "share":
        items = [i for i in items if i.get("shared")]
    items = sorted((_clean(i) for i in items), key=_sort_key)
    return {
        "scope": scope,
        "items": items,
        "count": len(items),
        "open": sum(1 for i in items if not i["done"]),
        "shared": sum(1 for i in items if i["shared"]),
    }


def add(fields: dict, owner: str = "aman", scope: str = "full") -> dict:
    # A partner add always lands in the shared space (she has no private lane), and is
    # tagged to her so the owner can see who added it.
    shared = bool(fields.get("shared", False))
    if scope == "share":
        shared = True
        owner = "jahnavi"
    it = {
        "id": uuid.uuid4().hex[:12],
        "title": str(fields.get("title", "")).strip()[:200],
        "kind": (fields.get("kind") or "task") if (fields.get("kind") in KINDS) else "task",
        "category": str(fields.get("category", "")).strip()[:40],
        "due": str(fields.get("due", "")).strip()[:10],
        "done": bool(fields.get("done", False)),
        "shared": shared,
        "priority": str(fields.get("priority", "")).strip()[:12],
        "notes": str(fields.get("notes", "")).strip()[:500],
        "owner": owner,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    if not it["title"]:
        raise ValueError("title is required")
    with _LOCK:
        items = _load()
        items.append(it)
        _write(items)
    return _clean(it)


# Jahnavi (share scope) has read/write/edit on *shared* items: she can change every
# field EXCEPT `shared` itself — locking that stops her accidentally un-sharing an item
# and losing her own access to it. Un/re-sharing stays with the owner.
_SHARE_WRITABLE = {"title", "kind", "category", "due", "done", "priority", "notes"}
# Fields the owner may patch (everything, including the share flag).
_OWNER_WRITABLE = {"title", "kind", "category", "due", "done", "shared", "priority", "notes"}


def update(item_id: str, patch: dict, scope: str = "full") -> dict:
    with _LOCK:
        items = _load()
        for it in items:
            if it.get("id") != item_id:
                continue
            if scope == "share":
                if not it.get("shared"):
                    raise PermissionError("not a shared item")
                allowed = _SHARE_WRITABLE
            else:
                allowed = _OWNER_WRITABLE
            for k, v in patch.items():
                if k not in allowed:
                    continue
                if k in ("done", "shared"):
                    it[k] = bool(v)
                elif k == "kind":
                    it[k] = v if v in KINDS else it.get("kind", "task")
                else:
                    it[k] = str(v).strip()[:500]
            it["updated_at"] = _now_iso()
            _write(items)
            return _clean(it)
    raise KeyError(item_id)


def delete(item_id: str, scope: str = "full") -> bool:
    """Owner may delete anything; partner may delete only shared items."""
    with _LOCK:
        items = _load()
        target = next((i for i in items if i.get("id") == item_id), None)
        if target is None:
            return False
        if scope == "share" and not target.get("shared"):
            raise PermissionError("not a shared item")
        _write([i for i in items if i.get("id") != item_id])
    return True


def stats() -> dict:
    items = _load()
    return {
        "total": len(items),
        "open": sum(1 for i in items if not i.get("done")),
        "shared": sum(1 for i in items if i.get("shared")),
        "overdue": sum(1 for i in items
                       if not i.get("done") and i.get("due")
                       and i["due"] < datetime.now(timezone.utc).strftime("%Y-%m-%d")),
    }
