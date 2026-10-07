"""Page data. Every function takes a db with .query(sql, params) and returns plain dicts for the templates.

Rules this module enforces on screen:
  * the Desk and Holdings pages never carry a net-worth figure;
  * a price older than the market session is labelled as such, never presented as live;
  * ideas and calls are never removed for being held: they carry a "you hold this" marker and a count;
  * anything the app cannot see (HDFC demats, missing balances, liabilities) is listed, not hidden.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import fmt
from .config import KNOWN_DEMATS


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _freshness(db) -> dict:
    return {r["source"]: r["last_at"] for r in db.query("select source, last_at from wb.desk_freshness")}


def _price_basis(source: str | None, price_time: datetime | None, now: datetime) -> dict:
    """Say honestly what a price is. A holdings-pull price is a morning snapshot, not a live quote."""
    if price_time is None:
        return {"label": "no price", "live": False}
    if source and source != "holdings-pull":
        live = fmt.market_open(now) and (now - price_time).total_seconds() < 20 * 60
        return {"label": f"{source} · {fmt.ist_clock(price_time)}", "live": live}
    return {"label": f"morning pull · {fmt.ist_clock(price_time)}", "live": False}


def _coverage(db) -> dict:
    """How much of the book the 'already held' check can see."""
    ing = {r["portfolio"] for r in db.query("select distinct portfolio from wb.holdings_view")}
    stated = {r["owner_id"] for r in db.query("select distinct owner_id from wb.manual_holdings where active")}
    rows = []
    for code, label, broker in KNOWN_DEMATS:
        seen = code in ing or (broker == "hdfc" and label.lower() in {s.lower() for s in stated})
        rows.append({"code": code, "label": label, "broker": broker, "seen": seen})
    seen = sum(r["seen"] for r in rows)
    return {"rows": rows, "seen": seen, "total": len(rows), "pct": round(seen / len(rows) * 100) if rows else 0}


def desk(db, now: datetime | None = None) -> dict:
    now = now or _now()
    fresh = _freshness(db)
    mv_cols = "symbol, price, day_change_pct, price_source, price_time, owner_name"
    gainers = db.query(f"select {mv_cols} from wb.holdings_view where day_change_pct is not null "
                       "order by day_change_pct desc limit 5")
    losers = db.query(f"select {mv_cols} from wb.holdings_view where day_change_pct is not null "
                      "order by day_change_pct asc limit 5")
    for r in gainers + losers:
        r["basis"] = _price_basis(r["price_source"], r["price_time"], now)
    movers_live = any(r["basis"]["live"] for r in gainers + losers)
    scale = max([abs(float(r["day_change_pct"])) for r in gainers + losers] + [0.01])
    for r in gainers + losers:
        r["bar"] = fmt.bar_width(r["day_change_pct"], scale)

    ideas = db.query("select id, symbol, side, entry, stop, target, horizon, thesis, status, run_date, age_days, "
                     "price, price_time, price_source, pct_from_entry, held from wb.ideas_view order by run_date desc, id desc")
    for r in ideas:
        r["basis"] = _price_basis(r["price_source"], r["price_time"], now)
        r["stale"] = (r["age_days"] or 0) > 7 or "stale" in (r["thesis"] or "").lower()
        # a long idea progresses from its stop toward its target; sells/trims have no such range
        r["range"] = fmt.range_bar(r["price"], r["stop"], r["target"], r["entry"]) if (r["side"] or "").upper() in ("ADD", "BUY") else None

    calls = db.query("select id, caller, called_at, kind, action, symbol_raw, symbol, entry_low, entry_high, stop, "
                     "targets, horizon, status, needs_review, unresolved, price, price_time, price_source, "
                     "pct_from_entry, held from wb.calls_view order by called_at desc limit 20")
    for r in calls:
        r["basis"] = _price_basis(r["price_source"], r["price_time"], now)
        first_target = min(r["targets"]) if r["targets"] else None
        r["range"] = fmt.range_bar(r["price"], r["stop"], first_target, r["entry_high"]) if r["action"] in ("ADD", "BUY") else None

    held = {"ideas": sum(1 for r in ideas if r["held"]), "calls": sum(1 for r in calls if r["held"])}
    return {
        "gainers": gainers, "losers": losers, "movers_live": movers_live,
        "ideas": ideas, "calls": calls, "held": held,
        "coverage": _coverage(db),
        "fresh": {k: {"at": v, "age": fmt.age(v, now)} for k, v in fresh.items()},
        "now": now,
    }


def holdings(db, now: datetime | None = None) -> dict:
    now = now or _now()
    rows = db.query("select symbol, qty, avg_price, price, market_value, pnl_pct, day_change_pct, price_source, "
                    "price_time, owner_name from wb.holdings_view order by market_value desc nulls last")
    for r in rows:
        r["basis"] = _price_basis(r["price_source"], r["price_time"], now)
    acts = db.query("select symbol, status, buy_below, add_below, target, trim_above, price, crossing, inputs_missing "
                    "from wb.actions_view order by (crossing is null), symbol")
    return {"rows": rows, "actions": acts, "coverage": _coverage(db), "now": now}


def networth(db, now: datetime | None = None) -> dict:
    now = now or _now()
    lines = db.query("select scope, line, count(*) n, count(*) filter (where status='provisional') prov, "
                     "sum(amount) amount from wb.net_worth_lines group by 1, 2 order by 1, 2")
    by_scope: dict[str, dict] = {}
    for r in lines:
        s = by_scope.setdefault(r["scope"], {"lines": [], "total": 0.0, "prov": 0})
        s["lines"].append(r)
        s["total"] += float(r["amount"] or 0)
        s["prov"] += int(r["prov"] or 0)
    total = sum(s["total"] for s in by_scope.values())
    buckets = db.query("select bucket_id, amount, lines from wb.by_bucket order by amount desc nulls last")
    accounts = db.query("select owner_id, type, institution, last4, scope, as_of, amount, status, source "
                        "from wb.balance_latest order by owner_id, last4")
    for a in accounts:
        a["age"] = fmt.age(datetime.combine(a["as_of"], datetime.min.time(), tzinfo=timezone.utc), now) if a["as_of"] else "never"

    gaps = []
    for r in db.query("select a.owner_id, a.type, a.institution, a.last4 from wb.accounts a where a.active and "
                      "not exists (select 1 from wb.balances b where b.account_id = a.id)"):
        gaps.append(f"No balance on record: {r['institution']} ••{r['last4']} ({r['owner_id']})")
    for r in db.query("select subject from wb.conflicts where decided_value is null order by id"):
        gaps.append(f"Open question: {r['subject']}")
    cov = _coverage(db)
    for r in cov["rows"]:
        if not r["seen"]:
            gaps.append(f"Holdings not ingested: {r['label']} ({r['code']})")
    counts = db.query("select (select count(*) from wb.liabilities) liab, (select count(*) from wb.assets) assets")[0]
    if not counts["liab"]:
        gaps.append("No liabilities recorded (LAS loan, cards, other loans)")
    if not counts["assets"]:
        gaps.append("No real assets or company book values recorded")
    n_active = db.query("select count(*) n from wb.accounts where active")[0]["n"]
    counted, expected = len(accounts) + cov["seen"], int(n_active) + cov["total"]
    return {"total": total, "by_scope": by_scope, "buckets": buckets, "accounts": accounts,
            "gaps": gaps, "partial": bool(gaps), "now": now,
            "counted": counted, "expected": expected, "counted_pct": round(counted / expected * 100) if expected else 0}


def health(db, now: datetime | None = None) -> dict:
    now = now or _now()
    jobs = db.query("select job, description, active, last_ran_at, last_ok_at, last_run_ok, age_minutes, status "
                    "from wb.source_health order by active desc, job")
    for j in jobs:
        j["ok_age"] = fmt.age(j["last_ok_at"], now)
    live = [j for j in jobs if j["active"]]
    ok = sum(1 for j in live if j["status"] == "OK")
    return {"jobs": jobs, "fresh": {k: fmt.age(v, now) for k, v in _freshness(db).items()}, "now": now,
            "ok": ok, "live": len(live), "ok_pct": round(ok / len(live) * 100) if live else 0}
