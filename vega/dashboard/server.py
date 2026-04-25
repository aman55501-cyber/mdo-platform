"""FastAPI dashboard server with REST + SSE endpoints."""

from __future__ import annotations

import asyncio
import csv
import io
import json
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from ..events import EventType, MarketDataEvent, SentimentEvent, SignalEvent
from ..utils.logging import get_logger
from ..utils.time import is_market_open, is_premarket, now_ist, format_ist
from ..data.external_feeds import (
    fetch_tender247, fetch_gem, fetch_npa, singhvi_calls_to_feed
)
from ..vedanta import bridge as vedanta_bridge

log = get_logger("dashboard")

STATIC_DIR = Path(__file__).parent / "static"


def create_app(engine: any) -> FastAPI:
    """Create FastAPI app wired to the VEGA engine."""

    app = FastAPI(title="VEGA Dashboard", version="0.1.0")

    # SSE clients
    sse_queues: list[asyncio.Queue] = []

    # Subscribe to engine events for SSE broadcast
    async def _broadcast_market(event: MarketDataEvent) -> None:
        data = {
            "type": "market",
            "ticker": event.ticker,
            "ltp": event.ltp,
            "timestamp": event.timestamp.isoformat(),
        }
        for q in sse_queues:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass

    async def _broadcast_sentiment(event: SentimentEvent) -> None:
        data = {
            "type": "sentiment",
            "ticker": event.ticker,
            "score": event.score,
            "confidence": event.confidence,
            "summary": event.summary,
            "themes": event.themes,
            "post_count": event.post_count,
            "timestamp": event.timestamp.isoformat(),
        }
        for q in sse_queues:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass

    async def _broadcast_signal(event: SignalEvent) -> None:
        data = {
            "type": "signal",
            "id": event.id,
            "ticker": event.ticker,
            "action": event.action,
            "entry_price": event.entry_price,
            "target_price": event.target_price,
            "stop_loss": event.stop_loss,
            "quantity": event.quantity,
            "technical_score": event.technical_score,
            "sentiment_score": event.sentiment_score,
            "combined_score": event.combined_score,
            "rationale": event.rationale,
            "timestamp": event.timestamp.isoformat(),
        }
        for q in sse_queues:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass

    engine._event_bus.subscribe(EventType.MARKET_DATA, _broadcast_market)
    engine._event_bus.subscribe(EventType.SENTIMENT, _broadcast_sentiment)
    engine._event_bus.subscribe(EventType.SIGNAL, _broadcast_signal)

    # --- Routes ---

    @app.get("/", response_class=HTMLResponse)
    async def index():
        html_path = STATIC_DIR / "index.html"
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    @app.get("/api/status")
    async def api_status():
        now = now_ist()
        market = "OPEN" if is_market_open() else ("PRE-MARKET" if is_premarket() else "CLOSED")
        return {
            "time": format_ist(now),
            "market": market,
            "broker_authenticated": engine.is_broker_authenticated,
            "active_positions": engine.active_position_count,
            "watchlist": engine.config.watchlist,
        }

    @app.get("/api/positions")
    async def api_positions():
        positions = await engine.get_positions()
        return {"positions": positions}

    @app.get("/api/holdings")
    async def api_holdings():
        holdings = await engine.get_holdings()
        return {"holdings": holdings}

    @app.get("/api/funds")
    async def api_funds():
        funds = await engine.get_funds()
        return funds

    @app.get("/api/watchlist")
    async def api_watchlist():
        tickers = engine.config.watchlist
        data = []
        for t in tickers:
            entry = {"ticker": t, "ltp": None, "sentiment_score": None, "sentiment_confidence": None}
            mkt = engine._latest_market.get(t)
            if mkt:
                entry["ltp"] = mkt.ltp
            sent = engine._latest_sentiment.get(t)
            if sent:
                entry["sentiment_score"] = sent.score
                entry["sentiment_confidence"] = sent.confidence
                entry["sentiment_summary"] = sent.summary
            data.append(entry)
        return {"watchlist": data}

    @app.get("/api/signals")
    async def api_signals():
        if engine._store._db:
            rows = await engine._store._db.execute_fetchall(
                "SELECT * FROM trade_signals ORDER BY created_at DESC LIMIT 50"
            )
            return {"signals": [dict(r) for r in rows]}
        return {"signals": []}

    @app.get("/api/sentiment/{ticker}")
    async def api_sentiment(ticker: str):
        ticker = ticker.upper()
        try:
            event = await engine.get_sentiment(ticker)
            return {
                "ticker": event.ticker,
                "score": event.score,
                "confidence": event.confidence,
                "summary": event.summary,
                "themes": event.themes,
                "post_count": event.post_count,
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/pnl")
    async def api_pnl():
        stats = await engine.get_daily_stats()
        return stats

    @app.get("/api/health")
    async def api_health():
        checks = await engine.health_check()
        return checks

    @app.get("/api/stream")
    async def api_stream():
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        sse_queues.append(q)

        async def event_generator() -> AsyncGenerator:
            try:
                while True:
                    try:
                        data = await asyncio.wait_for(q.get(), timeout=30.0)
                        yield {"event": data["type"], "data": json.dumps(data)}
                    except asyncio.TimeoutError:
                        yield {"event": "ping", "data": "{}"}
            finally:
                sse_queues.remove(q)

        return EventSourceResponse(event_generator())

    # --- Portfolio Upload ---

    @app.post("/api/portfolio/upload")
    async def upload_portfolio(file: UploadFile = File(...)):
        """Upload a CSV/Excel portfolio file. Expected columns: ticker/symbol, quantity, average_price."""
        if not file.filename:
            raise HTTPException(400, "No file provided")

        ext = file.filename.rsplit(".", 1)[-1].lower()
        content = await file.read()

        try:
            if ext == "csv":
                records = _parse_csv(content.decode("utf-8"))
            elif ext in ("xlsx", "xls"):
                records = _parse_excel(content)
            else:
                raise HTTPException(400, f"Unsupported file type: .{ext}. Use .csv or .xlsx")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, f"Failed to parse file: {exc}")

        # Add tickers to watchlist
        added = []
        for rec in records:
            ticker = rec.get("ticker", "").upper()
            if ticker and ticker not in engine.config.watchlist:
                engine.config.watchlist.append(ticker)
                added.append(ticker)

        # Store in risk manager state
        for rec in records:
            ticker = rec.get("ticker", "").upper()
            if ticker:
                engine._risk_manager.state.positions[ticker] = {
                    "ticker": ticker,
                    "quantity": int(rec.get("quantity", 0)),
                    "average_price": float(rec.get("average_price", 0)),
                    "entry_price": float(rec.get("average_price", 0)),
                    "target": float(rec.get("average_price", 0)) * 1.03,
                    "stop_loss": float(rec.get("average_price", 0)) * 0.985,
                    "signal_id": "uploaded",
                }

        return {
            "message": f"Uploaded {len(records)} positions",
            "records": records,
            "added_to_watchlist": added,
        }

    # ── Singhvi Live Calls ──────────────────────────────────────────────

    @app.get("/api/singhvi")
    async def api_singhvi():
        """Latest Anil Singhvi stock calls with NSE + X links."""
        try:
            calls = []
            if hasattr(engine, "_singhvi_monitor") and engine._singhvi_monitor:
                calls = engine._singhvi_monitor.latest_calls
            items = singhvi_calls_to_feed(calls)
            return {"calls": [i.to_dict() for i in items], "count": len(items)}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/singhvi/refresh")
    async def api_singhvi_refresh():
        """Force re-poll @AnilSinghvi_ right now."""
        try:
            if hasattr(engine, "_singhvi_monitor") and engine._singhvi_monitor:
                calls = await engine._singhvi_monitor.poll_once()
                items = singhvi_calls_to_feed(calls)
                return {"calls": [i.to_dict() for i in items], "count": len(items), "refreshed": True}
            return {"calls": [], "count": 0, "refreshed": False}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # ── External Feeds (Tender247 / GeM / NPA) ─────────────────────────

    @app.get("/api/feeds/tenders")
    async def api_feeds_tenders():
        """Tender247.com — active coal/washery/mineral tenders with direct links."""
        try:
            items = await fetch_tender247(engine._grok_client)
            return {"items": [i.to_dict() for i in items], "count": len(items)}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/feeds/gem")
    async def api_feeds_gem():
        """GeM.gov.in — active government marketplace bids with direct links."""
        try:
            items = await fetch_gem(engine._grok_client)
            return {"items": [i.to_dict() for i in items], "count": len(items)}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/feeds/npa")
    async def api_feeds_npa():
        """IBBI/NCLT/Bank NPA auctions — industrial property liquidations with direct links."""
        try:
            items = await fetch_npa(engine._grok_client)
            return {"items": [i.to_dict() for i in items], "count": len(items)}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/feeds/all")
    async def api_feeds_all():
        """All external feeds combined — Tender247 + GeM + NPA + Singhvi — sorted by urgency."""
        try:
            singhvi_calls = []
            if hasattr(engine, "_singhvi_monitor") and engine._singhvi_monitor:
                singhvi_calls = engine._singhvi_monitor.latest_calls

            # Run all fetches concurrently
            tender_items, gem_items, npa_items = await asyncio.gather(
                fetch_tender247(engine._grok_client),
                fetch_gem(engine._grok_client),
                fetch_npa(engine._grok_client),
                return_exceptions=True,
            )
            singhvi_items = singhvi_calls_to_feed(singhvi_calls)

            all_items = []
            for batch in [tender_items, gem_items, npa_items, singhvi_items]:
                if isinstance(batch, list):
                    all_items.extend(batch)

            urgency_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            all_items.sort(key=lambda x: urgency_order.get(x.urgency, 99))

            return {
                "items": [i.to_dict() for i in all_items],
                "count": len(all_items),
                "sources": {
                    "tender247": len(tender_items) if isinstance(tender_items, list) else 0,
                    "gem": len(gem_items) if isinstance(gem_items, list) else 0,
                    "npa": len(npa_items) if isinstance(npa_items, list) else 0,
                    "singhvi": len(singhvi_items),
                }
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # ── VWLR / Vedanta CRM ─────────────────────────────────────────────

    @app.get("/api/intel")
    async def api_intel(urgency: str | None = None, category: str | None = None, status: str | None = None):
        """Intel Centre items from SQLite."""
        try:
            if engine._store._db:
                q = "SELECT * FROM intel_items WHERE 1=1"
                params: list = []
                if urgency:
                    q += " AND urgency = ?"
                    params.append(urgency.upper())
                if category:
                    q += " AND category = ?"
                    params.append(category.lower())
                if status:
                    q += " AND status = ?"
                    params.append(status.lower())
                q += " ORDER BY CASE urgency WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END, created_at DESC LIMIT 100"
                rows = await engine._store._db.execute_fetchall(q, params)
                return {"items": [dict(r) for r in rows]}
            return {"items": []}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/intel/{item_id}/resolve")
    async def api_intel_resolve(item_id: int):
        try:
            if engine._store._db:
                await engine._store._db.execute(
                    "UPDATE intel_items SET status='resolved', updated_at=datetime('now') WHERE id=?",
                    (item_id,)
                )
                row = await engine._store._db.execute_fetchall("SELECT * FROM intel_items WHERE id=?", (item_id,))
                return dict(row[0]) if row else {}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/intel/{item_id}/acknowledge")
    async def api_intel_acknowledge(item_id: int):
        try:
            if engine._store._db:
                await engine._store._db.execute(
                    "UPDATE intel_items SET status='acknowledged', updated_at=datetime('now') WHERE id=?",
                    (item_id,)
                )
                row = await engine._store._db.execute_fetchall("SELECT * FROM intel_items WHERE id=?", (item_id,))
                return dict(row[0]) if row else {}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/intel/{item_id}/snooze")
    async def api_intel_snooze(item_id: int, days: int = 1):
        try:
            if engine._store._db:
                await engine._store._db.execute(
                    "UPDATE intel_items SET status='snoozed', updated_at=datetime('now') WHERE id=?",
                    (item_id,)
                )
                row = await engine._store._db.execute_fetchall("SELECT * FROM intel_items WHERE id=?", (item_id,))
                return dict(row[0]) if row else {}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/intel")
    async def api_intel_add(item: dict):
        try:
            if engine._store._db:
                await engine._store._db.execute(
                    """INSERT INTO intel_items (category, source, urgency, entity, title, body, due_date, status)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (item.get("category","market"), item.get("source","manual"),
                     item.get("urgency","MEDIUM"), item.get("entity",""),
                     item.get("title",""), item.get("body",""),
                     item.get("due_date"), "open")
                )
                rows = await engine._store._db.execute_fetchall(
                    "SELECT * FROM intel_items ORDER BY id DESC LIMIT 1"
                )
                return dict(rows[0]) if rows else {}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # ── VWLR endpoints ─────────────────────────────────────────────────

    @app.get("/api/vwlr/tenders")
    async def api_vwlr_tenders(buyer: str | None = None, hot: bool = False):
        try:
            tenders = vedanta_bridge.get_tenders()
            if buyer:
                tenders = [t for t in tenders if buyer.lower() in t.get("buyer","").lower()]
            if hot:
                tenders = [t for t in tenders if t.get("eligibility_score", 0) > 0.7]
            return {"tenders": tenders}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/vwlr/leads")
    async def api_vwlr_leads(priority: str | None = None):
        try:
            leads = vedanta_bridge.get_leads()
            if priority:
                leads = [l for l in leads if l.get("priority","").lower() == priority.lower()]
            return {"leads": leads}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/vwlr/followups")
    async def api_vwlr_followups():
        try:
            leads = vedanta_bridge.get_followups_today()
            return {"leads": leads}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/vwlr/bid")
    async def api_vwlr_bid(buyer: str, volume: float, route: str, gate_price: float):
        try:
            result = vedanta_bridge.calculate_bid(buyer, volume, route, gate_price)
            return result
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # ── Grok ask ───────────────────────────────────────────────────────

    @app.post("/api/grok/ask")
    async def api_grok_ask(body: dict):
        try:
            question = body.get("question", "")
            answer = await engine._grok_client.ask(question)
            return {"answer": answer}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # ── Operations Tasks ────────────────────────────────────────────────

    @app.get("/api/ops/tasks")
    async def api_ops_tasks(status: str | None = None, category: str | None = None):
        try:
            if engine._store._db:
                q = "SELECT * FROM ops_tasks WHERE status != 'deleted'"
                params: list = []
                if status:
                    q += " AND status = ?"
                    params.append(status)
                if category:
                    q += " AND category = ?"
                    params.append(category)
                q += " ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, due_date ASC NULLS LAST"
                rows = await engine._store._db.execute_fetchall(q, params)
                return {"tasks": [dict(r) for r in rows]}
            return {"tasks": []}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/ops/tasks")
    async def api_ops_task_add(body: dict):
        try:
            if engine._store._db:
                await engine._store._db.execute(
                    """INSERT INTO ops_tasks (title,description,entity,assigned_to,priority,status,category,due_date)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (body.get("title",""), body.get("description",""), body.get("entity",""),
                     body.get("assigned_to","Aman"), body.get("priority","medium"),
                     "open", body.get("category","general"), body.get("due_date") or None)
                )
                await engine._store._db.commit()
                rows = await engine._store._db.execute_fetchall("SELECT * FROM ops_tasks ORDER BY id DESC LIMIT 1")
                return dict(rows[0]) if rows else {}
            return {}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.put("/api/ops/tasks/{task_id}")
    async def api_ops_task_update(task_id: int, body: dict):
        try:
            if engine._store._db:
                sets, params = [], []
                for k in ("title","description","entity","assigned_to","priority","status","category","due_date"):
                    if k in body:
                        sets.append(f"{k}=?")
                        params.append(body[k])
                if body.get("status") in ("done","completed"):
                    sets.append("completed_at=datetime('now')")
                if sets:
                    sets.append("updated_at=datetime('now')")
                    params.append(task_id)
                    await engine._store._db.execute(f"UPDATE ops_tasks SET {','.join(sets)} WHERE id=?", params)
                    await engine._store._db.commit()
                rows = await engine._store._db.execute_fetchall("SELECT * FROM ops_tasks WHERE id=?", (task_id,))
                return dict(rows[0]) if rows else {}
            return {}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # ── ANS Entities ────────────────────────────────────────────────────

    @app.get("/api/entities")
    async def api_entities(type: str | None = None, status: str | None = None):
        try:
            if engine._store._db:
                q = "SELECT * FROM ans_entities WHERE 1=1"
                params: list = []
                if type:
                    q += " AND entity_type=?"
                    params.append(type)
                if status:
                    q += " AND status=?"
                    params.append(status)
                q += " ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, name"
                rows = await engine._store._db.execute_fetchall(q, params)
                return {"entities": [dict(r) for r in rows]}
            return {"entities": []}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.put("/api/entities/{entity_id}")
    async def api_entity_update(entity_id: int, body: dict):
        try:
            if engine._store._db:
                sets, params = [], []
                for k in ("business","location","directors","annual_turnover","status","notes","cin","gstin","pan"):
                    if k in body:
                        sets.append(f"{k}=?")
                        params.append(body[k])
                if sets:
                    params.append(entity_id)
                    await engine._store._db.execute(f"UPDATE ans_entities SET {','.join(sets)} WHERE id=?", params)
                    await engine._store._db.commit()
                rows = await engine._store._db.execute_fetchall("SELECT * FROM ans_entities WHERE id=?", (entity_id,))
                return dict(rows[0]) if rows else {}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # ── Compliance Filings ──────────────────────────────────────────────

    @app.get("/api/compliance/filings")
    async def api_compliance_filings(entity: str | None = None, status: str | None = None, filing_type: str | None = None):
        try:
            if engine._store._db:
                q = "SELECT * FROM compliance_filings WHERE 1=1"
                params: list = []
                if entity:
                    q += " AND entity_name=?"
                    params.append(entity)
                if status:
                    q += " AND status=?"
                    params.append(status)
                if filing_type:
                    q += " AND filing_type=?"
                    params.append(filing_type)
                q += """ ORDER BY
                    CASE status WHEN 'overdue' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
                    due_date ASC NULLS LAST"""
                rows = await engine._store._db.execute_fetchall(q, params)
                return {"filings": [dict(r) for r in rows]}
            return {"filings": []}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.put("/api/compliance/filings/{filing_id}")
    async def api_compliance_filing_update(filing_id: int, body: dict):
        try:
            if engine._store._db:
                sets, params = [], []
                for k in ("status","notes","filed_on","assigned_to","due_date"):
                    if k in body:
                        sets.append(f"{k}=?")
                        params.append(body[k])
                if body.get("status") == "filed":
                    sets.append("filed_on=date('now')")
                if sets:
                    sets.append("updated_at=datetime('now')")
                    params.append(filing_id)
                    await engine._store._db.execute(f"UPDATE compliance_filings SET {','.join(sets)} WHERE id=?", params)
                    await engine._store._db.commit()
                rows = await engine._store._db.execute_fetchall("SELECT * FROM compliance_filings WHERE id=?", (filing_id,))
                return dict(rows[0]) if rows else {}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # ── Aditi Investment Pools ──────────────────────────────────────────

    @app.get("/api/aditi/pools")
    async def api_aditi_pools():
        try:
            if engine._store._db:
                rows = await engine._store._db.execute_fetchall("SELECT * FROM aditi_pools ORDER BY pool_code")
                return {"pools": [dict(r) for r in rows]}
            return {"pools": []}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.put("/api/aditi/pools/{pool_code}")
    async def api_aditi_pool_update(pool_code: str, body: dict):
        try:
            if engine._store._db:
                sets, params = [], []
                for k in ("current_value","target_allocation","instruments","notes"):
                    if k in body:
                        sets.append(f"{k}=?")
                        params.append(body[k])
                if sets:
                    sets.append("updated_at=datetime('now')")
                    params.append(pool_code)
                    await engine._store._db.execute(f"UPDATE aditi_pools SET {','.join(sets)} WHERE pool_code=?", params)
                    await engine._store._db.commit()
                rows = await engine._store._db.execute_fetchall("SELECT * FROM aditi_pools WHERE pool_code=?", (pool_code,))
                return dict(rows[0]) if rows else {}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # ── VWLR Lead CRM ───────────────────────────────────────────────────

    @app.put("/api/vwlr/leads/{lead_id}")
    async def api_vwlr_lead_update(lead_id: int, body: dict):
        try:
            conn = vedanta_bridge._get_conn()
            sets, params = [], []
            for k in ("status","priority","next_followup","notes","potential_volume"):
                if k in body:
                    sets.append(f"{k}=?")
                    params.append(body[k])
            if sets:
                params.append(lead_id)
                conn.execute(f"UPDATE leads SET {','.join(sets)} WHERE id=?", params)
                conn.commit()
            row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
            return dict(row) if row else {}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/vwlr/leads")
    async def api_vwlr_lead_add(body: dict):
        try:
            conn = vedanta_bridge._get_conn()
            conn.execute(
                """INSERT INTO leads (company,contact_person,phone,location,distance_km,
                   potential_volume,status,priority,next_followup,notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (body.get("company",""), body.get("contact_person",""),
                 body.get("phone",""), body.get("location",""),
                 body.get("distance_km",0), body.get("potential_volume",""),
                 body.get("status","prospect"), body.get("priority","Medium"),
                 body.get("next_followup"), body.get("notes",""))
            )
            conn.commit()
            row = conn.execute("SELECT * FROM leads ORDER BY id DESC LIMIT 1").fetchone()
            return dict(row) if row else {}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/vwlr/interactions")
    async def api_vwlr_interaction_add(body: dict):
        try:
            if engine._store._db:
                await engine._store._db.execute(
                    """INSERT INTO vwlr_interactions (lead_id,company,contact,type,notes,outcome,follow_up_date,created_by)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (body.get("lead_id"), body.get("company",""), body.get("contact",""),
                     body.get("type","call"), body.get("notes",""), body.get("outcome",""),
                     body.get("follow_up_date"), body.get("created_by","Aman"))
                )
                await engine._store._db.commit()
            return {"ok": True}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/vwlr/interactions")
    async def api_vwlr_interactions(lead_id: int | None = None):
        try:
            if engine._store._db:
                q = "SELECT * FROM vwlr_interactions WHERE 1=1"
                params: list = []
                if lead_id:
                    q += " AND lead_id=?"
                    params.append(lead_id)
                q += " ORDER BY created_at DESC LIMIT 50"
                rows = await engine._store._db.execute_fetchall(q, params)
                return {"interactions": [dict(r) for r in rows]}
            return {"interactions": []}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    return app


def _parse_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    records = []
    for row in reader:
        # Normalize column names
        norm = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in row.items()}
        ticker = norm.get("ticker") or norm.get("symbol") or norm.get("stock") or norm.get("scrip") or ""
        qty = norm.get("quantity") or norm.get("qty") or norm.get("shares") or "0"
        avg = norm.get("average_price") or norm.get("avg_price") or norm.get("buy_price") or norm.get("price") or "0"
        if ticker:
            records.append({
                "ticker": ticker.upper().replace(" ", ""),
                "quantity": int(float(qty)) if qty else 0,
                "average_price": float(avg) if avg else 0,
            })
    return records


def _parse_excel(content: bytes) -> list[dict]:
    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(400, "pandas required for Excel parsing")

    df = pd.read_excel(io.BytesIO(content))
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    ticker_col = None
    for c in ["ticker", "symbol", "stock", "scrip"]:
        if c in df.columns:
            ticker_col = c
            break

    qty_col = None
    for c in ["quantity", "qty", "shares"]:
        if c in df.columns:
            qty_col = c
            break

    avg_col = None
    for c in ["average_price", "avg_price", "buy_price", "price"]:
        if c in df.columns:
            avg_col = c
            break

    if not ticker_col:
        raise HTTPException(400, "No ticker/symbol column found in file")

    records = []
    for _, row in df.iterrows():
        ticker = str(row.get(ticker_col, "")).strip().upper()
        qty = int(float(row.get(qty_col, 0))) if qty_col else 0
        avg = float(row.get(avg_col, 0)) if avg_col else 0
        if ticker:
            records.append({"ticker": ticker, "quantity": qty, "average_price": avg})
    return records
