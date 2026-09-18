"""gmail_mail — a read-only 24h sweep of key senders (brief's Home/Operations feed).

Reads only. It never sends and never drafts here (drafting is a Phase 4 action, and
even then a Gmail *draft* only — rule 5). Credentials come from google_auth; a
missing token degrades this one panel to UNREACHABLE.

Two things:
  1. Mail from key senders (Vimal, Hotel ANS, HDFC, hotel brands, Progility, plus
     any subject containing "Hotel ANS" or "VWLR") in the last 24h — counted and
     listed. Nil state in words: "no mail from key senders in 24h".
  2. Tender247 (admin@bidsnrfp.com): counted, and the announced tender count parsed
     out of the subject line, e.g. "10  New Tender/s, 17-Sep-26 - Tender247".
"""

from __future__ import annotations

import re

from . import NIL, OK, Result
from .google_auth import gmail_service

# Senders / domains that matter. Domains use Gmail's from:domain matching.
KEY_SENDERS = [
    "vimal500321@gmail.com",
    "gm@hotelans.in",
    "finance@hotelans.in",
    "hdfc.bank.in",
    "hdfcsec.com",
    "marriott.com",
    "radissonhotels.com",
    "gingerhotels.com",
    "fernhotels.com",
    "spreehotels",
    "staybloom.com",
    "progilitytech.com",
]
SUBJECT_TERMS = ["Hotel ANS", "VWLR"]
TENDER247_SENDER = "admin@bidsnrfp.com"

_TENDER_COUNT_RE = re.compile(r"(\d+)\s*new\s+tender", re.IGNORECASE)


def build_key_query() -> str:
    froms = " OR ".join(f"from:{s}" for s in KEY_SENDERS)
    subs = " OR ".join(f'subject:"{t}"' for t in SUBJECT_TERMS)
    return f"newer_than:1d ({froms} OR {subs})"


def parse_tender_count(subject: str) -> int | None:
    """Pull the announced tender count out of a Tender247 subject line."""
    m = _TENDER_COUNT_RE.search(subject or "")
    return int(m.group(1)) if m else None


def _header(msg: dict, name: str) -> str:
    for h in msg.get("payload", {}).get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _list_ids(service, query: str, cap: int = 40) -> list[str]:
    resp = service.users().messages().list(userId="me", q=query, maxResults=cap).execute()
    return [m["id"] for m in resp.get("messages", [])]


def fetch() -> Result:
    service = gmail_service()

    # 1) key senders
    key_ids = _list_ids(service, build_key_query())
    rows = []
    for mid in key_ids[:20]:
        msg = service.users().messages().get(
            userId="me", id=mid, format="metadata",
            metadataHeaders=["From", "Subject"],
        ).execute()
        sender = _header(msg, "From")
        subject = _header(msg, "Subject") or "(no subject)"
        rows.append(
            {
                "gutter": "MAIL", "severity": "quiet",
                "text": subject[:80] + ("…" if len(subject) > 80 else ""),
                "meta": sender[:60],
            }
        )

    # 2) Tender247 announced count
    t_ids = _list_ids(service, f"newer_than:1d from:{TENDER247_SENDER}", cap=10)
    announced = None
    for mid in t_ids:
        msg = service.users().messages().get(
            userId="me", id=mid, format="metadata", metadataHeaders=["Subject"]
        ).execute()
        n = parse_tender_count(_header(msg, "Subject"))
        if n is not None:
            announced = n if announced is None else max(announced, n)

    key_n = len(key_ids)
    if announced is not None:
        tender_line = f"Tender247 announced {announced} new tenders"
    elif t_ids:
        tender_line = f"Tender247: {len(t_ids)} mail(s), count not in subject"
    else:
        tender_line = "no Tender247 mail in 24h"

    if key_n:
        summary = f"{key_n} mail(s) from key senders in 24h. {tender_line}."
        status = OK
    else:
        summary = f"No mail from key senders in 24h. {tender_line}."
        status = NIL
    return Result(
        name="mail",
        status=status,
        summary=summary,
        data={"key_senders": key_n, "tender247_announced": announced},
        extra={"rows": rows},
    )
