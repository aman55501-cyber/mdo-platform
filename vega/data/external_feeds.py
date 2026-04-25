"""External feed scrapers via Grok web_search.

Sources:
  - Tender247.com   — coal/mineral/industrial tenders
  - GeM.gov.in      — government marketplace bids
  - IBBI / NCLT     — NPA liquidation auctions, real estate
  - Anil Singhvi    — already handled in sentiment/singhvi.py, re-exposed here

Each function returns a list[FeedItem] — dicts with a 'url' field pointing
to the actual source page so the user can click straight through.
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

from ..utils.logging import get_logger
from ..utils.time import now_ist

log = get_logger("external_feeds")

# ── data model ────────────────────────────────────────────────────────────────

@dataclass
class FeedItem:
    id: str
    source: str          # "tender247" | "gem" | "nclt" | "ibbi" | "singhvi" | "hdfc"
    category: str        # "tender" | "gem_bid" | "npa_auction" | "stock_call"
    title: str
    summary: str
    url: str             # ← direct link to actual page
    urgency: str         # "critical" | "high" | "medium" | "low"
    amount: str | None   # ₹ value if applicable
    due_date: str | None
    entity: str | None
    fetched_at: str = field(default_factory=lambda: now_ist().isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _make_id(source: str, text: str) -> str:
    return f"{source}_{hashlib.md5(text.encode()).hexdigest()[:10]}"


def _parse_json_from_text(text: str) -> list[dict]:
    """Extract JSON array from Grok response (handles markdown fences)."""
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        start = text.find("[")
        end = text.rfind("]") + 1
        if start < 0 or end <= start:
            return []
        return json.loads(text[start:end])
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("feed_parse_failed", error=str(exc), text=text[:200])
        return []


# ── Tender247 ─────────────────────────────────────────────────────────────────

TENDER247_SYSTEM = """You are a procurement intelligence analyst for an Indian coal washery company
(ANS Group, Raigarh, Chhattisgarh). Search tender247.com for active tenders relevant to:
- Coal, coal washery, mineral, middlings supply/purchase
- Industrial supplies: conveyor belts, HM plant, HEMM
- Government contracts in Chhattisgarh, Odisha, Jharkhand, Maharashtra
- SECL, CCL, WCL, MCL, SCCL, NLC, or private mining company tenders

For each tender return JSON with EXACTLY these fields:
{
  "tender_id": "string",
  "title": "string (concise)",
  "organization": "string",
  "value": "string (e.g. ₹2.4 Cr or '10,000 MT' or 'NA')",
  "due_date": "DD-MMM-YYYY or null",
  "location": "string",
  "url": "EXACT tender247.com URL for this tender — MUST start with https://tender247.com",
  "urgency": "high if due ≤3 days, medium if ≤7 days, low otherwise"
}

Return a JSON array. Max 12 results. Only OPEN/ACTIVE tenders.
If no tender247.com direct URL is found, use https://tender247.com/search?keyword=coal+washery
Return ONLY the JSON array."""

TENDER247_USER = (
    "Search tender247.com for coal washery, SECL, coal middlings, mineral tenders "
    "in Chhattisgarh / Odisha / Jharkhand. Today is {date}. "
    "Find the 10 most relevant OPEN tenders. Return JSON array with direct URLs."
)


async def fetch_tender247(grok_client) -> list[FeedItem]:
    today = now_ist().strftime("%d %B %Y")
    try:
        raw = await grok_client.web_search(
            system_prompt=TENDER247_SYSTEM,
            user_message=TENDER247_USER.format(date=today),
        )
    except Exception as exc:
        log.error("tender247_fetch_error", error=str(exc))
        return []

    items = _parse_json_from_text(raw)
    result = []
    for item in items:
        title = item.get("title", "")
        if not title:
            continue
        result.append(FeedItem(
            id=_make_id("tender247", title),
            source="tender247",
            category="tender",
            title=title,
            summary=f"{item.get('organization', '')} · {item.get('location', '')} · {item.get('value', '')}",
            url=item.get("url") or "https://tender247.com",
            urgency=item.get("urgency", "medium"),
            amount=item.get("value"),
            due_date=item.get("due_date"),
            entity=item.get("organization"),
            metadata={
                "tender_id": item.get("tender_id", ""),
                "location": item.get("location", ""),
            },
        ))
    log.info("tender247_fetched", count=len(result))
    return result


# ── GeM (Government e-Marketplace) ───────────────────────────────────────────

GEM_SYSTEM = """You are a government procurement analyst for ANS Group, Raigarh (coal washery / industrial).
Search gem.gov.in for active bids and direct purchase orders relevant to:
- Coal, coal washery products, mineral processing
- Industrial chemicals, lubricants, conveyor equipment
- Coal handling, coal transportation, crushing/screening
- Infrastructure in Chhattisgarh or Central India ministries

For each GeM bid/order return JSON:
{
  "bid_id": "string",
  "title": "string (concise)",
  "ministry_dept": "string",
  "estimated_value": "string (₹ amount)",
  "bid_end_date": "DD-MMM-YYYY or null",
  "quantity": "string",
  "url": "EXACT gem.gov.in URL — MUST start with https://mkp.gem.gov.in or https://bidplus.gem.gov.in",
  "urgency": "high if ends ≤3 days, medium ≤7 days, low otherwise",
  "consignee_location": "state/city"
}

Max 10 results. Only ACTIVE bids. Return ONLY the JSON array."""

GEM_USER = (
    "Search gem.gov.in for active coal, mineral, industrial bids for Chhattisgarh or central India. "
    "Today is {date}. Find 8 most relevant bids. Include direct bid URLs."
)


async def fetch_gem(grok_client) -> list[FeedItem]:
    today = now_ist().strftime("%d %B %Y")
    try:
        raw = await grok_client.web_search(
            system_prompt=GEM_SYSTEM,
            user_message=GEM_USER.format(date=today),
        )
    except Exception as exc:
        log.error("gem_fetch_error", error=str(exc))
        return []

    items = _parse_json_from_text(raw)
    result = []
    for item in items:
        title = item.get("title", "")
        if not title:
            continue
        result.append(FeedItem(
            id=_make_id("gem", title),
            source="gem",
            category="gem_bid",
            title=title,
            summary=f"{item.get('ministry_dept', '')} · Qty: {item.get('quantity', '')} · {item.get('consignee_location', '')}",
            url=item.get("url") or "https://gem.gov.in",
            urgency=item.get("urgency", "medium"),
            amount=item.get("estimated_value"),
            due_date=item.get("bid_end_date"),
            entity=item.get("ministry_dept"),
            metadata={
                "bid_id": item.get("bid_id", ""),
                "quantity": item.get("quantity", ""),
                "location": item.get("consignee_location", ""),
            },
        ))
    log.info("gem_fetched", count=len(result))
    return result


# ── NCLT / IBBI NPA Auctions ──────────────────────────────────────────────────

NPA_SYSTEM = """You are an NPA/distressed asset analyst for Aman Agrawal, ANS Group, Raigarh CG.
Search ibbi.gov.in, nclt.gov.in, and bank auction portals (bankeauctions.com, ibapi.in,
sarfaesi.com, bankauctions.co.in) for:
- Industrial property auctions: factories, plants, land
- Coal / mining company liquidations
- Real estate NPA auctions in Chhattisgarh, Odisha, MP, Maharashtra
- NCLT insolvency proceedings for companies with industrial assets
- Reserve price ₹1 Cr to ₹500 Cr range

For each opportunity return JSON:
{
  "case_no": "string",
  "company_name": "string",
  "asset_description": "string (concise — what is being sold)",
  "asset_type": "factory | land | plant | mixed | company",
  "reserve_price": "₹ amount or null",
  "auction_date": "DD-MMM-YYYY or null",
  "location": "city, state",
  "url": "EXACT direct URL to the case/listing — ibbi.gov.in, nclt.gov.in, or auction portal",
  "liquidator": "name if available",
  "urgency": "high if auction ≤7 days, medium ≤30 days, low otherwise",
  "bank": "name of bank (if SARFAESI/bank auction)"
}

Max 10 results. Prioritize Chhattisgarh, Odisha, Jharkhand.
Return ONLY the JSON array."""

NPA_USER = (
    "Search ibbi.gov.in, nclt.gov.in, and bank auction portals for NPA/liquidation auctions "
    "of industrial properties, factories, coal companies in Chhattisgarh, Odisha, Central India. "
    "Today is {date}. Find 8 most relevant opportunities. Include direct case/auction URLs."
)


async def fetch_npa(grok_client) -> list[FeedItem]:
    today = now_ist().strftime("%d %B %Y")
    try:
        raw = await grok_client.web_search(
            system_prompt=NPA_SYSTEM,
            user_message=NPA_USER.format(date=today),
        )
    except Exception as exc:
        log.error("npa_fetch_error", error=str(exc))
        return []

    items = _parse_json_from_text(raw)
    result = []
    for item in items:
        company = item.get("company_name", "")
        asset = item.get("asset_description", "")
        title = f"{company} — {asset}" if company else asset
        if not title.strip():
            continue
        result.append(FeedItem(
            id=_make_id("npa", title),
            source="nclt" if "nclt" in item.get("url", "").lower() or "ibbi" in item.get("url", "").lower() else "bank_auction",
            category="npa_auction",
            title=title,
            summary=f"{item.get('location', '')} · {item.get('asset_type', '')} · Reserve: {item.get('reserve_price', 'TBD')}",
            url=item.get("url") or "https://ibbi.gov.in",
            urgency=item.get("urgency", "medium"),
            amount=item.get("reserve_price"),
            due_date=item.get("auction_date"),
            entity=company,
            metadata={
                "case_no": item.get("case_no", ""),
                "asset_type": item.get("asset_type", ""),
                "liquidator": item.get("liquidator", ""),
                "bank": item.get("bank", ""),
                "location": item.get("location", ""),
            },
        ))
    log.info("npa_fetched", count=len(result))
    return result


# ── Singhvi calls → FeedItem ──────────────────────────────────────────────────

def singhvi_calls_to_feed(calls: list) -> list[FeedItem]:
    """Convert SinghviCall objects (from singhvi.py) to FeedItem for unified feed."""
    result = []
    for call in calls:
        ticker = getattr(call, "ticker", "")
        direction = getattr(call, "direction", "")
        entry = getattr(call, "entry_price", None)
        sl = getattr(call, "stop_loss", None)
        target = getattr(call, "target", None)
        validity = getattr(call, "validity", "unknown")
        confidence = getattr(call, "confidence", 0.5)
        summary = getattr(call, "summary", "")
        ts = getattr(call, "post_timestamp", "recent")

        # Urgency: intraday = high, swing = medium, positional = low
        urgency = "high" if validity == "intraday" else ("medium" if validity == "swing" else "low")

        # Links: X post + NSE quote
        nse_url = f"https://www.nseindia.com/get-quotes/equity?symbol={ticker}"
        x_url = "https://x.com/AnilSinghvi_"

        details = []
        if entry: details.append(f"Entry ₹{entry:,.0f}")
        if sl:    details.append(f"SL ₹{sl:,.0f}")
        if target: details.append(f"TGT ₹{target:,.0f}")
        details.append(validity.upper())

        result.append(FeedItem(
            id=_make_id("singhvi", f"{ticker}{direction}{summary[:30]}"),
            source="singhvi",
            category="stock_call",
            title=f"{direction} {ticker} — {' · '.join(details)}",
            summary=summary,
            url=nse_url,         # primary: NSE chart
            urgency=urgency,
            amount=f"₹{entry:,.0f}" if entry else None,
            due_date=None,
            entity="Anil Singhvi",
            metadata={
                "ticker": ticker,
                "direction": direction,
                "entry_price": entry,
                "stop_loss": sl,
                "target": target,
                "validity": validity,
                "confidence": confidence,
                "post_timestamp": ts,
                "x_url": x_url,
                "nse_url": nse_url,
                "tradingview_url": f"https://www.tradingview.com/chart/?symbol=NSE%3A{ticker}",
            },
        ))
    return result
