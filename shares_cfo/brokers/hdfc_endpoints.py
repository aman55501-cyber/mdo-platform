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

import os

# --- Auth / token ---
LOGIN = "/login"                 # GET ?api_key=... (opened in browser)
ACCESS_TOKEN = "/access-token"   # POST ?api_key=&request_token=  body {"apiSecret": "..."}

# --- Order book (READ). HDFC's exact path isn't probe-confirmed yet, so try a few
# candidates and let HDFC_ORDERBOOK_PATH override once you've confirmed it. Following
# the same honest pattern as the write path: never claim success we didn't get. ---
ORDERBOOK_CANDIDATES = [p for p in [
    os.environ.get("HDFC_ORDERBOOK_PATH", "").strip(),
    "/orders", "/order-book", "/orders/book", "/portfolio/orders", "/order/book",
] if p]

# --- Read-only portfolio endpoints (all CONFIRMED against the live account + docs) ---
HOLDINGS = "/portfolio/holdings"            # returns sector_name, day_change, day_change_percentage
PROFILE = "/user/profile"
POSITIONS = "/portfolio/cumulative-positions"  # confirmed from ir-docs
FUNDS = "/user/margins"                     # HDFC's "Funds / Limits" == margins; confirmed from ir-docs
FETCH_LTP = "/fetch-ltp"                     # PUT {"data":[{"exchange","token"}]} -> ltp + prev_close

# How the access token is presented on each authenticated call.
# The probe reports which the API actually accepts; change this one constant.
#   "bearer" -> Authorization: Bearer <token>
#   "header" -> access-token: <token>
#   "query"  -> ?access_token=<token>
AUTH_STYLE = "bearer"

# Candidate paths the probe will try for each concept. Confirmed paths first.
CANDIDATES = {
    "holdings": ["/portfolio/holdings"],  # confirmed
    "profile": ["/user/profile"],         # confirmed
    "positions": ["/portfolio/cumulative-positions"],  # confirmed
    "funds": ["/user/margins"],                          # confirmed
}
