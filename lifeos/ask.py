"""The ask bar — /ask.

Two behaviours (brief):
  * A message starting `capture:` or `remind:` skips the model and writes a row to
    the Notion Inbox with Status = New, then confirms. The 06:30 run files those the
    next morning. This is the ONE write LIFEOS makes, and the user initiates it.
  * Anything else calls Anthropic with the current run's state injected as the system
    prompt and streams the answer back. No data goes to the model that isn't already
    on the page. The model is instructed to draft/answer only, never to transact.

Credentials (ANTHROPIC_API_KEY, NOTION_TOKEN) are read lazily; a missing one yields a
plain error string rather than crashing the endpoint. /ask is behind the same HTTP
Basic gate as the page (it costs money per call).
"""

from __future__ import annotations

import os
from typing import Iterator, Optional

from . import db
from .sources import notion_client as nc

INBOX_DS = "577583d5-934f-4d26-bda6-4ffb7593eb42"

_SYSTEM_PREAMBLE = (
    "You are LIFEOS, Aman Agrawal's private morning console for the ANS Group. "
    "Answer ONLY from the console state provided below — do not invent numbers. If the "
    "state doesn't contain the answer, say so plainly. You are read-and-draft only: you "
    "may explain, summarise, or draft text, but never instruct the user to move money, "
    "sign, or file — those are his click. Be terse and concrete; he is on a phone."
)


# ── capture / remind ──────────────────────────────────────────────────────────
def parse_capture(message: str) -> Optional[tuple[str, str]]:
    """Return (kind, text) if the message is a capture/remind command, else None."""
    stripped = message.lstrip()
    low = stripped.lower()
    for prefix in ("capture:", "remind:", "remind me:"):
        if low.startswith(prefix):
            return prefix.rstrip(":").split()[0], stripped[len(prefix):].strip()
    return None


def write_capture(kind: str, text: str) -> str:
    """Write an Inbox row (Status=New) and return a confirmation string."""
    if not text:
        return "Nothing to capture — the note was empty."
    props = {
        "Item": nc.title_prop(text),
        "Status": nc.select_prop("New"),
        "For": nc.select_prop("Aman"),
        "Note": nc.text_prop(f"via ask bar ({kind})"),
    }
    nc.create_page(INBOX_DS, props)
    verb = "Reminder" if kind.startswith("remind") else "Captured"
    return f"{verb} → Inbox (New). It gets filed in tomorrow's 06:30 run."


# ── model answer ──────────────────────────────────────────────────────────────
def build_state_context() -> str:
    """Assemble the current run's facts — the same facts the page shows."""
    run = db.latest_run()
    if run is None:
        return "No run has completed yet; the console has no state."
    lines = [
        f"Run #{run['id']} · {run['trigger']} · started {run['started_at']} · "
        f"{run['sources_ok']} ok / {run['sources_unreachable']} unreachable.",
        "Sources:",
    ]
    for s in db.sources_for_run(run["id"]):
        detail = (s["detail"] or "").strip()
        lines.append(f"- {s['name']} [{s['status']}]: {detail}")
    return "\n".join(lines)


def _model() -> str:
    return os.environ.get("LIFEOS_LLM_MODEL", "").strip() or "claude-sonnet-5"


def stream_answer(question: str) -> Iterator[str]:
    """Yield the model's answer in chunks. On any error, yield a plain message."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        yield "ANTHROPIC_API_KEY not set — the ask bar is offline until it is added to .env."
        return
    try:
        from anthropic import Anthropic
    except ImportError:
        yield "anthropic SDK not installed."
        return

    system = f"{_SYSTEM_PREAMBLE}\n\n--- CONSOLE STATE ---\n{build_state_context()}"
    try:
        client = Anthropic(api_key=key)
        with client.messages.stream(
            model=_model(),
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}],
        ) as stream:
            for text in stream.text_stream:
                yield text
    except Exception as exc:  # noqa: BLE001 — surface a message, never 500 the bar
        yield f"\n[ask error: {type(exc).__name__}: {exc}]"
