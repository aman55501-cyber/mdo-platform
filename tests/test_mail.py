"""mail-reader — IMAP intake of statements, contract notes and tender results, rule-based, zero LLM spend.

Aman, chat 2026-10-09 (A26 C1). Nothing here touches the network: imaplib.IMAP4_SSL is a fake holding synthetic
.eml messages, the WhatsApp send is canned, the vault is a temp dir. Follows tests/test_compliance.py: a scratch
VEGA_DB_PATH is set before mdo_server is imported; the endpoint tests wipe the mail tables (the DB is shared by
every test module). The password used here is a fixture and must never appear in a line, a reply or a file name.
"""
from __future__ import annotations

import imaplib
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))
os.environ.setdefault("SHARE_MASTER_DATA_DIR", tempfile.mkdtemp())

import yaml  # noqa: E402
from pypdf import PdfWriter  # noqa: E402

import mdo_agent as ag  # noqa: E402
import mdo_mail as mm  # noqa: E402
from mdo_cos import IST  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOT = {"id": "mail-reader", "provider": "none", "model": "none"}
USER = "aman.55501@gmail.com"
PASSWORD = "abcd-efgh-ijkl-mnop"          # a fixture, never a real app password
NOW = datetime(2026, 10, 9, 9, 30, tzinfo=IST)

BIDSNRFP_HTML = """<html><body><p>Dear Vedanta Washery And Logistic Solutions,</p>
<p>Here are the new tender results where you participated.</p>
<table>
<tr><th>S.No</th><th>Tender Name</th><th>Organisation</th><th>Result</th></tr>
<tr><td>1</td><td><a href="https://bidsnrfp.com/t/101">Coal washing of 2 MTPA at Korba</a></td><td>SECL</td><td>Awarded to L1 - M/s ABC Washeries</td></tr>
<tr><td>2</td><td><a href="https://bidsnrfp.com/t/102">RCR of coal from Dipka siding</a></td><td>NTPC</td><td>Technically qualified, financial bid opened</td></tr>
</table>
<p>Regards,<br>Team BidsNRFP</p><p>Unsubscribe here</p></body></html>"""


def _pdf(encrypted: bool) -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=72, height=72)
    if encrypted:
        w.encrypt("ABCDE1234F")          # a PAN-shaped fixture, not a real PAN
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _eml(from_: str, subject: str, text: str = "", html: str = "", attachments=(), when: datetime | None = None,
         message_id: str | None = None) -> bytes:
    m = EmailMessage()
    m["From"] = from_
    m["To"] = USER
    m["Subject"] = subject
    m["Date"] = format_datetime((when or NOW).astimezone(timezone.utc))
    m["Message-ID"] = message_id or f"<{abs(hash((from_, subject))) % 10**8}@fixture>"
    m.set_content(text or " ")
    if html:
        m.add_alternative(html, subtype="html")
    for name, data, maintype, subtype in attachments:
        m.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return m.as_bytes()


def fixtures() -> dict[int, bytes]:
    """Six synthetic mails, five categories, one encrypted PDF, one bidsnrfp HTML body."""
    return {
        101: _eml("HDFC securities <edocs@hdfcsec.com>", "Contract Note for 08-Oct-2026 - AMAN AGRAWAL",
                  "Please find the contract note attached.", attachments=[("CN_08102026.pdf", _pdf(False), "application", "pdf")],
                  when=NOW - timedelta(hours=20)),
        102: _eml("Angel One <donotreply@angelone.in>", "DP Transaction Cum Holding Statement - A1504046",
                  "Client: ADITI INVESTMENTS. The PDF is protected with your PAN.",
                  attachments=[("DP_Holding_A1504046.pdf", _pdf(True), "application", "pdf")], when=NOW - timedelta(hours=10)),
        103: _eml("South Indian Bank <alerts@sib.bank.in>", "Your account statement for Sep 2026",
                  "Statement attached, password protected.", attachments=[("Statement_Sep2026.pdf", _pdf(True), "application", "pdf")],
                  when=NOW - timedelta(hours=6)),
        104: _eml("BidsNRFP <admin@bidsnrfp.com>", "(2) New Tender Results : Participation Insights",
                  "Open in a browser.", html=BIDSNRFP_HTML, when=NOW - timedelta(hours=3)),
        105: _eml("KFintech <donotreply@kfintech.com>", "SIP confirmation - Folio 12345 - ASHOK KUMAR AGRAWAL",
                  "Your SIP of Rs 5000 was processed.", when=NOW - timedelta(hours=2)),
        106: _eml("NSE Alerts <nse_alerts@nse.co.in>", "Funds/Securities Balance as on 08-Oct-2026",
                  "Balance confirmation from your trading member.", when=NOW - timedelta(hours=1)),
    }


class FakeIMAP:
    """Enough of imaplib.IMAP4_SSL for fetch_new: login, read-only select, UIDVALIDITY, uid SEARCH / FETCH, logout."""
    instances: list["FakeIMAP"] = []

    def __init__(self, host: str, messages: dict[int, bytes] | None = None, uidvalidity: int = 7, password: str = PASSWORD):
        self.host, self.messages, self.uidvalidity, self.password = host, dict(messages or {}), uidvalidity, password
        self.calls, self.readonly, self.logged_out = [], None, False
        FakeIMAP.instances.append(self)

    def login(self, user, pw):
        if user != USER or pw != self.password:
            raise imaplib.IMAP4.error(f"b'[AUTHENTICATIONFAILED] Invalid credentials (Failure)' for {user} / {pw}")
        return "OK", [b"Logged in"]

    def select(self, folder, readonly=False):
        self.readonly, self.folder = readonly, folder
        return "OK", [str(len(self.messages)).encode()]

    def response(self, code):
        return code, [str(self.uidvalidity).encode()] if code == "UIDVALIDITY" else [None]

    def uid(self, cmd, *args):
        self.calls.append((cmd,) + args)
        if cmd == "SEARCH":
            crit = args[-1]
            uids = sorted(self.messages)
            m = re.match(r"UID (\d+):\*", crit)
            if m:
                lo = int(m.group(1))
                hit = [u for u in uids if u >= lo] or uids[-1:]     # the IMAP quirk: n:* always returns the last message
                return "OK", [" ".join(str(u) for u in hit).encode()]
            return "OK", [" ".join(str(u) for u in uids).encode()]
        if cmd == "FETCH":
            u = int(args[0])
            raw = self.messages.get(u)
            if raw is None:
                return "NO", [None]
            return "OK", [(f"{u} (UID {u} BODY[] {{{len(raw)}}}".encode(), raw), b")"]
        raise AssertionError(cmd)

    def logout(self):
        self.logged_out = True
        return "BYE", [b""]


# ── pure: categories, entities, locks, parsing ───────────────────────────────
def test_categorise_by_sender_and_subject_never_guesses():
    assert mm.categorise("nse_alerts@nse.co.in", "Funds/Securities Balance as on 08-Oct-2026") == "exchange-balance"
    assert mm.categorise("info@bseindia.in", "Funds/Securities Balance") == "exchange-balance"
    assert mm.categorise("edocs@hdfcsec.com", "Contract Note for 08-Oct-2026") == "contract-note"
    assert mm.categorise("edocs@hdfcsec.com", "Consolidated Statement Sep 2026") == "broker-statement"
    assert mm.categorise("contract.notes@angeltrade.in", "Contract Note - A1504046") == "contract-note"
    assert mm.categorise("donotreply@angelone.in", "Margin Statement") == "broker-statement"
    assert mm.categorise("donotreply@angelone.in", "DP Transaction Cum Holding") == "broker-statement"
    assert mm.categorise("donotreply@angelone.in", "Register of Securities & Funds") == "broker-statement"
    assert mm.categorise("alerts@sib.bank.in", "Your account statement for Sep 2026") == "bank-statement"
    assert mm.categorise("admin@bidsnrfp.com", "(3) New Tender Results : Participation Insights") == "tender-result"
    assert mm.categorise("admin@bidsnrfp.com", "Welcome to BidsNRFP") == "other"
    assert mm.categorise("donotreply@kfintech.com", "SIP confirmation") == "mf-transaction"
    assert mm.categorise("do-not-reply@camsonline.com", "Monthly portfolio disclosure") == "mf-transaction"
    assert mm.categorise("custcomm@services.hdfcergo.com", "Policy renewal") == "insurance"
    assert mm.categorise("donotreply.evoting@cdslindia.co.in", "e-Voting notice") == "evoting"
    # an unknown sender is never guessed into a category, whatever the subject says
    assert mm.categorise("someone@example.com", "Contract Note / Bank Statement / Tender Results") == "other"
    assert mm.categorise("", "") == "other"
    # the actionable set: tender results, bank statements, broker HOLDING statements only
    assert mm.is_actionable("tender-result", "x") and mm.is_actionable("bank-statement", "x")
    assert mm.is_actionable("broker-statement", "DP Transaction Cum Holding")
    assert mm.is_actionable("broker-statement", "Register of Securities & Funds")
    assert not mm.is_actionable("broker-statement", "Margin Statement")
    assert not mm.is_actionable("contract-note", "Contract Note") and not mm.is_actionable("mf-transaction", "SIP")


def test_entity_hint_exact_matches_only():
    assert mm.entity_hint("Statement for ADITI INVESTMENTS (A1504046)") == "ADITI INVESTMENTS"
    assert mm.entity_hint("Dear Aman Agrawal,", "Ashok Kumar Agrawal") == "AMAN AGRAWAL; ASHOK KUMAR AGRAWAL"
    assert mm.entity_hint("Vedanta Washery And Logistic Solutions") == "VEDANTA WASHERY"
    assert mm.entity_hint("Amanda Agrawalla", "Aditi", "Vedanta Ltd") == ""      # partial / similar names never count
    assert mm.sender_label("alerts@sib.bank.in") == "SIB" and mm.sender_label("x@bidsnrfp.com") == "bidsnrfp"
    assert mm.sender_label("Angel <donotreply@angelone.in>") == "Angel One" and mm.sender_label("a@b.example") == "b.example"


def test_locked_pdf_detected_never_opened_and_parse_message():
    assert mm.is_locked_pdf(_pdf(True)) is True
    assert mm.is_locked_pdf(_pdf(False)) is False
    assert mm.is_locked_pdf(b"not a pdf") is False and mm.is_locked_pdf(b"") is False
    raw = fixtures()[102]
    p = mm.parse_message(raw, 102)
    assert p["from_addr"] == "donotreply@angelone.in" and p["subject"].startswith("DP Transaction Cum Holding")
    assert p["message_id"].startswith("<") and p["received_at"].endswith("+00:00")
    assert [a["name"] for a in p["attachments"]] == ["DP_Holding_A1504046.pdf"]
    d = mm.describe(p, "broker-statement")
    assert d["locked"] and d["summary"].startswith(mm.LOCKED_SUMMARY) and d["actionable"]
    assert d["entity_hint"] == "ADITI INVESTMENTS" and d["attachment_names"] == ["DP_Holding_A1504046.pdf"]
    assert "ABCDE1234F" not in json.dumps(d)                      # the fixture PAN is nowhere in the output
    # safe names for the vault folder and the files
    assert mm.safe_name("(2) New Tender Results : Participation Insights") == "2_New_Tender_Results_Participation_Insights"
    assert mm.safe_filename("../../etc/passwd") == "passwd" and mm.safe_filename("") == "attachment"


def test_bidsnrfp_html_parsed_into_rows_and_a_short_summary():
    rows = mm.parse_tender_html(BIDSNRFP_HTML)
    assert [r["title"] for r in rows] == ["Coal washing of 2 MTPA at Korba", "RCR of coal from Dipka siding"]
    assert rows[0]["result"] == "Awarded to L1 - M/s ABC Washeries" and rows[0]["url"] == "https://bidsnrfp.com/t/101"
    assert rows[1]["result"].startswith("Technically qualified")
    s = mm.tender_summary(rows)
    assert s.startswith("2 tender results: ") and "Awarded to L1" in s and len(s) <= mm.SUMMARY_MAX and "<" not in s
    assert mm.parse_tender_html("<p>Dear Aman,</p><p>Regards</p>") == []
    assert len(mm.tender_summary([], "x" * 2000)) == mm.SUMMARY_MAX


def test_push_and_heartbeat_text():
    rows = [{"category": "tender-result", "from_addr": "admin@bidsnrfp.com", "attachment_locked": 0},
            {"category": "tender-result", "from_addr": "admin@bidsnrfp.com", "attachment_locked": 0},
            {"category": "bank-statement", "from_addr": "alerts@sib.bank.in", "attachment_locked": 1}]
    assert mm.push_text(rows) == "Mail: 2 tender results (bidsnrfp), 1 SIB bank statement (locked) — see Morning › Mail"
    assert mm.push_text([{"category": "broker-statement", "from_addr": "donotreply@angelone.in", "attachment_locked": 1}]) == \
        "Mail: 1 Angel One holding statement (locked) — see Morning › Mail"
    zero = {c: 0 for c in mm.CATEGORIES}
    assert mm.heartbeat_line(zero, 0) == "mail-reader: 0 new (tender 0, broker 0, bank 0, mf 0, other 0), 0 locked — IMAP ok"
    counts = dict(zero, **{"tender-result": 1, "contract-note": 1, "broker-statement": 1, "exchange-balance": 1,
                           "bank-statement": 1, "mf-transaction": 1, "evoting": 1})
    assert mm.heartbeat_line(counts, 2) == "mail-reader: 7 new (tender 1, broker 3, bank 1, mf 1, other 1), 2 locked — IMAP ok"


def test_config_and_redact_never_expose_the_password(monkeypatch):
    monkeypatch.setenv("GMAIL_IMAP_USER", USER)
    monkeypatch.setenv("GMAIL_APP_PASSWORD", PASSWORD)
    monkeypatch.delenv("GMAIL_IMAP_HOST", raising=False)
    monkeypatch.delenv("MAIL_READER_FOLDER", raising=False)
    cfg = mm.config()
    assert cfg["configured"] and cfg["host"] == "imap.gmail.com" and cfg["folder"] == "INBOX"
    assert mm.redact(f"login failed for {USER} with {PASSWORD}", cfg) == "login failed for [redacted] with [redacted]"
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "")
    assert mm.config()["configured"] is False


# ── fetch_new against the fake IMAP ──────────────────────────────────────────
def test_fetch_new_first_run_then_watermark_then_login_failure(monkeypatch):
    msgs = fixtures()
    box = {"imap": None}

    def factory(host):
        box["imap"] = FakeIMAP(host, msgs)
        return box["imap"]
    monkeypatch.setattr(imaplib, "IMAP4_SSL", factory)
    cfg = {"user": USER, "password": PASSWORD, "host": "imap.gmail.com", "folder": "INBOX", "configured": True}
    res = mm.fetch_new(cfg, 0, None, NOW)
    assert res["ok"] and [u for u, _ in res["messages"]] == [101, 102, 103, 104, 105, 106] and res["uidvalidity"] == 7
    assert box["imap"].readonly is True and box["imap"].logged_out
    assert box["imap"].calls[0] == ("SEARCH", None, "SINCE 02-Oct-2026")
    assert all(c[2] == "(BODY.PEEK[])" for c in box["imap"].calls if c[0] == "FETCH")
    # above the watermark: the IMAP "n:*" quirk (always returns the last message) is filtered out
    res = mm.fetch_new(cfg, 106, 7, NOW)
    assert res["ok"] and res["messages"] == [] and res["candidates"] == 0
    res = mm.fetch_new(cfg, 104, 7, NOW)
    assert [u for u, _ in res["messages"]] == [105, 106]
    # cap: oldest first, the rest next run
    res = mm.fetch_new(cfg, 101, 7, NOW, cap=2)
    assert [u for u, _ in res["messages"]] == [102, 103] and res["truncated"] == 3
    # first run cap keeps the newest
    res = mm.fetch_new(cfg, 0, None, NOW, cap=2)
    assert [u for u, _ in res["messages"]] == [105, 106]
    # UIDVALIDITY changed → reset, re-read from the start
    res = mm.fetch_new(cfg, 106, 3, NOW)
    assert res["reset"] and len(res["messages"]) == 6
    # wrong password: reported, redacted, never raised
    bad = dict(cfg, password="wrong-pass-0000")
    res = mm.fetch_new(bad, 0, None, NOW)
    assert not res["ok"] and res["reason"].startswith("IMAP login failed: ") and "AUTHENTICATIONFAILED" in res["reason"]
    assert "wrong-pass-0000" not in res["reason"] and USER not in res["reason"]


# ── endpoints + the run ──────────────────────────────────────────────────────
def _client():
    from fastapi.testclient import TestClient
    import mdo_server
    return TestClient(mdo_server.app)


def _wipe():
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    for t in ("mail_messages", "mail_state"):
        db.execute(f"DELETE FROM {t}")
    db.execute("DELETE FROM vwlr_tender_pipeline WHERE notes LIKE '[bidsnrfp]%'")
    db.commit(); db.close()


class _Sent:
    def __init__(self):
        self.texts, self.ok = [], True

    def __call__(self, text, to=None, legacy_send=None):
        self.texts.append(text)
        return {"sent": self.ok} if self.ok else {"sent": False, "reason": "bridge down"}


def _setup(monkeypatch, messages=None, password=PASSWORD):
    import mdo_server
    c = _client()
    c.get("/api/mail/stats")                   # opens the DB and creates the tables
    _wipe()
    sent = _Sent()
    monkeypatch.setitem(mdo_server._cos, "send_cos", sent)
    monkeypatch.setenv("GMAIL_IMAP_USER", USER)
    monkeypatch.setenv("GMAIL_APP_PASSWORD", password)
    monkeypatch.setenv("VAULT_DIR", tempfile.mkdtemp())
    msgs = messages if messages is not None else fixtures()
    fakes = []

    def factory(host):
        f = FakeIMAP(host, msgs)
        fakes.append(f)
        return f
    monkeypatch.setattr(imaplib, "IMAP4_SSL", factory)
    return c, sent, msgs, fakes


def test_run_stores_categorises_locks_pushes_once_and_heartbeats_zero_next_time(monkeypatch):
    c, sent, msgs, fakes = _setup(monkeypatch)
    r = c.post("/api/mail/run", json={"now": NOW.isoformat()}).json()
    assert r["configured"] and r["status"] == "clean" and r["new"] == 6 and r["dupes"] == 0 and r["locked"] == 2
    assert r["counts"] == {"broker-statement": 1, "contract-note": 1, "exchange-balance": 1, "bank-statement": 1,
                           "tender-result": 1, "mf-transaction": 1, "insurance": 0, "evoting": 0, "grok-tender": 0, "other": 0}
    # the one line: tender result + bank statement (locked) + Angel holding statement (locked)
    assert r["pushed"] == 1 and sent.texts == [
        "Mail: 1 tender result (bidsnrfp), 1 SIB bank statement (locked), 1 Angel One holding statement (locked) — see Morning › Mail"]
    assert r["line"] == ("mail-reader: 6 new (tender 1, broker 3, bank 1, mf 1, other 0), 2 locked — IMAP ok"
                         " · 1 line pushed · 2 tender results → pipeline")
    assert r["tenders_posted"] == 2 and len(r["tenders"]) == 2 and r["tenders"][0]["source"] == "bidsnrfp"
    # the vault: attachments under finance/mail/<date>_<category>_<safe-subject>/, tender body kept, locked PDF untouched
    vault = os.environ["VAULT_DIR"]
    rows = c.get("/api/mail/recent?days=7").json()
    assert rows["count"] == 6 and [x["uid"] for x in rows["items"]] == [106, 105, 104, 103, 102, 101]
    by = {x["uid"]: x for x in rows["items"]}
    assert by[102]["stored_path"] == "finance/mail/2026-10-08_broker-statement_DP_Transaction_Cum_Holding_Statement_-_A1504046"
    assert os.path.exists(os.path.join(vault, by[102]["stored_path"], "DP_Holding_A1504046.pdf"))
    assert by[102]["attachment_locked"] and by[102]["summary"].startswith(mm.LOCKED_SUMMARY) and by[102]["entity_hint"] == "ADITI INVESTMENTS"
    assert by[103]["attachment_locked"] and by[103]["actionable"] and by[103]["pushed_at"]
    assert by[101]["category"] == "contract-note" and not by[101]["attachment_locked"] and not by[101]["actionable"]
    assert by[101]["entity_hint"] == "AMAN AGRAWAL" and by[101]["pushed_at"] is None
    assert by[104]["summary"].startswith("2 tender results: ") and "Awarded to L1" in by[104]["summary"]
    assert os.path.exists(os.path.join(vault, by[104]["stored_path"], "body.html"))
    assert by[104]["entity_hint"] == "VEDANTA WASHERY"
    assert by[105]["category"] == "mf-transaction" and by[105]["stored_path"] == "" and by[105]["entity_hint"] == "ASHOK KUMAR AGRAWAL"
    assert by[106]["category"] == "exchange-balance" and by[106]["sender"] == "NSE"
    # the tender pipeline got the two results through the door's body (source bidsnrfp, status result)
    pipe = [t for t in c.get("/api/vwlr/pipeline").json()["tenders"] if t["notes"].startswith("[bidsnrfp]")]
    assert len(pipe) == 2 and all(t["status"] == "result" for t in pipe) and pipe[0]["url"].startswith("https://bidsnrfp.com/t/")
    # the Message-IDs decide: the same six mails under new UIDs are dupes, not new rows
    msgs[201], msgs[202] = msgs[101], msgs[104]
    r2 = c.post("/api/mail/run", json={"now": (NOW + timedelta(minutes=30)).isoformat()}).json()
    assert r2["new"] == 0 and r2["dupes"] == 2 and r2["pushed"] == 0 and len(sent.texts) == 1
    assert r2["line"] == "mail-reader: 0 new (tender 0, broker 0, bank 0, mf 0, other 0), 0 locked — IMAP ok"
    assert c.get("/api/mail/recent?days=7").json()["count"] == 6
    # the watermark moved: only UIDs above it are searched
    assert fakes[-1].calls[0] == ("SEARCH", None, "UID 107:*")
    st = c.get("/api/mail/stats?days=7").json()
    assert st["state"]["last_uid"] == 202 and st["state"]["runs"] == 2 and st["configured"] and st["total"] == 6 and st["locked"] == 2
    assert st["by_category"]["broker-statement"] == {"count": 1, "locked": 1, "actionable": 1, "new": 1}
    assert [x["uid"] for x in st["actionable"]] == [104, 103, 102]
    # a quiet mailbox: the empty heartbeat, nothing pushed
    r3 = c.post("/api/mail/run", json={"now": (NOW + timedelta(hours=1)).isoformat()}).json()
    assert r3["new"] == 0 and r3["dupes"] == 0 and r3["line"].endswith("0 locked — IMAP ok") and len(sent.texts) == 1
    assert fakes[-1].calls[0] == ("SEARCH", None, "UID 203:*")
    # ack takes a row off the actionable list's open state
    a = c.post(f"/api/mail/{by[103]['id']}/ack").json()
    assert a == {"ok": True, "id": by[103]["id"], "status": "ack"}
    assert c.get("/api/mail/recent?days=7&category=bank-statement&status=ack").json()["count"] == 1
    assert c.get("/api/mail/recent?days=7&category=nope").status_code == 400
    assert c.post("/api/mail/999999/ack").status_code == 404
    # the password is in no reply and no stored line
    blob = json.dumps([r, r2, r3, rows, st])
    assert PASSWORD not in blob and "ABCDE1234F" not in blob


def test_push_failure_is_a_warning_and_the_next_run_does_not_repeat(monkeypatch):
    c, sent, msgs, _ = _setup(monkeypatch, {103: fixtures()[103]})
    sent.ok = False
    r = c.post("/api/mail/run", json={"now": NOW.isoformat()}).json()
    assert r["new"] == 1 and r["pushed"] == 0 and r["push_failed"] == 1 and r["status"] == "warning"
    assert r["line"].endswith("1 locked — IMAP ok · push NOT delivered") and r["text"].startswith("Mail: 1 SIB bank statement (locked)")
    assert c.get("/api/mail/recent?days=7").json()["items"][0]["pushed_at"] is None


def test_not_configured_and_login_failure_report_without_crashing_or_credentials(monkeypatch):
    c, sent, _, _ = _setup(monkeypatch, {})
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "")
    r = c.post("/api/mail/run", json={"now": NOW.isoformat()}).json()
    assert r["configured"] is False and r["status"] == "warning" and r["new"] == 0 and sent.texts == []
    assert r["line"] == "mail-reader: IMAP not configured (GMAIL_IMAP_USER / GMAIL_APP_PASSWORD missing in .env)"
    assert c.get("/api/mail/stats").json()["note"] == mm.NOT_CONFIGURED
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "wrong-pass-0000")
    r = c.post("/api/mail/run", json={"now": NOW.isoformat()}).json()
    assert r["status"] == "warning" and r["line"].startswith("mail-reader: IMAP login failed: ") and "AUTHENTICATIONFAILED" in r["line"]
    assert "wrong-pass-0000" not in json.dumps(r) and USER not in r["line"]
    st = c.get("/api/mail/stats").json()
    assert st["state"]["runs"] == 2 and "wrong-pass-0000" not in json.dumps(st)


def test_run_mail_reader_heartbeats_every_run_and_logs_no_credential(monkeypatch, capsys):
    c, sent, msgs, _ = _setup(monkeypatch)
    hb = []
    monkeypatch.setattr(ag, "heartbeat", lambda bot, cad, status, summary, checks=None: hb.append((bot, cad, status, summary)))

    def fake_api(path, method="GET", body=None, timeout=30):
        assert path == "/api/mail/run" and method == "POST"
        r = c.post(path, json=body)
        assert r.status_code == 200
        return r.json()
    monkeypatch.setattr(ag, "api", fake_api)
    monkeypatch.setattr(ag, "RUN_ARGS", [])
    assert ag.run_mail_reader(BOT, "none", "hourly", now=NOW) == 0
    assert hb[-1][0] == "mail-reader" and hb[-1][2] == "clean" and hb[-1][3].startswith("mail-reader: 6 new (tender 1, broker 3, bank 1, mf 1, other 0), 2 locked — IMAP ok")
    assert ag.run_mail_reader(BOT, "none", "hourly", now=NOW + timedelta(minutes=30)) == 0
    assert hb[-1][3] == "mail-reader: 0 new (tender 0, broker 0, bank 0, mf 0, other 0), 0 locked — IMAP ok"
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "wrong-pass-0000")
    assert ag.run_mail_reader(BOT, "none", "hourly", now=NOW + timedelta(hours=1)) == 0
    assert hb[-1][2] == "warning" and hb[-1][3].startswith("mail-reader: IMAP login failed: ")
    out = capsys.readouterr().out + json.dumps(hb)
    assert PASSWORD not in out and "wrong-pass-0000" not in out and "ABCDE1234F" not in out
    assert "mail-reader pushed: Mail: 1 tender result (bidsnrfp)" in out
    # the dispatcher knows the bot
    assert ag.CUSTOM_BOTS["mail-reader"] is ag.run_mail_reader


# ── wiring: fleet.yaml, cron, .env.example, the Morning card ──────────────────
def test_fleet_cron_env_and_morning_card_wiring():
    fleet = yaml.safe_load(open(os.path.join(ROOT, "fleet.yaml"), encoding="utf-8"))
    bot = next(b for b in fleet["bots"] if b["id"] == "mail-reader")
    assert bot["provider"] == "none" and bot["model"] == "none" and bot["enabled"] is True
    assert bot["cadence"].startswith("every 30 min 07:00-22:00 IST") and "22:30 IST" in bot["cadence"]
    assert "IMAP ok" in bot["heartbeat"] and "IMAP not configured" in bot["heartbeat"] and "IMAP login failed" in bot["heartbeat"]
    assert bot["objective"] == ("every statement, note and tender result lands in the vault the day it arrives; "
                                "Aman hears only about the actionable ones")
    assert set(bot["serves"]) <= {o["id"] for o in yaml.safe_load(open(os.path.join(ROOT, "agenda.yaml"), encoding="utf-8"))["objectives"]}
    assert any("No LLM" in r for r in bot["charter"]["rules"]) and any("password" in r for r in bot["charter"]["rules"])
    doc = open(os.path.join(ROOT, "DEPLOY_HOSTINGER.md"), encoding="utf-8").read()
    block = doc[doc.index("# MDO fleet — one line per bot"):]
    block = block[:block.index("```")]
    lines = [l for l in block.splitlines() if "mdo_agent.py mail-reader" in l]
    assert len(lines) == 3
    assert lines[0].startswith("30 1    * * *") and lines[1].startswith("*/30 2-16 * * *") and lines[2].startswith("0  17   * * *")
    env = open(os.path.join(ROOT, ".env.example"), encoding="utf-8").read()
    assert "\nGMAIL_IMAP_USER=\n" in env and "\nGMAIL_APP_PASSWORD=\n" in env
    assert "\nGMAIL_IMAP_HOST=imap.gmail.com\n" in env and "\nMAIL_READER_FOLDER=INBOX\n" in env
    assert env.index("# ── Chief of Staff") < env.index("GMAIL_IMAP_USER=")        # deploy_vps.sh appends from that block
    assert "GMAIL_APP_PASSWORD" not in open(os.path.join(ROOT, "mdo_mail.py"), encoding="utf-8").read().split("def config")[1].split("def redact")[0].replace(
        'os.environ.get("GMAIL_APP_PASSWORD", "")', "")       # the only read is the one env lookup
    page_path = os.path.join(ROOT, "mdo-app", "app", "morning", "page.tsx")
    if not os.path.exists(page_path):            # the backend image ships no frontend source; checked in the repo run
        return
    page = open(page_path, encoding="utf-8").read()
    assert "<MailCard />" in page and "function MailCard()" in page and "api.mail.stats(7)" in page
    assert "q.isLoading && <div" in page.split("function MailCard()")[1]     # loading state before any table (Directive 17)
    api_ts = open(os.path.join(ROOT, "mdo-app", "lib", "api.ts"), encoding="utf-8").read()
    assert "/api/mail/stats?days=" in api_ts and "/api/mail/${id}/ack" in api_ts and "/api/mail/recent?days=" in api_ts


GROK_BODY = """[GROK-TENDER] buyer|title|tender id|category|publish|closing|value|EMD|eligibility|location|URL
SECL|Operation & maintenance of coal washery, 2.5 MTPA, Korba|SECL/GM/2026/W/41|Coal washing|01-10-2026|28-10-2026|Rs 1,250 Crore|Rs 2 Cr|Class A washery experience|Korba|https://www.secl-cil.in/t/w41.pdf
WCL|RCR transportation Umrer OC|WCL/RCR/9|RCR|2 Oct 2026|2026-11-05|Rs 40 Crore||5 yrs RCR|Nagpur|https://tender247.com/x/9
WCL|RCR transportation Umrer OC|WCL/RCR/9|RCR|2 Oct 2026|2026-11-05|Rs 40 Crore||5 yrs RCR|Nagpur|https://tender247.com/x/9
|||
not a table line
"""


def test_grok_tender_table_is_parsed_and_only_trusted_senders_count(monkeypatch):
    rows = mm.parse_grok_tenders(GROK_BODY)
    assert [(r["buyer"], r["tender_id"], r["due_date"]) for r in rows] == [
        ("SECL", "SECL/GM/2026/W/41", "2026-10-28"), ("WCL", "WCL/RCR/9", "2026-11-05")]      # header, duplicate, junk skipped
    assert rows[0]["url"] == "https://www.secl-cil.in/t/w41.pdf" and rows[0]["value"] == "Rs 1,250 Crore" and rows[1]["emd"] == ""
    assert mm.parse_grok_tenders("[GROK-TENDER] NONE FOUND") == [] and mm.parse_grok_tenders("") == []
    monkeypatch.setenv("GMAIL_IMAP_USER", "aman.55501@gmail.com")
    assert mm.categorise("Grok <noreply@x.ai>", "[GROK-TENDER] 10 Oct") == "grok-tender"
    assert mm.categorise("Aman <aman.55501@gmail.com>", "Fwd: [GROK-TENDER] 10 Oct") == "grok-tender"
    assert mm.categorise("Mallory <m@evil.example>", "[GROK-TENDER] 10 Oct") == "other"       # cannot feed the pipeline
    d = mm.describe({"subject": "[GROK-TENDER]", "text": GROK_BODY, "html": "", "attachments": [], "from_addr": "x"}, "grok-tender")
    assert d["actionable"] is True and d["summary"].startswith("2 tenders from Grok: SECL — Operation")
    empty = mm.describe({"subject": "[GROK-TENDER]", "text": "NONE FOUND", "html": "", "attachments": [], "from_addr": "x"}, "grok-tender")
    assert empty["actionable"] is False and empty["summary"] == "Grok: NONE FOUND"


def test_grok_email_flows_into_the_pipeline_with_one_push_and_a_heartbeat(monkeypatch):
    msgs = {201: _eml("Grok <noreply@x.ai>", "[GROK-TENDER] 2026-10-09", GROK_BODY, when=NOW - timedelta(hours=1)),
            202: _eml("Mallory <m@evil.example>", "[GROK-TENDER] 2026-10-09", GROK_BODY, when=NOW - timedelta(hours=1)),
            203: _eml("Grok <noreply@x.ai>", "[GROK-TENDER] 2026-10-08", "NONE FOUND", when=NOW - timedelta(hours=30))}
    c, sent, _, _ = _setup(monkeypatch, messages=msgs)
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    db.execute("DELETE FROM vwlr_tender_pipeline WHERE notes LIKE '[grok]%'"); db.commit(); db.close()
    r = c.post("/api/mail/run", json={"now": NOW.isoformat()}).json()
    assert r["counts"]["grok-tender"] == 2 and r["counts"]["other"] == 1          # the stranger's mail is just "other"
    assert r["tenders_posted"] == 2 and "Grok: 2 new tenders → pipeline" in r["line"] and ", grok 2" in r["line"]
    assert sent.texts == ["Mail: 1 Grok tender list — see Morning › Mail"]         # the NONE FOUND mail is not actionable
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    rows = db.execute("SELECT buyer, due_date, url, notes FROM vwlr_tender_pipeline WHERE notes LIKE '[grok]%' ORDER BY buyer").fetchall()
    db.close()
    assert [(b, d) for b, d, _, _ in rows] == [("SECL", "2026-10-28"), ("WCL", "2026-11-05")]
    assert "ref SECL/GM/2026/W/41" in rows[0][3] and "Korba" in rows[0][3] and rows[1][2] == "https://tender247.com/x/9"
    # a second run adds nothing: the mails are stored, the tenders are duplicates
    r2 = c.post("/api/mail/run", json={"now": NOW.isoformat()}).json()
    assert r2["new"] == 0 and r2["tenders_posted"] == 0
