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

# --- Read-only portfolio endpoints ---
HOLDINGS = "/portfolio/holdings"          # CONFIRMED by probe (returns sector_name, day_change)
PROFILE = "/user/profile"                 # CONFIRMED by probe
POSITIONS = "/portfolio/overall_positions"  # strong lead (real HDFC adapter) — confirm via probe
FUNDS = "/portfolio/funds"                # TO CONFIRM — none of the first guesses hit; see CANDIDATES

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
    "positions": [
        "/portfolio/overall_positions", "/portfolio/positions", "/portfolio/day_positions",
        "/positions", "/overall_positions", "/portfolio/net_positions",
    ],
    "funds": [
        "/portfolio/funds", "/user/funds", "/portfolio/limits", "/user/limits",
        "/funds", "/limits", "/margin", "/user/margin", "/funds/limits",
        "/portfolio/margin", "/portfolio/available_margin",
    ],
}
