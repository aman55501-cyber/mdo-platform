"""Shared test setup. The suite drives mdo_server through FastAPI's TestClient without an app key: a sandbox that
exports MDO_AUTH_TOKEN (the CoS cloud environment does) would otherwise turn every endpoint call into a 401 and
the suite into dozens of KeyErrors (seen 2026-10-09: 29 failures here, 144/144 inside the VPS image). Blank it
before any test module imports mdo_server; a test that wants the lock sets mdo_server.MDO_AUTH_TOKEN itself.
"""
import os

os.environ["MDO_AUTH_TOKEN"] = ""
# mail-reader tests fake imaplib; a real mailbox must never be reached from the suite
os.environ["GMAIL_IMAP_USER"] = ""
os.environ["GMAIL_APP_PASSWORD"] = ""
