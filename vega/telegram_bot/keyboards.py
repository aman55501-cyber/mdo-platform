"""Inline keyboards for Telegram — MDO mind map with live edit support.

All tree data comes from MdoStore (mdo_config.json). Editing is done
in-place via inline buttons without leaving the chat.

Edit flow per node:
  [normal view]  →  tap ✏️ Edit  →  [edit mode]
  Edit mode shows: Rename | + Add Command | − Remove Command | × Delete Section | ✓ Done
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .mdo_store import get_store


# ------------------------------------------------------------------ #
#  Mind map — normal navigation                                        #
# ------------------------------------------------------------------ #

def mdo_root_keyboard() -> InlineKeyboardMarkup:
    store = get_store()
    root = store.get("root") or {}
    buttons = []
    for child_id in root.get("children", []):
        node = store.get(child_id)
        if not node:
            continue
        buttons.append([
            InlineKeyboardButton(
                f"{node.get('icon','')} {node.get('label', child_id)}",
                callback_data=f"mdo_{child_id}",
            )
        ])
    buttons.append([
        InlineKeyboardButton("✏️ Edit map", callback_data="mdo_edit_root"),
        InlineKeyboardButton("↩ Top", callback_data="mdo_root"),
    ])
    return InlineKeyboardMarkup(buttons)


def mdo_node_keyboard(node_id: str) -> InlineKeyboardMarkup:
    store = get_store()
    node = store.get(node_id)
    if not node:
        return mdo_root_keyboard()

    buttons = []

    if "children" in node:
        for child_id in node["children"]:
            child = store.get(child_id)
            if not child:
                continue
            buttons.append([
                InlineKeyboardButton(
                    f"{child.get('icon','')} {child.get('label', child_id)}",
                    callback_data=f"mdo_{child_id}",
                )
            ])
    elif "commands" in node:
        for i, (cmd, desc) in enumerate(node["commands"]):
            label = cmd if not desc else f"{cmd}  —  {desc}"
            buttons.append([
                InlineKeyboardButton(label[:60], callback_data=f"mdo_noop_{node_id}_{i}")
            ])

    # Edit + Back row
    buttons.append([
        InlineKeyboardButton("✏️ Edit",  callback_data=f"mdo_edit_{node_id}"),
        InlineKeyboardButton("« Back",  callback_data="mdo_root"),
    ])
    return InlineKeyboardMarkup(buttons)


def mdo_node_text(node_id: str) -> str:
    store = get_store()
    node = store.get(node_id) or store.get("root") or {}
    icon  = node.get("icon", "")
    label = node.get("label", node_id)

    if "commands" in node:
        lines = [f"<b>{icon} {label}</b>\n"]
        for cmd, desc in node["commands"]:
            if cmd.startswith("/"):
                lines.append(f"<code>{cmd}</code>" + (f"  — {desc}" if desc else ""))
            elif cmd:
                lines.append(f"  {cmd}")
        return "\n".join(lines)
    elif "children" in node:
        return f"<b>{icon} {label}</b>\n\nTap a section to expand:"
    return f"<b>{icon} {label}</b>"


# ------------------------------------------------------------------ #
#  Edit mode keyboards                                                 #
# ------------------------------------------------------------------ #

def mdo_edit_keyboard(node_id: str) -> InlineKeyboardMarkup:
    """Edit-mode keyboard for a node.

    Parent node  → Rename | + Add Section | × Delete | ✓ Done
    Leaf node    → Rename | + Add Command | Remove commands | × Delete | ✓ Done
    """
    store = get_store()
    node = store.get(node_id)
    if not node:
        return mdo_root_keyboard()

    locked = node.get("locked", False)
    buttons = []

    # Rename
    buttons.append([
        InlineKeyboardButton("✏️ Rename", callback_data=f"mdoedit_rename_{node_id}"),
        InlineKeyboardButton("🎨 Icon",   callback_data=f"mdoedit_icon_{node_id}"),
    ])

    if "commands" in node:
        # + Add Command
        buttons.append([
            InlineKeyboardButton("＋ Add command", callback_data=f"mdoedit_addcmd_{node_id}"),
        ])
        # Remove individual commands
        for i, (cmd, _) in enumerate(node["commands"]):
            label = cmd[:35] + ("…" if len(cmd) > 35 else "")
            buttons.append([
                InlineKeyboardButton(f"✕ {label}", callback_data=f"mdoedit_rmcmd_{node_id}_{i}"),
            ])
    elif "children" in node:
        buttons.append([
            InlineKeyboardButton("＋ Add section", callback_data=f"mdoedit_addsec_{node_id}"),
        ])

    # Delete section (not locked, not root)
    if not locked and node_id != "root":
        buttons.append([
            InlineKeyboardButton("🗑 Delete this section", callback_data=f"mdoedit_del_{node_id}"),
        ])

    buttons.append([
        InlineKeyboardButton("✓ Done", callback_data=f"mdo_{node_id}"),
    ])
    return InlineKeyboardMarkup(buttons)


def mdo_edit_text(node_id: str) -> str:
    store = get_store()
    node = store.get(node_id) or {}
    icon  = node.get("icon", "")
    label = node.get("label", node_id)
    return (
        f"<b>✏️ Editing: {icon} {label}</b>\n\n"
        "Choose what to change:"
    )


# ------------------------------------------------------------------ #
#  Trade confirmation                                                  #
# ------------------------------------------------------------------ #

def trade_confirmation_keyboard(signal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{signal_id}"),
            InlineKeyboardButton("❌ Reject",  callback_data=f"reject_{signal_id}"),
        ],
        [
            InlineKeyboardButton("📝 Modify Qty", callback_data=f"modify_{signal_id}"),
        ],
    ])


def watchlist_keyboard(tickers: list[str]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(t, callback_data=f"sentiment_{t}")]
        for t in tickers
    ]
    return InlineKeyboardMarkup(buttons)


def otp_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Cancel Login", callback_data="cancel_otp")]
    ])


def autosinghvi_keyboard(current: bool) -> InlineKeyboardMarkup:
    status = "ON" if current else "OFF"
    action = "off" if current else "on"
    label  = f"Auto-execute: {status}  —  tap to turn {action.upper()}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f"autosinghvi_{action}")]
    ])
