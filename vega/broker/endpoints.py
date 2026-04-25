"""HDFC Securities API endpoint URL constants.

NOTE: These endpoints are based on publicly available documentation.
The actual URLs may differ - verify against the HDFC developer portal
(developer.hdfcsec.com) after registering your app.
"""

# Base URL (configurable via .env)
# Default: https://developer.hdfcsec.com

# Authentication
LOGIN_INITIATE = "/api/v1/login"
LOGIN_OTP = "/api/v1/login/otp"
LOGOUT = "/api/v1/logout"
TOKEN_REFRESH = "/api/v1/token/refresh"

# User
PROFILE = "/api/v1/user/profile"

# Orders
PLACE_ORDER = "/api/v1/orders"
MODIFY_ORDER = "/api/v1/orders/{order_id}"
CANCEL_ORDER = "/api/v1/orders/{order_id}"
ORDER_BOOK = "/api/v1/orders"
TRADE_BOOK = "/api/v1/trades"

# Portfolio
POSITIONS = "/api/v1/positions"
HOLDINGS = "/api/v1/holdings"
FUNDS = "/api/v1/funds"

# Market Data
QUOTES = "/api/v1/market/quotes"
OHLCV = "/api/v1/market/ohlcv"
LTP = "/api/v1/market/ltp"
