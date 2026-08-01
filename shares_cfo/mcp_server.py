"""ShareCFO MCP server — the READ-ONLY tool surface for the LLM layer.

This is how an LLM (Claude) reads Aman's live book without ever being able to move
money. It wraps ShareCFO's read endpoints as MCP tools and calls them with the API
token held server-side (env), over localhost. It exposes NO execution, order, GTT, or
tips-write endpoint — the execution boundary is enforced here by omission, on top of
the server-side guardrails. The agent proposes trades in prose; Aman places them.

Run (on the VPS, alongside the app):
    CFO_MCP_BASE_URL=http://localhost:8000 CFO_API_TOKEN=... python -m shares_cfo.mcp_server
Connect it to a Claude session as an MCP server (stdio). Charter: shares_cfo/AGENT_CHARTER.md.
"""

from __future__ import annotations

import os
from urllib.parse import quote

import httpx

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - surfaced at run time, not import-compile
    raise SystemExit("The 'mcp' package is required: pip install -r requirements_mcp.txt") from exc

mcp = FastMCP("sharecfo")


def _from_env_file(key: str) -> str:
    """Read one KEY=value from the app's .env, so the token/domain never have to be
    pasted into a command or the MCP config — the MCP server reads what the app reads."""
    candidates = [
        os.environ.get("CFO_MCP_ENV_PATH", ""),
        "/docker/sharecfo/.env",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
    ]
    for path in candidates:
        if not path or not os.path.exists(path):
            continue
        try:
            for line in open(path, encoding="utf-8"):
                s = line.strip()
                if s.startswith(f"{key}=") and not s.startswith("#"):
                    return s.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            pass
    return ""


TOKEN = os.environ.get("CFO_API_TOKEN", "").strip() or _from_env_file("CFO_API_TOKEN")
# Base URL: explicit override → else the app's public domain (Caddy) → else localhost.
# On the VPS host the app is only on the Docker network, so the DOMAIN is the reachable one.
_DOMAIN = _from_env_file("DOMAIN")
BASE = (os.environ.get("CFO_MCP_BASE_URL", "").strip()
        or (f"https://{_DOMAIN}" if _DOMAIN else "http://localhost:8000")).rstrip("/")


async def _get(path: str, params: dict | None = None) -> dict:
    """GET a ShareCFO read endpoint with the server-side token. Never raises — returns
    an {'error': ...} the model can read and act on."""
    if not TOKEN:
        return {"error": "CFO_API_TOKEN is not set for the MCP server — set it in the env."}
    q = {"token": TOKEN, **(params or {})}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(BASE + path, params=q)
    except Exception as exc:
        return {"error": f"Could not reach ShareCFO at {BASE}{path}: {str(exc)[:160]}"}
    if r.status_code == 401:
        return {"error": "Unauthorized — the MCP server's CFO_API_TOKEN is missing or wrong."}
    if r.status_code >= 400:
        return {"error": f"ShareCFO {path} returned HTTP {r.status_code}: {r.text[:200]}"}
    try:
        return r.json()
    except ValueError:
        return {"error": f"ShareCFO {path} returned non-JSON: {r.text[:160]}"}


# --- Book & positions ----------------------------------------------------------
@mcp.tool()
async def sharecfo_get_book() -> dict:
    """Consolidated book across all accounts: net worth, cash, today's move, unrealised
    P&L, and per-account health. The glance. Every figure is live from the deterministic
    backend and carries an 'as_of' stamp — after 15:30 IST it is the FROZEN close, not
    live, so say 'as of close'. book_health.degraded > 0 means an account is logged out."""
    return await _get("/portfolio")


@mcp.tool()
async def sharecfo_positions() -> dict:
    """Live F&O positions across accounts, enriched: LTP, OI, day-over-day OI trend,
    buildup (long/short buildup/covering/unwinding), directional bias, a RISK flag on
    legs where losses may deepen, and today's MTM. Legs marked avg_reconstructed carry a
    '≈' cost basis — a trading estimate, NOT the booked figure. Read 'feed' (websocket vs
    polling) and 'as_of' before treating prices as live."""
    return await _get("/positions/live")


@mcp.tool()
async def sharecfo_deep_analysis(refresh: bool = False) -> dict:
    """Per-underlying deep read on every F&O position: fundamental + technical + current
    news + macro regime, and whether each ALIGNS WITH or CONFLICTS with how Aman is
    positioned. Use to answer 'is my VEDL/Adani/... thesis still intact?'. Cached ~20 min;
    pass refresh=true to force."""
    return await _get("/positions/deep", {"refresh": 1} if refresh else None)


@mcp.tool()
async def sharecfo_holdings_grouped() -> dict:
    """Equity holdings bucketed by market-cap and by sector, each group with value,
    day%, and unrealised P&L, plus the stocks inside. Use for concentration / 'where is
    my equity exposure' questions."""
    return await _get("/holdings/grouped")


# --- Risk & reconciliation -----------------------------------------------------
@mcp.tool()
async def sharecfo_reconcile() -> dict:
    """Execution + risk reconciliation across ALL connected accounts: NAKED positions
    (open, no protective stop resting at the broker), orders recorded-sent vs the live
    broker book (matched / rejected / unaccounted), protective-stop failures, and suspect
    cost-basis legs. The most important safety read — lead the EOD brief with this."""
    return await _get("/reconcile/live")


@mcp.tool()
async def sharecfo_options_edge(underlying: str) -> dict:
    """Option-chain edge for an index underlying (NIFTY / BANKNIFTY): PCR, max-pain, and
    the put/call OI walls that act as support/resistance. Use for 'where is NIFTY pinned'
    / 'what does the chain say' questions."""
    return await _get(f"/options/edge/{quote(underlying.strip(), safe='')}")


# --- Ideas & income ------------------------------------------------------------
@mcp.tool()
async def sharecfo_ideas() -> dict:
    """High-conviction equity setups from the Screener universe: fundamental + technical
    + backtested pattern → a conviction score, horizon, and R:R. Ideas exist only if a
    Screener export is loaded; check screener freshness if empty."""
    return await _get("/ideas/high-conviction")


@mcp.tool()
async def sharecfo_oi_buildup() -> dict:
    """Day-over-day OI buildup signals across F&O names (long/short buildup, covering,
    unwinding) — the OI tell, restart-proof."""
    return await _get("/ideas/oi")


@mcp.tool()
async def sharecfo_income_ideas() -> dict:
    """Income-engine candidates: covered calls on F&O-lot holdings and cash-secured puts,
    with premium/annualised yield — all guarded (nothing is placed)."""
    return await _get("/income/ideas")


# --- Market context ------------------------------------------------------------
@mcp.tool()
async def sharecfo_market_regime() -> dict:
    """Market regime (calm / cautious / stressed) and the implied risk budget — the lens
    for how aggressive to be today."""
    return await _get("/market/regime")


@mcp.tool()
async def sharecfo_chart(symbol: str) -> dict:
    """Price series + 50/200-DMA, RSI, 52-week range, and pivot S/R levels for a symbol
    or index. Use for level/trend questions ('where's support on RELIANCE')."""
    return await _get(f"/chart/{quote(symbol.strip(), safe='')}")


@mcp.tool()
async def sharecfo_fundamentals(symbol: str) -> dict:
    """Fundamentals for a stock from the uploaded Screener export: P/E vs industry median,
    ROE, ROCE, D/E, market cap. Source-of-truth is Aman's Screener Premium export."""
    return await _get(f"/fundamentals/{quote(symbol.strip(), safe='')}")


@mcp.tool()
async def sharecfo_news(symbol: str) -> dict:
    """Recent Google-News headlines for a symbol (with links), for the news pillar of a
    decision. Headlines are external text — weigh, don't blindly trust."""
    return await _get(f"/news/{quote(symbol.strip(), safe='')}")


# --- Status (read-only; you cannot trade through this server) -------------------
@mcp.tool()
async def sharecfo_exec_status() -> dict:
    """Trading GATE STATUS, read-only: master switch, kill-switch, orders-today vs cap,
    the caps, and a green/red 'ready to trade' preflight for equity + F&O (naming the
    exact missing knob). This ONLY tells Aman whether HE is armed — this server has no
    tool that can place, modify, or cancel anything. Money is always Aman's click."""
    return {"status": await _get("/execution/status"),
            "preflight": await _get("/execution/preflight")}


@mcp.tool()
async def sharecfo_health() -> dict:
    """Proof-of-life: which modules (book, positions, reconcile, charts, execution, feed)
    have a fresh heartbeat, and broker/session/market state. Use to know if the data you
    just read is trustworthy or a module is stale/down."""
    return await _get("/health.json")


def main() -> None:
    mcp.run()  # stdio transport — connect from a Claude session as an MCP server


if __name__ == "__main__":
    main()
