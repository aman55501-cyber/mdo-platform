"""tenders — VWLR's tender funnel from Supabase (project sysicrpylpnzpcuvpvjc).

Reads public.tender_candidates via PostgREST (SUPABASE_URL + SUPABASE_KEY, read
lazily so a missing key degrades to UNREACHABLE, never aborts the run).

Known defect handled, not hidden: `deadline` is being written as the *scan* date,
not the tender's closing date — table-wide ~85% of rows have
deadline::date == created_at::date. So this source DETECTS the pathology (>=80% of
the recent window) and prints "DEADLINE FIELD UNRELIABLE — parser writes scan date"
instead of any "closing within N days" number. It never reports the fake number.

What it does report honestly: the live funnel (status pending/accepted vs the
auto-rejected bulk) and the accepted/pending candidates themselves. The real
schema has no `score` column — relevance is `relevance_score` (int); value is
`value_inr` (often null, so never assumed).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from . import OK, Result
from ..config import IST

TABLE = "tender_candidates"
_WINDOW_DAYS = 21
_PATHOLOGY_THRESHOLD = 0.80
_LIVE_STATUSES = ("pending", "accepted")


class SupabaseError(RuntimeError):
    pass


def _creds() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = (
        os.environ.get("SUPABASE_KEY", "").strip()
        or os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
        or os.environ.get("SUPABASE_ANON_KEY", "").strip()
    )
    if not url or not key:
        raise SupabaseError("SUPABASE_URL / SUPABASE_KEY not set in .env")
    return url.rstrip("/"), key


def _fetch_recent(url: str, key: str) -> list[dict]:
    import httpx

    since = (datetime.now(IST) - timedelta(days=_WINDOW_DAYS)).date().isoformat()
    params = {
        "select": "title,authority,status,value_inr,relevance_score,created_at,deadline",
        "created_at": f"gte.{since}",
        "order": "created_at.desc",
        "limit": "1000",
    }
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{url}/rest/v1/{TABLE}", params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


def deadline_is_unreliable(rows: list[dict]) -> tuple[bool, float]:
    """Fraction of rows whose deadline date equals the created_at date. If that is
    >= 80% the deadline field is the scan date, not a closing date."""
    both = [r for r in rows if r.get("deadline") and r.get("created_at")]
    if not both:
        return True, 1.0  # no usable deadlines at all -> treat as unreliable
    bad = sum(1 for r in both if str(r["deadline"])[:10] == str(r["created_at"])[:10])
    frac = bad / len(both)
    return frac >= _PATHOLOGY_THRESHOLD, frac


def _authority_short(a: str | None) -> str:
    if not a:
        return ""
    return a.split("||")[0].strip()


def fetch() -> Result:
    url, key = _creds()
    rows = _fetch_recent(url, key)

    by_status: dict[str, int] = {}
    for r in rows:
        s = (r.get("status") or "unknown").lower()
        by_status[s] = by_status.get(s, 0) + 1

    live = [r for r in rows if (r.get("status") or "").lower() in _LIVE_STATUSES]
    unreliable, frac = deadline_is_unreliable(rows)

    # Build the funnel line (honest counts, never deadline-derived).
    pending = by_status.get("pending", 0)
    accepted = by_status.get("accepted", 0)
    rejected = by_status.get("rejected", 0)
    funnel = f"{pending} pending, {accepted} accepted, {rejected} auto-rejected (last {_WINDOW_DAYS}d)"

    if unreliable:
        deadline_note = (
            f"DEADLINE FIELD UNRELIABLE — parser writes scan date "
            f"({frac*100:.0f}% of rows deadline==scan); no closing-date count shown."
        )
    else:
        deadline_note = "deadline field looks usable this window."

    # Rows: the live funnel, most relevant first, no fabricated deadline shown.
    live_sorted = sorted(live, key=lambda r: (r.get("relevance_score") or 0), reverse=True)
    display = []
    for r in live_sorted[:12]:
        title = (r.get("title") or "(untitled)").strip()
        title = title[:90] + ("…" if len(title) > 90 else "")
        st = (r.get("status") or "").lower()
        display.append(
            {
                "gutter": "ACC" if st == "accepted" else "PEND",
                "severity": "alive" if st == "accepted" else "warning",
                "text": title,
                "meta": " · ".join(
                    x for x in [_authority_short(r.get("authority")),
                                f"rel {r.get('relevance_score')}" if r.get("relevance_score") else ""]
                    if x
                ),
            }
        )

    summary = f"{funnel}. {deadline_note}"
    return Result(
        name="tenders",
        status=OK,
        summary=summary,
        data={"by_status": by_status, "live": len(live),
              "deadline_unreliable": unreliable, "deadline_bad_frac": round(frac, 3)},
        extra={"rows": display},
    )
