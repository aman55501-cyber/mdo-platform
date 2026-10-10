"""mail-reader — IMAP intake of statements, contract notes and tender results. Rules only, zero LLM spend.

Aman, chat 2026-10-09 (AMAN_PENDING A26 C1): the Gmail app password lives in the VPS .env. Everything that lands
in aman.55501@gmail.com from the exchanges, the brokers, the bank, the registrars, the insurer, CDSL e-voting and
bidsnrfp is pulled over IMAP (SSL, imaplib + the email stdlib), categorised by sender + subject, stored in the
vault (finance/mail/<date>_<category>_<safe-subject>/<filename>) and counted. Aman hears ONE WhatsApp line only
when something actionable arrived: a tender result, a bank statement, or a broker holding statement. Contract
notes, MF confirmations, insurance and e-voting are stored silently.

Locked PDFs (Angel One: the PAN; SIB and HDFC Sec: a password) are detected with pypdf.is_encrypted, flagged
attachment_locked=1 with summary "locked PDF (PAN/password) — not opened" and NEVER opened: no password is tried,
none is asked for in chat (Directive 9). The Share Master Angel import takes the unlocked PDF Aman prints himself.

Tables of its own:
  mail_messages   one row per message (message_id UNIQUE = the dedupe key), category, entity_hint (exact name
                  matches only — never guessed), attachment names (JSON), attachment_locked, stored_path (relative
                  to the vault), summary, status new/seen/ack, actionable, pushed_at
  mail_state      the mailbox watermark (last UID) + UIDVALIDITY; a changed UIDVALIDITY resets the watermark

Credentials: GMAIL_IMAP_USER / GMAIL_APP_PASSWORD (never logged, never returned — only "configured" / "not
configured"); GMAIL_IMAP_HOST defaults to imap.gmail.com, MAIL_READER_FOLDER to INBOX. A login failure is a
reported warning ("IMAP login failed: <reason without credentials>"), never a crash (Directive 5).

Run by `python mdo_agent.py mail-reader` (fleet.yaml: mail-reader) every 30 min 07:00-22:00 IST and once at
22:30 IST, through POST /api/mail/run. First run: the last FIRST_RUN_DAYS days only, at most MAX_PER_RUN messages.
The pure helpers above register() take plain values and touch nothing — tests/test_mail.py runs them without a
server and with a fake imaplib.IMAP4_SSL.
"""
from __future__ import annotations

import email
import email.policy
import email.utils
import html as _html
import imaplib
import io
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from mdo_cos import IST

BOT_ID = "mail-reader"
CATEGORIES = ("broker-statement", "contract-note", "exchange-balance", "bank-statement", "tender-result",
              "mf-transaction", "insurance", "evoting", "grok-tender", "other")
ACTIONABLE_CATEGORIES = ("tender-result", "bank-statement", "broker-statement")
STATUSES = ("new", "seen", "ack")
ENTITY_NAMES = ("ADITI INVESTMENTS", "AMAN AGRAWAL", "ASHOK KUMAR AGRAWAL", "VEDANTA WASHERY")   # exact, never guessed
FIRST_RUN_DAYS = 7
MAX_PER_RUN = 300
SUMMARY_MAX = 600
LOCKED_SUMMARY = "locked PDF (PAN/password) — not opened"
VAULT_AREA = "finance/mail"            # inside the vault's finance/ area (mdo_cos.VAULT_AREAS)
NOT_CONFIGURED = "IMAP not configured"
MAIL_DOMAIN_LABELS = {              # sender domain → the short name Aman knows it by (push line + Morning card)
    "sib.bank.in": "SIB", "hdfcsec.com": "HDFC Sec", "angeltrade.in": "Angel One", "angelone.in": "Angel One",
    "bidsnrfp.com": "bidsnrfp", "nse.co.in": "NSE", "bseindia.in": "BSE", "kfintech.com": "KFintech",
    "camsonline.com": "CAMS", "hdfcergo.com": "HDFC Ergo", "cdslindia.co.in": "CDSL",
}
HOLDING_RX = re.compile(r"holding|dp transaction|register of securities|consolidated|portfolio statement", re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS mail_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid INTEGER NOT NULL DEFAULT 0,
    message_id TEXT NOT NULL UNIQUE,
    from_addr TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    received_at TEXT,                                 -- ISO, UTC
    category TEXT NOT NULL DEFAULT 'other',
    entity_hint TEXT NOT NULL DEFAULT '',
    attachment_names TEXT NOT NULL DEFAULT '[]',      -- JSON list
    attachment_locked INTEGER NOT NULL DEFAULT 0,
    stored_path TEXT NOT NULL DEFAULT '',             -- relative to the vault, '' when nothing was stored
    summary TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new',               -- new | seen | ack
    actionable INTEGER NOT NULL DEFAULT 0,
    pushed_at TEXT,
    acked_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_mail_messages_received ON mail_messages(received_at);
CREATE INDEX IF NOT EXISTS idx_mail_messages_category ON mail_messages(category, status);
CREATE TABLE IF NOT EXISTS mail_state (
    mailbox TEXT PRIMARY KEY,
    last_uid INTEGER NOT NULL DEFAULT 0,
    uidvalidity INTEGER,
    last_run_at TEXT, last_line TEXT DEFAULT '',
    runs INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now'))
);
"""


# ═════════════════════════════════════════════════════════════════════════════
# Pure helpers — no database, no network
# ═════════════════════════════════════════════════════════════════════════════

def _query_tz(s: str) -> str:
    """'2026-10-09T08:00:00 05:30' → '+05:30': an unescaped '+' in a query string arrives as a space."""
    return re.sub(r" (\d\d:\d\d)$", r"+\1", s.strip())

def config() -> dict:
    """The IMAP settings. The password never leaves this dict's `password` key; `configured` is what gets logged."""
    user = os.environ.get("GMAIL_IMAP_USER", "").strip()
    pw = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    return {"user": user, "password": pw, "configured": bool(user and pw),
            "host": os.environ.get("GMAIL_IMAP_HOST", "").strip() or "imap.gmail.com",
            "folder": os.environ.get("MAIL_READER_FOLDER", "").strip() or "INBOX"}


def redact(text: Any, cfg: dict | None = None) -> str:
    """Strip the credentials from any string that might reach a log or a report (an IMAP error can echo the login)."""
    s = str(text or "")
    cfg = cfg or config()
    for secret in (cfg.get("password"), cfg.get("user")):
        if secret and len(secret) >= 4:
            s = s.replace(secret, "[redacted]")
    return s


def domain_of(from_addr: str) -> str:
    addr = email.utils.parseaddr(from_addr or "")[1] or str(from_addr or "")
    return addr.rsplit("@", 1)[-1].strip().lower() if "@" in addr else ""


def _domain_in(domain: str, *roots: str) -> bool:
    return any(domain == r or domain.endswith("." + r) for r in roots)


def sender_label(from_addr: str) -> str:
    d = domain_of(from_addr)
    for root, label in MAIL_DOMAIN_LABELS.items():
        if _domain_in(d, root):
            return label
    return d or "unknown sender"


def categorise(from_addr: str, subject: str) -> str:
    """Sender + subject rules. An unknown sender is `other` — never guessed from the subject alone."""
    d, s = domain_of(from_addr), " ".join(str(subject or "").split()).lower()
    if "[grok-tender]" in s and (_domain_in(d, *GROK_DOMAINS) or _own_address(from_addr)):
        return "grok-tender"                 # only Grok's own mail or Aman's mailbox; any other sender cannot feed the pipeline
    if _domain_in(d, "nse.co.in", "bseindia.in"):
        return "exchange-balance"
    if _domain_in(d, "hdfcsec.com", "angeltrade.in", "angelone.in"):
        if "contract note" in s or "contract-note" in s:
            return "contract-note"
        return "broker-statement"
    if _domain_in(d, "sib.bank.in", "sib.co.in", "southindianbank.com"):
        return "bank-statement"
    if _domain_in(d, "bidsnrfp.com"):
        return "tender-result" if ("tender" in s or "participation" in s) else "other"
    if "kfintech" in d or "camsonline" in d or _domain_in(d, "kfintech.com", "camsonline.com"):
        return "mf-transaction"
    if _domain_in(d, "hdfcergo.com"):
        return "insurance"
    if _domain_in(d, "cdslindia.co.in", "cdslindia.com") and ("evoting" in d or "e-voting" in s or "evoting" in s or "voting" in s):
        return "evoting"
    return "other"


GROK_DOMAINS = ("x.ai", "grok.com", "xai.com")


def _own_address(from_addr: str) -> bool:
    """True when the mail comes from the mailbox this bot reads (Aman forwarding or Grok sending through his Gmail)."""
    own = os.environ.get("GMAIL_IMAP_USER", "").strip().lower()
    return bool(own) and own in str(from_addr or "").lower()


def parse_grok_tenders(text: str) -> list[dict]:
    """The [GROK-TENDER] email table, pipe-separated, header row first:
    buyer|title|tender id|category|publish|closing|value|EMD|eligibility|location|URL. One dict per data row;
    the header, 'NONE FOUND' and any line with fewer than 6 cells are skipped. Nothing is inferred."""
    from mdo_tenders_direct import parse_date
    out, seen = [], set()
    for raw in str(text or "").splitlines():
        line = raw.strip().lstrip("-*•").strip()
        if line.count("|") < 5:
            continue
        cells = [c.strip() for c in line.split("|")]
        cells[0] = re.sub(r"^\[GROK-TENDER\]\s*", "", cells[0], flags=re.I).strip()
        if cells[0].lower() == "buyer" or (len(cells) > 1 and cells[1].lower() == "title") or set("".join(cells)) <= set("-: "):
            continue
        cells += [""] * (11 - len(cells))
        url = next((c for c in cells[::-1] if c.lower().startswith("http")), "")
        title, tid = cells[1], cells[2]
        key = (tid or title).lower()
        if not title or key in seen:
            continue
        seen.add(key)
        out.append({"buyer": cells[0][:120], "title": title[:300], "tender_id": tid[:80], "category": cells[3][:60],
                    "published": parse_date(cells[4]), "due_date": parse_date(cells[5]), "value": cells[6][:60],
                    "emd": cells[7][:60], "eligibility": cells[8][:200], "location": cells[9][:80], "url": url[:500],
                    "line": line[:300]})
    return out


def entity_hint(*texts: str) -> str:
    """The exact names found (case-insensitive, whole-word), in ENTITY_NAMES order, joined by '; '. Nothing else."""
    blob = " ".join(" ".join(str(t or "").split()) for t in texts).upper()
    found = [n for n in ENTITY_NAMES if re.search(r"(?<![A-Z0-9])" + re.escape(n) + r"(?![A-Z0-9])", blob)]
    return "; ".join(found)


def is_actionable(category: str, subject: str) -> bool:
    """tender results and bank statements always; a broker mail only when it is a holding statement."""
    if category in ("tender-result", "bank-statement"):
        return True
    if category == "broker-statement":
        return bool(HOLDING_RX.search(str(subject or "")))
    return False


def safe_name(text: str, limit: int = 60) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", str(text or "")).strip("._-")
    s = re.sub(r"_+", "_", s)
    return (s[:limit].rstrip("._-") or "untitled")


def safe_filename(name: str, fallback: str = "attachment") -> str:
    base = os.path.basename(str(name or "").replace("\\", "/")).strip()
    base = safe_name(base, 120)
    if base in ("", "untitled") or base.startswith("."):
        return fallback
    return base


def is_locked_pdf(data: bytes) -> bool:
    """True when the PDF is encrypted. Detection only — never decrypted, no password tried."""
    if not data or not data[:5].startswith(b"%PDF"):
        return False
    try:
        from pypdf import PdfReader
        return bool(PdfReader(io.BytesIO(data)).is_encrypted)
    except Exception:
        return b"/Encrypt" in data[:200000]


def html_to_text(html: str) -> str:
    """Tags out, table cells joined by ' | ', one line per row/paragraph. No parser dependency."""
    s = str(html or "")
    s = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</t[dh]\s*>", " | ", s)
    s = re.sub(r"(?i)</(tr|p|div|li|h[1-6]|table)\s*>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = _html.unescape(s)
    lines = []
    for ln in s.splitlines():
        ln = " ".join(ln.split())
        ln = re.sub(r"(\s*\|\s*)+$", "", ln)
        ln = re.sub(r"^(\s*\|\s*)+", "", ln)
        ln = re.sub(r"\s*\|\s*", " | ", ln)
        if ln:
            lines.append(ln)
    return "\n".join(lines)


_TENDER_WORD = re.compile(r"tender|result|award|\bl[123]\b|bid|rfp|nit\b|winner|participat|qualified|cancel", re.I)
_RESULT_WORD = re.compile(r"award|\bl[123]\b|\bwon\b|lost|rejected|cancel|retender|result|qualified|disqualified|technically|financial|opened", re.I)
_HEADER_CELL = re.compile(r"^(s\.?\s*no\.?|sr\.?\s*no\.?|#|tender( name| title)?|title|name|result|status|buyer|organisation|organization|department|value|date|due date|closing date)$", re.I)
_PROSE_SKIP = ("dear ", "regards", "thanks", "thank you", "unsubscribe", "this email", "this e-mail", "click here", "copyright",
               "here are", "please find", "team ")


def _links(html: str) -> dict[str, str]:
    out = {}
    for u, t in re.findall(r'(?is)href="([^"]+)"[^>]*>(.*?)</a>', str(html or "")):
        text = " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", t)).split()).lower()
        if text:
            out[text] = u
    return out


def parse_tender_html(html: str) -> list[dict]:
    """bidsnrfp 'New Tender Results : Participation Insights': every table row that names a tender becomes
    {title, result, line, url}; with no table, the prose lines that carry tender words. Nothing is inferred —
    the title is the row's first text cell, the result the first cell with a result word, as the mail wrote them."""
    text = html_to_text(html)
    link_by_text = _links(html)
    lines = text.splitlines()
    table_rows = []
    for line in lines:
        cells = [c.strip() for c in line.split(" | ") if c.strip()]
        if len(cells) < 2:
            continue
        if all(_HEADER_CELL.match(c) for c in cells):
            continue
        table_rows.append((line, cells))
    out, seen = [], set()

    def _add(title: str, result: str, line: str) -> None:
        key = title.lower()
        if not title or key in seen:
            return
        seen.add(key)
        url = ""
        low = line.lower()
        for t, u in link_by_text.items():
            if t in low:
                url = u
                break
        out.append({"title": title[:200], "result": result[:120], "line": line[:300], "url": url[:500]})

    if table_rows:
        for line, cells in table_rows:
            texty = [c for c in cells if not re.fullmatch(r"[\d.)]+", c)]
            if not texty:
                continue
            title = texty[0]
            result = next((c for c in texty[1:] if _RESULT_WORD.search(c)), "")
            _add(title, result, line)
        return out
    for line in lines:
        low = line.lower()
        if len(line) < 8 or not _TENDER_WORD.search(line) or low.startswith(_PROSE_SKIP):
            continue
        m = re.search(r"\s[-–—:]\s", line)
        title, result = (line[:m.start()].strip(), line[m.end():].strip()) if m else (line, "")
        _add(title, result if _RESULT_WORD.search(result) else "", line)
    return out


def tender_summary(rows: list[dict], text: str = "") -> str:
    """Plain text, ≤ SUMMARY_MAX chars: 'N results: title — result; …' or the body's first lines."""
    if rows:
        parts = [(r["title"] + (" — " + r["result"] if r.get("result") else "")) for r in rows]
        s = f"{len(rows)} tender result{'s' if len(rows) != 1 else ''}: " + "; ".join(parts)
    else:
        s = " ".join(str(text or "").split())
    return s[:SUMMARY_MAX].rstrip()


def parse_message(raw: bytes, uid: int = 0) -> dict:
    """One RFC822 message → the fields the table needs plus the body and the attachments (bytes stay in memory)."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    subject = " ".join(str(msg.get("Subject") or "").split())
    from_hdr = str(msg.get("From") or "")
    from_addr = (email.utils.parseaddr(from_hdr)[1] or from_hdr).strip().lower()
    mid = " ".join(str(msg.get("Message-ID") or "").split()).strip()
    if not mid:
        mid = f"<uid-{uid}-{safe_name(from_addr, 40)}-{safe_name(subject, 40)}>"
    received = None
    try:
        d = email.utils.parsedate_to_datetime(str(msg.get("Date") or ""))
        if d is not None:
            received = (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (TypeError, ValueError):
        received = None
    text, html, attachments = [], [], []
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.is_multipart():
            continue
        disp = str(part.get("Content-Disposition") or "").lower()
        fname = part.get_filename()
        ctype = part.get_content_type()
        if fname or disp.startswith("attachment"):
            try:
                data = part.get_payload(decode=True) or b""
            except Exception:
                data = b""
            attachments.append({"name": safe_filename(fname or f"part-{len(attachments) + 1}.bin"),
                                "content_type": ctype, "data": data})
            continue
        if ctype in ("text/plain", "text/html"):
            try:
                body = part.get_content()
            except Exception:
                payload = part.get_payload(decode=True) or b""
                body = payload.decode(part.get_content_charset() or "utf-8", "replace")
            (html if ctype == "text/html" else text).append(str(body))
    return {"uid": int(uid or 0), "message_id": mid[:300], "from_addr": from_addr[:200], "subject": subject[:500],
            "received_at": received.isoformat() if received else None,
            "text": "\n".join(text), "html": "\n".join(html), "attachments": attachments}


def describe(parsed: dict, category: str) -> dict:
    """Category, entity hint, locked flag, summary and the tender rows for one parsed message. Pure."""
    locked_names = [a["name"] for a in parsed["attachments"] if is_locked_pdf(a["data"])]
    names = [a["name"] for a in parsed["attachments"]]
    html_text = html_to_text(parsed["html"]) if parsed["html"] else ""
    body_text = parsed["text"].strip() or html_text          # many senders ship a stub text part and the real body in HTML
    hint = entity_hint(parsed["subject"], body_text[:20000], html_text[:20000], " ".join(names))
    tenders = parse_tender_html(parsed["html"]) if category == "tender-result" and parsed["html"] else []
    if category == "tender-result" and not tenders and body_text:
        tenders = parse_tender_html("<p>" + "</p><p>".join(body_text.splitlines()) + "</p>")
    if category == "tender-result" and html_text:
        body_text = html_text                                  # the summary fallback reads the real body
    if category == "grok-tender":
        tenders = parse_grok_tenders(html_text or body_text)
    if locked_names:
        summary = LOCKED_SUMMARY + (f" · {', '.join(locked_names)}" if len(locked_names) <= 3 else f" · {len(locked_names)} files")
    elif category == "tender-result":
        summary = tender_summary(tenders, body_text)
    elif category == "grok-tender":
        summary = (f"{len(tenders)} tender{'s' if len(tenders) != 1 else ''} from Grok: "
                   + "; ".join(f"{t['buyer']} — {t['title']}" for t in tenders[:4])) if tenders else "Grok: NONE FOUND"
    elif names:
        summary = f"{len(names)} attachment{'s' if len(names) != 1 else ''}: " + ", ".join(names[:5])
    else:
        summary = " ".join(body_text.split())[:200]
    return {"category": category, "entity_hint": hint, "attachment_names": names, "locked": bool(locked_names),
            "locked_names": locked_names, "summary": summary[:SUMMARY_MAX], "tenders": tenders,
            "actionable": bool(tenders) if category == "grok-tender" else is_actionable(category, parsed["subject"])}


def push_text(rows: list[dict]) -> str:
    """ONE WhatsApp line for the actionable rows of a run, e.g.
    "Mail: 2 tender results (bidsnrfp), 1 SIB bank statement (locked) — see Morning › Mail"."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["category"], sender_label(r["from_addr"])), []).append(r)
    order = {"tender-result": 0, "grok-tender": 0, "bank-statement": 1, "broker-statement": 2}
    parts = []
    for (cat, label), rs in sorted(groups.items(), key=lambda kv: (order.get(kv[0][0], 9), kv[0][1])):
        n = len(rs)
        locked = all(int(r.get("attachment_locked") or 0) for r in rs) and n > 0
        if cat == "grok-tender":
            parts.append(f"{n} Grok tender list{'s' if n != 1 else ''}")
        elif cat == "tender-result":
            parts.append(f"{n} tender result{'s' if n != 1 else ''} ({label})")
        elif cat == "bank-statement":
            parts.append(f"{n} {label} bank statement{'s' if n != 1 else ''}" + (" (locked)" if locked else ""))
        else:
            parts.append(f"{n} {label} holding statement{'s' if n != 1 else ''}" + (" (locked)" if locked else ""))
    return "Mail: " + ", ".join(parts) + " — see Morning › Mail"


def heartbeat_line(counts: dict, locked: int, imap: str = "IMAP ok") -> str:
    """"mail-reader: N new (tender R, broker B, bank K, mf M, other O), W locked — IMAP ok"."""
    broker = counts.get("broker-statement", 0) + counts.get("contract-note", 0) + counts.get("exchange-balance", 0)
    other = counts.get("insurance", 0) + counts.get("evoting", 0) + counts.get("other", 0)
    total = sum(counts.values())
    grok = f", grok {counts['grok-tender']}" if counts.get("grok-tender") else ""
    return (f"{BOT_ID}: {total} new (tender {counts.get('tender-result', 0)}, broker {broker}, "
            f"bank {counts.get('bank-statement', 0)}, mf {counts.get('mf-transaction', 0)}, other {other}{grok}), "
            f"{locked} locked — {imap}")


def _imap_date(d: datetime) -> str:
    return d.strftime("%d-%b-%Y")


def _uids(data: Any) -> list[int]:
    out = []
    for chunk in data or []:
        if isinstance(chunk, bytes):
            out.extend(int(x) for x in chunk.split() if x.isdigit())
    return sorted(set(out))


def _fetched_bytes(data: Any) -> bytes | None:
    for item in data or []:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
            return bytes(item[1])
    return None


def fetch_new(cfg: dict, last_uid: int, uidvalidity: int | None, now: datetime | None = None,
              first_run_days: int = FIRST_RUN_DAYS, cap: int = MAX_PER_RUN) -> dict:
    """IMAP over SSL: log in, select the folder read-only, list the UIDs above the watermark (first run: the last
    `first_run_days` days, newest `cap`), fetch each with BODY.PEEK[] (nothing is marked read). Returns
    {ok, reason, uidvalidity, messages: [(uid, raw)], candidates, truncated}. Never raises; the reason is redacted."""
    now = now or datetime.now(timezone.utc)
    res: dict[str, Any] = {"ok": False, "reason": "", "uidvalidity": uidvalidity, "messages": [], "candidates": 0,
                           "truncated": 0, "reset": False}
    try:
        conn = imaplib.IMAP4_SSL(cfg["host"])
    except Exception as e:
        res["reason"] = f"IMAP connect failed: {redact(e, cfg)[:160]}"
        return res
    try:
        try:
            conn.login(cfg["user"], cfg["password"])
        except Exception as e:
            res["reason"] = f"IMAP login failed: {redact(e, cfg)[:160]}"
            return res
        typ, _ = conn.select(cfg["folder"], readonly=True)
        if typ != "OK":
            res["reason"] = f"IMAP select {cfg['folder']} failed"
            return res
        validity = None
        try:
            v = conn.response("UIDVALIDITY")[1]
            validity = int(v[0]) if v and v[0] is not None else None
        except Exception:
            validity = None
        res["uidvalidity"] = validity
        if uidvalidity is not None and validity is not None and validity != uidvalidity:
            res["reset"] = True
            last_uid = 0
        if last_uid > 0:
            typ, data = conn.uid("SEARCH", None, f"UID {last_uid + 1}:*")
            uids = [u for u in _uids(data) if u > last_uid]
        else:
            since = _imap_date(now - timedelta(days=first_run_days))
            typ, data = conn.uid("SEARCH", None, f"SINCE {since}")
            uids = _uids(data)
        res["candidates"] = len(uids)
        if len(uids) > cap:
            if last_uid > 0:
                res["truncated"] = len(uids) - cap
                uids = uids[:cap]                       # oldest first; the rest next run
            else:
                uids = uids[-cap:]                      # first run: the newest `cap`
        for u in uids:
            try:
                typ, data = conn.uid("FETCH", str(u), "(BODY.PEEK[])")
                raw = _fetched_bytes(data) if typ == "OK" else None
            except Exception:
                raw = None
            if raw:
                res["messages"].append((u, raw))
        res["ok"] = True
        return res
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def vault_dir() -> str:
    try:
        from mdo_share_master import vault_dir as _vd
        return _vd()
    except Exception:
        return os.environ.get("VAULT_DIR", os.path.join(
            os.path.dirname(os.path.abspath(os.environ.get("VEGA_DB_PATH", "/data/vega_data.db"))), "vault"))


def store_files(parsed: dict, category: str, day: str, extra: dict[str, bytes] | None = None) -> tuple[str, list[str]]:
    """Write the attachments (and `extra` files) under <vault>/finance/mail/<date>_<category>_<safe-subject>/.
    Returns (relative dir, written file names); ('', []) when there was nothing to store."""
    files = [(a["name"], a["data"]) for a in parsed["attachments"] if a.get("data")]
    for name, data in (extra or {}).items():
        if data:
            files.append((safe_filename(name), data))
    if not files:
        return "", []
    rel_dir = f"{VAULT_AREA}/{day}_{category}_{safe_name(parsed['subject'])}"
    full_dir = os.path.join(vault_dir(), *rel_dir.split("/"))
    os.makedirs(full_dir, exist_ok=True)
    written = []
    for name, data in files:
        target = os.path.join(full_dir, name)
        stem, ext = os.path.splitext(name)
        n = 2
        while os.path.exists(target):                       # same mail re-stored or two parts with one name
            target = os.path.join(full_dir, f"{stem}_{n}{ext}")
            n += 1
        tmp = target + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, target)
        written.append(os.path.basename(target))
    return rel_dir, written


def _parse_now(v: Any) -> datetime:
    if isinstance(v, datetime):
        d = v
    elif v:
        try:
            d = datetime.fromisoformat(_query_tz(str(v).replace("Z", "+00:00")))
        except ValueError:
            d = datetime.now(IST)
    else:
        d = datetime.now(IST)
    return (d if d.tzinfo else d.replace(tzinfo=IST)).astimezone(IST)


# ═════════════════════════════════════════════════════════════════════════════
# Registration — tables, endpoints, the run the bot triggers
# ═════════════════════════════════════════════════════════════════════════════
def register(app, vdb: Callable[[], Awaitable[Any]], send_cos: Callable[[str], dict],
             tender_ingest: Callable[..., Awaitable[dict]] | None = None) -> dict:
    """Mount /api/mail/*. `send_cos` is the same function POST /api/cos/send wraps; `tender_ingest` is the tender
    door's body (mdo_cos_api.register()['tender_ingest']) so bidsnrfp results also land in the pipeline."""
    import asyncio

    async def ensure_schema(db=None):
        db = db if db is not None else await vdb()
        await db.executescript(SCHEMA)
        await db.commit()

    def _row(r) -> dict:
        d = dict(r)
        try:
            d["attachment_names"] = json.loads(d.get("attachment_names") or "[]")
        except ValueError:
            d["attachment_names"] = []
        d["attachment_locked"] = bool(d.get("attachment_locked"))
        d["actionable"] = bool(d.get("actionable"))
        d["sender"] = sender_label(d.get("from_addr") or "")
        return d

    async def state(mailbox: str) -> dict:
        db = await vdb()
        rows = await db.execute_fetchall("SELECT * FROM mail_state WHERE mailbox=?", (mailbox,))
        if rows:
            return dict(rows[0])
        return {"mailbox": mailbox, "last_uid": 0, "uidvalidity": None, "last_run_at": None, "last_line": "", "runs": 0}

    async def _audit(db, rel: str, nbytes: int, ok: bool, note: str = "") -> None:
        try:
            await db.execute("INSERT INTO vault_audit (action,path,bytes,actor,ok,note) VALUES (?,?,?,?,?,?)",
                             ("put", rel[:300], nbytes, BOT_ID, 1 if ok else 0, note[:200]))
        except Exception:
            pass                                             # the audit table belongs to the vault; never block intake

    async def store_one(db, uid: int, raw: bytes, now: datetime) -> dict | None:
        """Parse, categorise, store, insert. Returns the inserted row dict, or None when message_id already exists."""
        parsed = parse_message(raw, uid)
        dup = await db.execute_fetchall("SELECT id FROM mail_messages WHERE message_id=?", (parsed["message_id"],))
        if dup:
            return None
        category = categorise(parsed["from_addr"], parsed["subject"])
        info = describe(parsed, category)
        day = (datetime.fromisoformat(parsed["received_at"]).astimezone(IST) if parsed["received_at"] else now).strftime("%Y-%m-%d")
        extra = {}
        if category == "tender-result":
            if parsed["html"]:
                extra["body.html"] = parsed["html"].encode("utf-8", "replace")
            elif parsed["text"]:
                extra["body.txt"] = parsed["text"].encode("utf-8", "replace")
        rel, written = "", []
        try:
            rel, written = await asyncio.to_thread(store_files, parsed, category, day, extra)
            if rel:
                await _audit(db, rel, sum(len(a["data"]) for a in parsed["attachments"]), True, f"{len(written)} files")
        except Exception as e:
            await _audit(db, rel or VAULT_AREA, 0, False, redact(e)[:200])
            info["summary"] = (f"store failed: {redact(e)[:120]} · " + info["summary"])[:SUMMARY_MAX]
        await db.execute(
            "INSERT OR IGNORE INTO mail_messages (uid, message_id, from_addr, subject, received_at, category, entity_hint, "
            "attachment_names, attachment_locked, stored_path, summary, status, actionable) VALUES (?,?,?,?,?,?,?,?,?,?,?,'new',?)",
            (uid, parsed["message_id"], parsed["from_addr"], parsed["subject"], parsed["received_at"] or now.astimezone(timezone.utc).isoformat(),
             category, info["entity_hint"], json.dumps(info["attachment_names"]), 1 if info["locked"] else 0, rel,
             info["summary"], 1 if info["actionable"] else 0))
        rows = await db.execute_fetchall("SELECT * FROM mail_messages WHERE message_id=?", (parsed["message_id"],))
        row = _row(rows[0]) if rows else None
        if row is not None:
            row["tenders"] = info["tenders"]
        return row

    async def run(now_v: Any = None) -> dict:
        """One intake: UIDs above the watermark → store, categorise, count; one push when something actionable
        arrived; the heartbeat line always (Directive 5). Login failure is a warning line, not an exception."""
        now = _parse_now(now_v)
        cfg = config()
        stamp = now.astimezone(timezone.utc).isoformat()
        counts = {c: 0 for c in CATEGORIES}
        out: dict[str, Any] = {"as_of": now.isoformat(), "configured": cfg["configured"], "mailbox": cfg["folder"],
                               "new": 0, "dupes": 0, "locked": 0, "counts": counts, "actionable": [], "pushed": 0,
                               "push_failed": 0, "push": {}, "text": "", "tenders_posted": 0, "tenders": [],
                               "status": "clean", "line": "", "note": ""}
        db = await vdb()
        st = await state(cfg["folder"])
        if not cfg["configured"]:
            out["status"] = "warning"
            out["line"] = f"{BOT_ID}: {NOT_CONFIGURED} (GMAIL_IMAP_USER / GMAIL_APP_PASSWORD missing in .env)"
            await _save_state(db, cfg["folder"], st["last_uid"], st.get("uidvalidity"), stamp, out["line"])
            return out
        fetched = await asyncio.to_thread(fetch_new, cfg, int(st["last_uid"] or 0), st.get("uidvalidity"), now)
        if not fetched["ok"]:
            out["status"] = "warning"
            out["line"] = f"{BOT_ID}: {redact(fetched['reason'], cfg)}"
            await _save_state(db, cfg["folder"], st["last_uid"], st.get("uidvalidity"), stamp, out["line"])
            return out
        if fetched["reset"]:
            out["note"] = "UIDVALIDITY changed — watermark reset, re-read the last 7 days"
        new_rows, last_uid, failed = [], int(st["last_uid"] or 0), 0
        for uid, raw in fetched["messages"]:
            try:
                row = await store_one(db, uid, raw, now)
            except Exception as e:
                failed += 1
                out["note"] = (out["note"] + " · " if out["note"] else "") + f"uid {uid} not stored: {redact(e, cfg)[:80]}"
                continue                                     # named in the heartbeat line; not counted as new
            if row is None:
                out["dupes"] += 1
            else:
                new_rows.append(row)
                counts[row["category"]] = counts.get(row["category"], 0) + 1
                if row["attachment_locked"]:
                    out["locked"] += 1
            last_uid = max(last_uid, int(uid))
        await db.commit()
        out["new"], out["failed"] = len(new_rows), failed
        # bidsnrfp results → the tender pipeline (in-process door; nothing invented: title + result as the mail says)
        posted = 0
        for row in new_rows:
            if row["category"] != "tender-result" or not row.get("tenders"):
                continue
            items = [{"buyer": "", "title": t["title"], "category": "Tender result", "status": "result",
                      "source": "bidsnrfp", "url": t.get("url") or "",
                      "notes": (t.get("result") or t.get("line") or "")[:500]} for t in row["tenders"]]
            out["tenders"].extend(items)
            if tender_ingest is not None:
                try:
                    r = await tender_ingest(items, "bidsnrfp")
                    posted += int(r.get("added") or 0)
                except Exception as e:
                    out["note"] = (out["note"] + " · " if out["note"] else "") + f"tender door failed: {redact(e, cfg)[:80]}"
        grok_posted = 0
        for row in new_rows:                                 # Grok's [GROK-TENDER] table → the pipeline, source "grok"
            if row["category"] != "grok-tender" or not row.get("tenders"):
                continue
            items = [{"buyer": t["buyer"], "title": t["title"], "category": t["category"] or "Other", "due_date": t["due_date"],
                      "url": t["url"], "source": "grok",
                      "notes": " · ".join(x for x in (t["tender_id"] and f"ref {t['tender_id']}", t["value"] and f"value {t['value']}",
                                                      t["emd"] and f"EMD {t['emd']}", t["location"], t["eligibility"]) if x)[:500]}
                     for t in row["tenders"]]
            out["tenders"].extend(items)
            if tender_ingest is not None:
                try:
                    r = await tender_ingest(items, "grok")
                    grok_posted += int(r.get("added") or 0)
                except Exception as e:
                    out["note"] = (out["note"] + " · " if out["note"] else "") + f"tender door failed: {redact(e, cfg)[:80]}"
        out["tenders_posted"] = posted + grok_posted
        if out["tenders"] and tender_ingest is None:
            out["note"] = (out["note"] + " · " if out["note"] else "") + "tender door not wired — results stored only"
        # ONE WhatsApp line when something actionable arrived
        actionable = [r for r in new_rows if r["actionable"]]
        out["actionable"] = [{k: r[k] for k in ("id", "category", "from_addr", "subject", "attachment_locked", "summary")} for r in actionable]
        if actionable:
            text = push_text(actionable)
            out["text"] = text
            try:
                push = send_cos(text) or {}
            except Exception as e:
                push = {"sent": False, "reason": redact(e, cfg)[:200]}
            out["push"] = push
            if push.get("sent"):
                out["pushed"] = 1
                await db.execute(f"UPDATE mail_messages SET pushed_at=? WHERE id IN ({','.join('?' * len(actionable))})",
                                 [stamp] + [r["id"] for r in actionable])
            else:
                out["push_failed"] = 1
                out["status"] = "warning"
        line = heartbeat_line(counts, out["locked"])
        if fetched["truncated"]:
            line += f" · {fetched['truncated']} more next run"
        if actionable:
            line += " · 1 line pushed" if out["pushed"] else " · push NOT delivered"
        if posted:
            line += f" · {posted} tender result{'s' if posted != 1 else ''} → pipeline"
        if counts.get("grok-tender"):
            line += f" · Grok: {grok_posted} new tender{'s' if grok_posted != 1 else ''} → pipeline"
        if out["note"]:
            line += " · " + out["note"]
        out["line"] = line
        await _save_state(db, cfg["folder"], last_uid, fetched.get("uidvalidity"), stamp, line)
        return out

    async def _save_state(db, mailbox: str, last_uid: int, uidvalidity: int | None, stamp: str, line: str) -> None:
        await db.execute(
            "INSERT INTO mail_state (mailbox, last_uid, uidvalidity, last_run_at, last_line, runs) VALUES (?,?,?,?,?,1) "
            "ON CONFLICT(mailbox) DO UPDATE SET last_uid=excluded.last_uid, uidvalidity=excluded.uidvalidity, "
            "last_run_at=excluded.last_run_at, last_line=excluded.last_line, runs=mail_state.runs+1, updated_at=datetime('now')",
            (mailbox, int(last_uid or 0), uidvalidity, stamp, redact(line)[:1000]))
        await db.commit()

    async def recent(days: int = 7, category: str = "", status: str = "", limit: int = 200, now_v: Any = None) -> dict:
        days = max(1, min(int(days or 7), 400))
        now = _parse_now(now_v)
        since = (now.astimezone(timezone.utc) - timedelta(days=days)).isoformat()
        q, params = "SELECT * FROM mail_messages WHERE received_at >= ?", [since]
        if category:
            if category not in CATEGORIES:
                raise HTTPException(400, f"category must be one of {', '.join(CATEGORIES)}")
            q += " AND category=?"; params.append(category)
        if status:
            if status not in STATUSES:
                raise HTTPException(400, f"status must be one of {', '.join(STATUSES)}")
            q += " AND status=?"; params.append(status)
        q += " ORDER BY received_at DESC, id DESC LIMIT ?"; params.append(max(1, min(int(limit or 200), 1000)))
        db = await vdb()
        items = [_row(r) for r in await db.execute_fetchall(q, params)]
        return {"items": items, "count": len(items), "days": days, "category": category, "status": status,
                "as_of": now.isoformat()}

    async def ack(mid: int) -> dict:
        db = await vdb()
        rows = await db.execute_fetchall("SELECT * FROM mail_messages WHERE id=?", (int(mid),))
        if not rows:
            raise HTTPException(404, f"mail {mid} not found")
        await db.execute("UPDATE mail_messages SET status='ack', acked_at=datetime('now') WHERE id=?", (int(mid),))
        await db.commit()
        return {"ok": True, "id": int(mid), "status": "ack"}

    async def stats(days: int = 7, now_v: Any = None) -> dict:
        days = max(1, min(int(days or 7), 400))
        now = _parse_now(now_v)
        since = (now.astimezone(timezone.utc) - timedelta(days=days)).isoformat()
        db = await vdb()
        by: dict[str, dict] = {c: {"count": 0, "locked": 0, "actionable": 0, "new": 0} for c in CATEGORIES}
        for r in await db.execute_fetchall(
                "SELECT category, COUNT(*) AS n, SUM(attachment_locked) AS locked, SUM(actionable) AS act, "
                "SUM(CASE WHEN status='new' THEN 1 ELSE 0 END) AS fresh FROM mail_messages WHERE received_at >= ? GROUP BY category", (since,)):
            d = dict(r)
            by.setdefault(d["category"], {"count": 0, "locked": 0, "actionable": 0, "new": 0}).update(
                {"count": int(d["n"] or 0), "locked": int(d["locked"] or 0), "actionable": int(d["act"] or 0), "new": int(d["fresh"] or 0)})
        actionable = [_row(r) for r in await db.execute_fetchall(
            "SELECT * FROM mail_messages WHERE actionable=1 ORDER BY received_at DESC, id DESC LIMIT 10")]
        cfg = config()
        st = await state(cfg["folder"])
        return {"days": days, "as_of": now.isoformat(), "total": sum(v["count"] for v in by.values()),
                "locked": sum(v["locked"] for v in by.values()), "by_category": by, "categories": list(CATEGORIES),
                "actionable": actionable, "configured": cfg["configured"], "host": cfg["host"], "mailbox": cfg["folder"],
                "state": {"last_uid": int(st.get("last_uid") or 0), "last_run_at": st.get("last_run_at"),
                          "last_line": st.get("last_line") or "", "runs": int(st.get("runs") or 0)},
                "note": "" if cfg["configured"] else NOT_CONFIGURED}

    # ── endpoints ─────────────────────────────────────────────────────────────
    @app.get("/api/mail/recent")
    async def mail_recent(days: int = 7, category: str = "", status: str = "", limit: int = 200):
        return await recent(days, category, status, limit)

    @app.get("/api/mail/stats")
    async def mail_stats(days: int = 7):
        return await stats(days)

    @app.post("/api/mail/{mid}/ack")
    async def mail_ack(mid: int):
        return await ack(mid)

    @app.post("/api/mail/run")
    async def mail_run(body: dict | None = None):
        body = body or {}
        return await run(body.get("now"))

    return {"ensure_schema": ensure_schema, "run": run, "recent": recent, "ack": ack, "stats": stats, "state": state}
