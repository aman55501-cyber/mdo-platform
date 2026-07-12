"""HDFC Securities OApi endpoint paths + auth style.

=========================== READ THIS BEFORE EDITING ===========================
The paths below are BEST-GUESS starting points, NOT gospel. They were written
from convention. `scripts/probe_hdfc.py` runs against the LIVE API on your PC,
reports which paths actually return 200 and what JSON they return, and this file
is corrected from that output. Do not trust these until the probe confirms them.

VERIFIED facts (from HDFC docs — trusted over convention):
  * base URL includes /oapi/v1               (see config.DEFAULT_BASE_URL)
  * a User-Agent header is MANDATORY          (see config.get_user_agent)
  * access token is obtained via /access-token (see scripts/hdfc_login.py)
================================================================================
"""

from __future__ import annotations

# --- Auth / token ---
LOGIN = "/login"                 # GET ?api_key=... (opened in browser)
ACCESS_TOKEN = "/access-token"   # POST ?api_key=&request_token=  body {"apiSecret": "..."}

# --- Read-only portfolio endpoints (probe corrects these) ---
HOLDINGS = "/holdings"
POSITIONS = "/positions"
FUNDS = "/limits"                # HDFC labels this "Funds / Limits"
PROFILE = "/profile"

# How the access token is presented on each authenticated call.
# The probe reports which the API actually accepts; change this one constant.
#   "bearer" -> Authorization: Bearer <token>
#   "header" -> access-token: <token>
#   "query"  -> ?access_token=<token>
AUTH_STYLE = "bearer"

# Candidate paths the probe will try for each concept if the primary 404s.
CANDIDATES = {
    "holdings": ["/holdings", "/portfolio/holdings", "/demat/holdings", "/portfolio"],
    "positions": ["/positions", "/portfolio/positions", "/positions/day", "/netpositions"],
    "funds": ["/limits", "/funds", "/margin", "/funds/limits", "/user/limits"],
    "profile": ["/profile", "/user/profile", "/customer/profile", "/me"],
}
