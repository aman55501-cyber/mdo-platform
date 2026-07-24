#!/usr/bin/env python3
"""CFO MCP Server — Model Context Protocol bridge to the ANS MDO platform.

This exposes the ANS MDO backend (the FastAPI service in ``mdo_server.py``,
deployed at ``CFO_MCP_BASE_URL``) to any MCP client — Claude Desktop, Claude
Code, Cursor, etc. — as a focused set of tools. It lets an assistant read and
act on the business cockpit: intelligence items, operations tasks, compliance
filings, the VWLR coal-washery CRM (leads, tenders, bid maths), the Aditi
investment pools, hotel occupancy, live market data and the daily briefing.

The server is a thin, stateless HTTP client. It holds no data of its own — every
tool call is proxied to the backend. It runs locally over stdio.

Configuration (environment variables):
    CFO_MCP_BASE_URL   Base URL of the deployed MDO backend.
                       Default: https://srv1641037.hstgr.cloud
    CFO_API_TOKEN      Optional bearer token. When the backend is started with
                       CFO_API_TOKEN set, it requires this token on every
                       /api request; the value here is sent as
                       ``Authorization: Bearer <token>``. Leave unset if the
                       backend has no token configured.
    CFO_MCP_TIMEOUT    Per-request timeout in seconds. Default: 30.

Run:
    pip install -r requirements_mcp.txt
    export CFO_API_TOKEN=...          # optional, only if the backend requires it
    export CFO_MCP_BASE_URL=https://srv1641037.hstgr.cloud
    python cfo_mcp_server.py
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field
from mcp.server.fastmcp import FastMCP

# ── configuration ────────────────────────────────────────────────────────────
BASE_URL = os.environ.get("CFO_MCP_BASE_URL", "https://srv1641037.hstgr.cloud").rstrip("/")
API_TOKEN = os.environ.get("CFO_API_TOKEN", "").strip()
TIMEOUT = float(os.environ.get("CFO_MCP_TIMEOUT", "30"))

mcp = FastMCP("cfo_mcp")


# ── shared HTTP helpers ──────────────────────────────────────────────────────
def _headers() -> dict[str, str]:
    """Build request headers, attaching the bearer token when configured."""
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"
    return headers


async def _request(
    method: str,
    path: str,
    *,
    params: Optional[dict[str, Any]] = None,
    json_body: Optional[dict[str, Any]] = None,
) -> Any:
    """Proxy a single request to the MDO backend and return parsed JSON.

    Args:
        method: HTTP verb ("GET", "POST", "PUT", "DELETE").
        path: API path beginning with "/" (e.g. "/api/intel").
        params: Optional query-string parameters. None values are dropped.
        json_body: Optional JSON request body for POST/PUT.

    Returns:
        The decoded JSON response (dict or list), or the raw text under a
        {"raw": ...} wrapper when the response is not JSON.
    """
    clean_params = {k: v for k, v in (params or {}).items() if v is not None}
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.request(
            method,
            path,
            params=clean_params or None,
            json=json_body,
            headers=_headers(),
        )
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text}


def _handle_error(e: Exception) -> str:
    """Turn an exception into an actionable, agent-readable error string."""
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 401:
            return (
                "Error: Unauthorized (401). The backend requires an API token. "
                "Set CFO_API_TOKEN in this MCP server's environment to the value "
                "configured on the backend."
            )
        if code == 404:
            return "Error: Not found (404). Check the id/path is correct."
        if code == 422:
            return f"Error: Validation failed (422): {e.response.text[:300]}"
        if code == 429:
            return "Error: Rate limited (429). Wait before retrying."
        if code >= 500:
            return f"Error: Backend error ({code}). The MDO server may be down or a DB is missing."
        return f"Error: Request failed with status {code}: {e.response.text[:300]}"
    if isinstance(e, httpx.ConnectError):
        return (
            f"Error: Cannot reach the MDO backend at {BASE_URL}. "
            "Check CFO_MCP_BASE_URL and that the server is running."
        )
    if isinstance(e, httpx.TimeoutException):
        return f"Error: Request to {BASE_URL} timed out after {TIMEOUT:.0f}s."
    return f"Error: Unexpected {type(e).__name__}: {e}"


def _dump(data: Any) -> str:
    """Serialize a JSON-compatible value to a compact, readable string."""
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


# ── input models ─────────────────────────────────────────────────────────────
class _Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class IntelFilter(_Base):
    urgency: Optional[str] = Field(
        default=None, description="Filter by urgency: CRITICAL, HIGH, MEDIUM or LOW."
    )
    category: Optional[str] = Field(
        default=None, description="Filter by category, e.g. 'market', 'compliance', 'ops'."
    )
    status: Optional[str] = Field(
        default=None, description="Filter by status: open, acknowledged, snoozed or resolved."
    )


class AddIntel(_Base):
    title: str = Field(..., description="Short headline for the intel item.", min_length=1, max_length=300)
    body: str = Field(default="", description="Full detail / context for the item.", max_length=5000)
    urgency: str = Field(default="MEDIUM", description="CRITICAL, HIGH, MEDIUM or LOW.")
    category: str = Field(default="market", description="Category, e.g. 'market', 'compliance', 'ops'.")
    entity: str = Field(default="", description="Related entity/company name, if any.")
    source: str = Field(default="mcp", description="Where this item came from.")
    due_date: Optional[str] = Field(default=None, description="Optional due date, ISO 'YYYY-MM-DD'.")


class ItemId(_Base):
    item_id: int = Field(..., description="Numeric id of the intel item.", ge=1)


class TaskFilter(_Base):
    status: Optional[str] = Field(default=None, description="Filter by status: open, in_progress, done.")
    category: Optional[str] = Field(default=None, description="Filter by category.")


class AddTask(_Base):
    title: str = Field(..., description="Task title.", min_length=1, max_length=300)
    description: str = Field(default="", description="Task detail.", max_length=5000)
    entity: str = Field(default="", description="Related entity/company.")
    assigned_to: str = Field(default="Aman", description="Who owns the task.")
    priority: str = Field(default="medium", description="critical, high, medium or low.")
    category: str = Field(default="general", description="Task category.")
    due_date: Optional[str] = Field(default=None, description="Optional due date, ISO 'YYYY-MM-DD'.")


class UpdateTask(_Base):
    task_id: int = Field(..., description="Numeric id of the task to update.", ge=1)
    title: Optional[str] = Field(default=None, description="New title.")
    description: Optional[str] = Field(default=None, description="New description.")
    status: Optional[str] = Field(default=None, description="New status: open, in_progress, done.")
    priority: Optional[str] = Field(default=None, description="New priority.")
    assigned_to: Optional[str] = Field(default=None, description="New owner.")
    due_date: Optional[str] = Field(default=None, description="New due date, ISO 'YYYY-MM-DD'.")


class ComplianceFilter(_Base):
    entity: Optional[str] = Field(default=None, description="Filter by entity name.")
    status: Optional[str] = Field(default=None, description="Filter by status: overdue, pending, filed.")


class UpdateCompliance(_Base):
    filing_id: int = Field(..., description="Numeric id of the compliance filing.", ge=1)
    status: Optional[str] = Field(default=None, description="New status. 'filed' auto-stamps filed_on.")
    notes: Optional[str] = Field(default=None, description="Notes to attach.")
    assigned_to: Optional[str] = Field(default=None, description="Reassign to person.")
    due_date: Optional[str] = Field(default=None, description="New due date, ISO 'YYYY-MM-DD'.")


class LeadFilter(_Base):
    priority: Optional[str] = Field(default=None, description="Filter by priority: High, Medium or Low.")


class AddLead(_Base):
    company: str = Field(..., description="Prospect company name.", min_length=1, max_length=200)
    contact_person: str = Field(default="", description="Primary contact name.")
    phone: str = Field(default="", description="Contact phone.")
    location: str = Field(default="", description="Location / city.")
    distance_km: float = Field(default=0, description="Distance from VWLR washery in km.", ge=0)
    potential_volume: str = Field(default="", description="Estimated coal volume (free text).")
    priority: str = Field(default="Medium", description="High, Medium or Low.")
    status: str = Field(default="prospect", description="Pipeline status.")
    next_followup: Optional[str] = Field(default=None, description="Next follow-up date, ISO 'YYYY-MM-DD'.")
    notes: str = Field(default="", description="Free-text notes.")


class LogInteraction(_Base):
    company: str = Field(..., description="Company the interaction was with.", min_length=1, max_length=200)
    lead_id: Optional[int] = Field(default=None, description="Related lead id, if known.", ge=1)
    contact: str = Field(default="", description="Person spoken to.")
    type: str = Field(default="call", description="Interaction type: call, meeting, email, whatsapp.")
    notes: str = Field(default="", description="What was discussed.", max_length=5000)
    outcome: str = Field(default="", description="Result / next step.")
    follow_up_date: Optional[str] = Field(default=None, description="Follow-up date, ISO 'YYYY-MM-DD'.")


class PipelineFilter(_Base):
    status: Optional[str] = Field(default=None, description="Filter by status: active, evaluating, closed.")


class AddTender(_Base):
    buyer: str = Field(..., description="Tender buyer / issuing body.", min_length=1, max_length=200)
    volume_mt: float = Field(default=0, description="Coal volume in metric tonnes.", ge=0)
    category: str = Field(default="Other", description="Tender category, e.g. 'RCR', 'Loading', 'Rakes'.")
    due_date: Optional[str] = Field(default=None, description="Submission deadline, ISO 'YYYY-MM-DD'.")
    status: str = Field(default="active", description="Pipeline status.")
    url: str = Field(default="", description="Tender document / portal URL.")
    notes: str = Field(default="", description="Notes.")
    eligibility_score: float = Field(default=0.8, description="Fit score 0-1.", ge=0, le=1)


class BidInput(_Base):
    buyer: str = Field(..., description="Buyer name.", min_length=1, max_length=200)
    volume: float = Field(..., description="Volume in metric tonnes.", gt=0)
    route: str = Field(..., description="Rail route origin: RAIGARH, BILASPUR, RAIPUR, NAGPUR or MUMBAI.")
    gate_price: float = Field(..., description="Coal gate price per tonne (INR).", gt=0)


class Symbol(_Base):
    symbol: str = Field(
        ..., description="Yahoo Finance symbol, e.g. 'COALINDIA.NS', 'RELIANCE.NS'.", min_length=1
    )


class NewsFilter(_Base):
    tickers: Optional[str] = Field(
        default=None, description="Comma-separated tickers, e.g. 'RELIANCE,HDFCBANK'. Omit for defaults."
    )


class AlertFilter(_Base):
    level: Optional[str] = Field(default=None, description="Filter by level: critical, important, info.")
    domain: Optional[str] = Field(default=None, description="Filter by domain, e.g. 'market', 'compliance'.")


class HotelDays(_Base):
    days: int = Field(default=7, description="Number of most-recent days to return.", ge=1, le=90)


class GrokAsk(_Base):
    question: str = Field(..., description="Natural-language question for the Grok assistant.", min_length=1)


class RawRequest(_Base):
    method: str = Field(default="GET", description="HTTP method: GET, POST, PUT or DELETE.")
    path: str = Field(..., description="API path beginning with '/api', e.g. '/api/aditi/pools'.", min_length=1)
    params: Optional[dict[str, Any]] = Field(default=None, description="Optional query params.")
    body: Optional[dict[str, Any]] = Field(default=None, description="Optional JSON body for POST/PUT.")


# ── read tools ───────────────────────────────────────────────────────────────
@mcp.tool(
    name="cfo_status",
    annotations={"title": "Platform status", "readOnlyHint": True, "openWorldHint": True},
)
async def cfo_status() -> str:
    """Get the MDO platform status: current IST time, whether the NSE market is
    open, broker auth state, active positions and the trading watchlist.

    Returns: JSON with keys time, market, broker_authenticated,
    active_positions, watchlist. Use this as a quick health/context check.
    """
    try:
        return _dump(await _request("GET", "/api/status"))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_daily_briefing",
    annotations={"title": "Daily intelligence briefing", "readOnlyHint": True, "openWorldHint": True},
)
async def cfo_daily_briefing() -> str:
    """Return today's structured intelligence briefing, grouped by level
    (critical / important / info) with a per-level count summary.

    This is the best single starting point for "what needs my attention today".
    If the result is empty, call cfo_run_intelligence_scan first, then retry.

    Returns: JSON with keys generated_at, critical[], important[], info[], summary.
    """
    try:
        return _dump(await _request("GET", "/api/intelligence/briefing"))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_list_intel",
    annotations={"title": "List intelligence items", "readOnlyHint": True, "openWorldHint": True},
)
async def cfo_list_intel(params: IntelFilter) -> str:
    """List intelligence items (news, signals, reminders) newest-first, ordered
    by urgency. Optionally filter by urgency, category and status.

    Args: params.urgency, params.category, params.status (all optional).
    Returns: JSON {"items": [...]} — each item has id, urgency, category,
    entity, title, body, status, due_date, created_at.
    """
    try:
        data = await _request(
            "GET", "/api/intel",
            params={"urgency": params.urgency, "category": params.category, "status": params.status},
        )
        return _dump(data)
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_list_tasks",
    annotations={"title": "List operations tasks", "readOnlyHint": True, "openWorldHint": True},
)
async def cfo_list_tasks(params: TaskFilter) -> str:
    """List operations tasks ordered by priority then due date. Optionally
    filter by status and category.

    Args: params.status, params.category (both optional).
    Returns: JSON {"tasks": [...]} — id, title, description, entity,
    assigned_to, priority, status, category, due_date.
    """
    try:
        data = await _request(
            "GET", "/api/ops/tasks", params={"status": params.status, "category": params.category}
        )
        return _dump(data)
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_list_compliance",
    annotations={"title": "List compliance filings", "readOnlyHint": True, "openWorldHint": True},
)
async def cfo_list_compliance(params: ComplianceFilter) -> str:
    """List statutory/compliance filings across ANS Group entities, ordered
    overdue → pending → filed, then by due date. Filter by entity or status.

    Args: params.entity, params.status (both optional).
    Returns: JSON {"filings": [...]} — id, entity_name, filing_type,
    due_date, status, assigned_to, filed_on, notes.
    """
    try:
        data = await _request(
            "GET", "/api/compliance/filings",
            params={"entity": params.entity, "status": params.status},
        )
        return _dump(data)
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_list_entities",
    annotations={"title": "List ANS Group entities", "readOnlyHint": True, "openWorldHint": True},
)
async def cfo_list_entities() -> str:
    """List the legal entities under ANS Group (companies, LLPs, HUF, etc.)
    with their registration and status details.

    Returns: JSON {"entities": [...]} — name, entity_type, business,
    location, status, pan, gstin, cin, annual_turnover, notes.
    """
    try:
        return _dump(await _request("GET", "/api/entities"))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_aditi_pools",
    annotations={"title": "Aditi investment pools", "readOnlyHint": True, "openWorldHint": True},
)
async def cfo_aditi_pools() -> str:
    """List the Aditi Investments capital pools with current value, target
    allocation and instruments.

    Returns: JSON {"pools": [...]} — pool_code, current_value,
    target_allocation, instruments, notes.
    """
    try:
        return _dump(await _request("GET", "/api/aditi/pools"))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_list_leads",
    annotations={"title": "List VWLR CRM leads", "readOnlyHint": True, "openWorldHint": True},
)
async def cfo_list_leads(params: LeadFilter) -> str:
    """List VWLR coal-washery CRM leads, ordered by priority then tender score.
    Optionally filter by priority.

    Args: params.priority (optional): High, Medium or Low.
    Returns: JSON {"leads": [...]} — id, company, contact_person, phone,
    location, distance_km, potential_volume, priority, status, next_followup.
    """
    try:
        data = await _request("GET", "/api/vwlr/leads", params={"priority": params.priority})
        return _dump(data)
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_list_followups",
    annotations={"title": "VWLR leads due for follow-up", "readOnlyHint": True, "openWorldHint": True},
)
async def cfo_list_followups() -> str:
    """List VWLR leads whose next follow-up is due within the next 3 days
    (soonest first). Use this to plan today's outreach.

    Returns: JSON {"leads": [...]} with the same shape as cfo_list_leads.
    """
    try:
        return _dump(await _request("GET", "/api/vwlr/followups"))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_tender_pipeline",
    annotations={"title": "VWLR tender pipeline", "readOnlyHint": True, "openWorldHint": True},
)
async def cfo_tender_pipeline(params: PipelineFilter) -> str:
    """List the internal VWLR tender pipeline (tenders being tracked / bid on),
    ordered active → evaluating → closed then by due date. Filter by status.

    Args: params.status (optional).
    Returns: JSON {"tenders": [...]} — id, buyer, volume_mt, category,
    due_date, status, url, eligibility_score, notes.
    """
    try:
        data = await _request("GET", "/api/vwlr/pipeline", params={"status": params.status})
        return _dump(data)
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_calc_bid",
    annotations={"title": "Calculate VWLR coal bid", "readOnlyHint": True, "openWorldHint": False},
)
async def cfo_calc_bid(params: BidInput) -> str:
    """Compute a suggested VWLR coal bid: landed cost (gate price + FOIS rail
    freight for the route), a volume discount, a 4% margin haircut, the
    resulting bid price, margin % and total revenue/margin for the volume.

    Args: params.buyer, params.volume (MT), params.route (rail origin),
    params.gate_price (INR/tonne).
    Returns: JSON with fois_freight, landed_cost, volume_discount_pct,
    suggested_bid, margin_pct, total_revenue, total_margin.
    """
    try:
        data = await _request(
            "GET", "/api/vwlr/bid",
            params={
                "buyer": params.buyer,
                "volume": params.volume,
                "route": params.route,
                "gate_price": params.gate_price,
            },
        )
        return _dump(data)
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_hotel_daily",
    annotations={"title": "Hotel daily performance", "readOnlyHint": True, "openWorldHint": True},
)
async def cfo_hotel_daily(params: HotelDays) -> str:
    """Return recent daily performance for Hotel ANS International — occupancy,
    room rate, F&B and total revenue — in chronological order.

    Args: params.days (default 7): number of most-recent days.
    Returns: JSON {"records": [...]} — date, occupied, total_rooms,
    occupancy_pct, rate, room_revenue, fnb_revenue, total_revenue.
    """
    try:
        return _dump(await _request("GET", "/api/hotel/daily", params={"days": params.days}))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_market_watchlist",
    annotations={"title": "Watchlist quotes", "readOnlyHint": True, "openWorldHint": True},
)
async def cfo_market_watchlist() -> str:
    """Fetch live quotes for the full business-context watchlist (coal/power/
    steel/rail names plus portfolio holdings), each annotated with why it
    matters to ANS Group.

    Returns: JSON {"watchlist": [...]} — ticker, name, context, cmp,
    change, change_pct, 52w_low, 52w_high, volume.
    """
    try:
        return _dump(await _request("GET", "/api/market/watchlist"))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_market_indices",
    annotations={"title": "Market indices", "readOnlyHint": True, "openWorldHint": True},
)
async def cfo_market_indices() -> str:
    """Fetch key index levels: Nifty 50, Bank Nifty, USD/INR, Nasdaq, Dow Jones.

    Returns: JSON {"indices": [...]} — label, value, change, change_pct.
    """
    try:
        return _dump(await _request("GET", "/api/market/indices"))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_market_quote",
    annotations={"title": "Single stock quote", "readOnlyHint": True, "openWorldHint": True},
)
async def cfo_market_quote(params: Symbol) -> str:
    """Fetch a live quote for one symbol from Yahoo Finance.

    Args: params.symbol — e.g. 'COALINDIA.NS', 'RELIANCE.NS'.
    Returns: JSON — symbol, cmp, prev_close, change, change_pct,
    52w_low, 52w_high, market_cap, volume.
    """
    try:
        return _dump(await _request("GET", f"/api/market/quote/{params.symbol}"))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_portfolio_news",
    annotations={"title": "Portfolio news", "readOnlyHint": True, "openWorldHint": True},
)
async def cfo_portfolio_news(params: NewsFilter) -> str:
    """Return recent news headlines for portfolio tickers (fetched from Yahoo
    Finance RSS). Optionally scope to specific tickers.

    Args: params.tickers (optional) — comma-separated, e.g. 'RELIANCE,HDFCBANK'.
    Returns: JSON {"news": [...], "tickers": [...]} — each item has ticker,
    title, link, published, fetched_at, read.
    """
    try:
        return _dump(await _request("GET", "/api/news/portfolio", params={"tickers": params.tickers}))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_intelligence_alerts",
    annotations={"title": "Unacknowledged alerts", "readOnlyHint": True, "openWorldHint": True},
)
async def cfo_intelligence_alerts(params: AlertFilter) -> str:
    """List unacknowledged intelligence alerts, most-urgent first. Optionally
    filter by level and domain.

    Args: params.level (critical/important/info), params.domain (both optional).
    Returns: JSON {"alerts": [...]} — id, level, domain, title, detail, created_at.
    """
    try:
        data = await _request(
            "GET", "/api/intelligence/alerts",
            params={"level": params.level, "domain": params.domain},
        )
        return _dump(data)
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


# ── write / action tools ─────────────────────────────────────────────────────
@mcp.tool(
    name="cfo_add_intel",
    annotations={"title": "Add intelligence item", "readOnlyHint": False, "destructiveHint": False},
)
async def cfo_add_intel(params: AddIntel) -> str:
    """Create a new intelligence item (a note, alert or reminder) on the board.

    Args: params.title (required), plus optional body, urgency, category,
    entity, source, due_date.
    Returns: JSON of the created item including its new id.
    """
    try:
        return _dump(await _request("POST", "/api/intel", json_body=params.model_dump()))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_resolve_intel",
    annotations={
        "title": "Resolve intelligence item",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
    },
)
async def cfo_resolve_intel(params: ItemId) -> str:
    """Mark an intelligence item as resolved.

    Args: params.item_id — the numeric id (from cfo_list_intel).
    Returns: JSON of the updated item.
    """
    try:
        return _dump(await _request("POST", f"/api/intel/{params.item_id}/resolve"))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_add_task",
    annotations={"title": "Add operations task", "readOnlyHint": False, "destructiveHint": False},
)
async def cfo_add_task(params: AddTask) -> str:
    """Create a new operations task.

    Args: params.title (required), plus optional description, entity,
    assigned_to, priority, category, due_date.
    Returns: JSON of the created task including its new id.
    """
    try:
        return _dump(await _request("POST", "/api/ops/tasks", json_body=params.model_dump()))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_update_task",
    annotations={"title": "Update operations task", "readOnlyHint": False, "destructiveHint": False},
)
async def cfo_update_task(params: UpdateTask) -> str:
    """Update fields on an existing operations task. Setting status to 'done'
    or 'completed' stamps the completion time.

    Args: params.task_id (required) plus any of title, description, status,
    priority, assigned_to, due_date.
    Returns: JSON of the updated task.
    """
    try:
        body = params.model_dump(exclude_none=True)
        body.pop("task_id", None)
        return _dump(await _request("PUT", f"/api/ops/tasks/{params.task_id}", json_body=body))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_update_compliance",
    annotations={"title": "Update compliance filing", "readOnlyHint": False, "destructiveHint": False},
)
async def cfo_update_compliance(params: UpdateCompliance) -> str:
    """Update a compliance filing. Setting status to 'filed' auto-stamps the
    filing date.

    Args: params.filing_id (required) plus any of status, notes,
    assigned_to, due_date.
    Returns: JSON of the updated filing.
    """
    try:
        body = params.model_dump(exclude_none=True)
        body.pop("filing_id", None)
        return _dump(
            await _request("PUT", f"/api/compliance/filings/{params.filing_id}", json_body=body)
        )
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_add_lead",
    annotations={"title": "Add VWLR CRM lead", "readOnlyHint": False, "destructiveHint": False},
)
async def cfo_add_lead(params: AddLead) -> str:
    """Add a new lead to the VWLR coal-washery CRM.

    Args: params.company (required) plus optional contact_person, phone,
    location, distance_km, potential_volume, priority, status,
    next_followup, notes.
    Returns: JSON of the created lead including its new id.
    """
    try:
        return _dump(await _request("POST", "/api/vwlr/leads", json_body=params.model_dump()))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_log_interaction",
    annotations={"title": "Log CRM interaction", "readOnlyHint": False, "destructiveHint": False},
)
async def cfo_log_interaction(params: LogInteraction) -> str:
    """Log a CRM interaction (call, meeting, email, whatsapp) against a company
    or lead.

    Args: params.company (required) plus optional lead_id, contact, type,
    notes, outcome, follow_up_date.
    Returns: JSON {"ok": true} on success.
    """
    try:
        body = params.model_dump()
        body["created_by"] = "Aman"
        return _dump(await _request("POST", "/api/vwlr/interactions", json_body=body))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_add_tender",
    annotations={"title": "Add tender to pipeline", "readOnlyHint": False, "destructiveHint": False},
)
async def cfo_add_tender(params: AddTender) -> str:
    """Add a tender to the internal VWLR tender pipeline.

    Args: params.buyer (required) plus optional volume_mt, category,
    due_date, status, url, notes, eligibility_score.
    Returns: JSON of the created pipeline row including its new id.
    """
    try:
        return _dump(await _request("POST", "/api/vwlr/tenders/add", json_body=params.model_dump()))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_run_intelligence_scan",
    annotations={
        "title": "Run intelligence scan",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
    },
)
async def cfo_run_intelligence_scan() -> str:
    """Run the classification engine: pull from all data sources, classify into
    critical/important/info and refresh the alert board. Run this before
    cfo_daily_briefing if the briefing looks stale or empty.

    Returns: JSON with a count of alerts by level.
    """
    try:
        return _dump(await _request("POST", "/api/intelligence/scan"))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_generate_briefing",
    annotations={"title": "Generate morning briefing", "readOnlyHint": False, "destructiveHint": False},
)
async def cfo_generate_briefing() -> str:
    """Generate today's narrative morning briefing (uses the Grok API on the
    backend). Requires GROK_API_KEY configured server-side.

    Returns: JSON of the generated briefing, or a message if no key is set.
    """
    try:
        return _dump(await _request("POST", "/api/briefing/generate"))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


@mcp.tool(
    name="cfo_ask_grok",
    annotations={"title": "Ask Grok assistant", "readOnlyHint": True, "openWorldHint": True},
)
async def cfo_ask_grok(params: GrokAsk) -> str:
    """Ask the backend's Grok assistant a free-form question. Requires
    GROK_API_KEY configured server-side; otherwise returns a notice.

    Args: params.question.
    Returns: JSON {"answer": "..."}.
    """
    try:
        return _dump(await _request("POST", "/api/grok/ask", json_body={"question": params.question}))
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


# ── generic escape hatch ─────────────────────────────────────────────────────
@mcp.tool(
    name="cfo_api_request",
    annotations={"title": "Raw MDO API request", "readOnlyHint": False, "openWorldHint": True},
)
async def cfo_api_request(params: RawRequest) -> str:
    """Advanced escape hatch: call any MDO backend endpoint directly. Use only
    when no dedicated tool covers the endpoint you need (e.g. trading signals,
    Singhvi calls, WhatsApp, HDFC auth). See the FastAPI routes in
    mdo_server.py for the full list of paths.

    Args: params.method (default GET), params.path (must start with '/api'),
    params.params (query), params.body (JSON for POST/PUT).
    Returns: JSON of the backend response.
    """
    path = params.path if params.path.startswith("/") else "/" + params.path
    if not path.startswith("/api"):
        return "Error: path must begin with '/api'."
    try:
        return _dump(
            await _request(params.method.upper(), path, params=params.params, json_body=params.body)
        )
    except Exception as e:  # noqa: BLE001
        return _handle_error(e)


if __name__ == "__main__":
    mcp.run()
