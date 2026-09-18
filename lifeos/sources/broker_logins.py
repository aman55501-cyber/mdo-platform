"""broker_logins — fold the daily HDFC/Angel logins into the 06:30 run.

'All daily logins happen here.' Reuses shares_cfo (its config + token_store + Angel
adapter) rather than a second way to do the same thing:

  Angel accounts — log in server-side (TOTP + MPIN), so LIFEOS arms them
                   automatically each morning. ALIVE on success, FAILED with reason.
  HDFC accounts  — need Aman's phone OAuth (/hdfc/login); they cannot be auto-armed.
                   LIFEOS reports whether today's token is present: ALIVE if armed,
                   NEEDS LOGIN otherwise (and the nudge loop drafts a reminder).

Off by default: set LIFEOS_BROKER_LOGINS=1 to enable (it needs shares_cfo deps and
per-account creds, and the token store on a shared volume). When off, the panel says
so — never a blank. shares_cfo is imported lazily so LIFEOS stays standalone.
"""

from __future__ import annotations

import asyncio

from . import NIL, OK, Result
from ..config import optional

_ENABLED = ("1", "true", "yes", "on")


def _enabled() -> bool:
    return optional("LIFEOS_BROKER_LOGINS").lower() in _ENABLED


# ── seams (import shares_cfo lazily; monkeypatched in tests) ───────────────────
def load_accounts() -> list[tuple[str, str, str]]:
    """Return [(creds_key, broker, label)] from shares_cfo config."""
    from shares_cfo import config as scfg  # lazy

    out: list[tuple[str, str, str]] = []
    for key in scfg.get_accounts():
        try:
            acct = scfg.load_account(key)
            out.append((acct.creds_key, acct.broker, acct.label))
        except Exception as exc:  # noqa: BLE001 — one bad account shouldn't hide the rest
            out.append((key, "unknown", f"config error: {type(exc).__name__}"))
    return out


def angel_login(creds_key: str) -> None:
    """Log an Angel account in server-side; raises on failure."""
    from shares_cfo import config as scfg  # lazy
    from shares_cfo.brokers.angel import AngelAdapter  # lazy

    acct = scfg.load_account(creds_key)
    adapter = AngelAdapter(acct)

    async def _run():
        try:
            await adapter._ensure_login()  # arms token_store on success
        finally:
            await adapter.close()

    asyncio.run(_run())


def hdfc_armed(creds_key: str) -> bool:
    from shares_cfo import token_store  # lazy

    return token_store.is_armed(creds_key)


# ── the source ────────────────────────────────────────────────────────────────
def fetch() -> Result:
    if not _enabled():
        return Result(
            name="broker_logins",
            status=NIL,
            summary="Broker logins not enabled here — set LIFEOS_BROKER_LOGINS=1 to run daily HDFC/Angel logins in the 06:30 run.",
        )

    accounts = load_accounts()
    rows: list[dict] = []
    armed = needs = failed = 0
    for key, broker, label in accounts:
        if broker == "angel":
            try:
                angel_login(key)
                rows.append({"gutter": "ALIVE", "severity": "alive", "text": f"{label} ({key})", "meta": "Angel · logged in server-side"})
                armed += 1
            except Exception as exc:  # noqa: BLE001
                rows.append({"gutter": "FAIL", "severity": "critical", "text": f"{label} ({key})", "meta": f"Angel login failed: {type(exc).__name__}: {exc}"[:90]})
                failed += 1
        elif broker == "hdfc":
            if hdfc_armed(key):
                rows.append({"gutter": "ALIVE", "severity": "alive", "text": f"{label} ({key})", "meta": "HDFC · armed today"})
                armed += 1
            else:
                rows.append({"gutter": "LOGIN", "severity": "warning", "text": f"{label} ({key})", "meta": "HDFC · needs your phone login today (/hdfc/login)"})
                needs += 1
        else:
            rows.append({"gutter": "?", "severity": "warning", "text": f"{label} ({key})", "meta": broker})
            needs += 1

    total = len(accounts)
    summary = f"{armed}/{total} accounts armed"
    if needs:
        summary += f", {needs} need your login"
    if failed:
        summary += f", {failed} failed"
    summary += "."
    return Result(
        name="broker_logins",
        status=OK,
        summary=summary,
        data={"armed": armed, "needs_login": needs, "failed": failed, "total": total},
        extra={"rows": rows},
    )
