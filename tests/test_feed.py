"""Decision Feed — the safety rules that make the feed worth trusting.

Covers R1–R8 from PLAN.md: dedup/cooldown, severity routing, action execution, the
money refusal, rejection never executing, failure recording, and the audit trail.

Runs under pytest OR standalone: `python tests/test_feed.py`.
Kept dependency-light (no pytest-asyncio) by driving the async API through asyncio.run.
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite

import mdo_feed


def run(coro):
    return asyncio.run(coro)


async def _fresh_db():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await mdo_feed.ensure_schema(db)
    return db


def _reset_env():
    for k in ("MDO_FEED_COOLDOWN_CRITICAL", "MDO_FEED_COOLDOWN_IMPORTANT",
              "MDO_FEED_COOLDOWN_INFO", "MDO_FEED_MONEY_ACTIONS", "MDO_FEED_EXPIRY_HOURS"):
        os.environ.pop(k, None)
    mdo_feed.clear_actions()


# --- R1/R2: dedup and cooldown ---------------------------------------------------

def test_dedup_within_cooldown():
    """The same finding must not interrupt twice inside its window."""
    _reset_env()

    async def go():
        db = await _fresh_db()
        first = await mdo_feed.publish(db, key="vwlr.sccl.deadline", title="SCCL deadline",
                                       severity="critical", domain="vwlr")
        second = await mdo_feed.publish(db, key="vwlr.sccl.deadline", title="SCCL deadline",
                                        severity="critical", domain="vwlr")
        assert first is not None and first["id"] > 0
        assert second is None, "duplicate inside cooldown must be suppressed"
        items = await mdo_feed.list_items(db)
        assert len(items) == 1
        # A quiet feed must be able to prove it was quiet on purpose.
        trail = await mdo_feed.audit_trail(db, first["id"])
        assert any(e["event"] == "suppressed" for e in trail)
        await db.close()

    run(go())


def test_republish_after_cooldown():
    """Once the window elapses the finding may interrupt again."""
    _reset_env()
    os.environ["MDO_FEED_COOLDOWN_CRITICAL"] = "0"

    async def go():
        db = await _fresh_db()
        a = await mdo_feed.publish(db, key="k", title="t", severity="critical")
        b = await mdo_feed.publish(db, key="k", title="t", severity="critical")
        assert a is not None and b is not None, "cooldown elapsed → publish again"
        assert a["id"] != b["id"]
        await db.close()

    run(go())
    _reset_env()


def test_different_keys_never_collide():
    _reset_env()

    async def go():
        db = await _fresh_db()
        assert await mdo_feed.publish(db, key="a", title="A", severity="critical")
        assert await mdo_feed.publish(db, key="b", title="B", severity="critical")
        assert len(await mdo_feed.list_items(db)) == 2
        await db.close()

    run(go())


# --- R3: severity routing --------------------------------------------------------

def test_notify_policy():
    assert mdo_feed.notify_policy("critical") == "push"
    assert mdo_feed.notify_policy("important") == "digest"
    assert mdo_feed.notify_policy("info") == "silent"


def test_publish_records_policy_and_orders_critical_first():
    _reset_env()

    async def go():
        db = await _fresh_db()
        await mdo_feed.publish(db, key="i", title="info item", severity="info")
        await mdo_feed.publish(db, key="c", title="critical item", severity="critical")
        items = await mdo_feed.list_items(db)
        assert items[0]["severity"] == "critical", "critical must sort first"
        assert items[0]["notify_policy"] == "push"
        assert items[1]["notify_policy"] == "silent"
        await db.close()

    run(go())


def test_unknown_severity_is_rejected():
    _reset_env()

    async def go():
        db = await _fresh_db()
        try:
            await mdo_feed.publish(db, key="x", title="t", severity="urgent")
            raise AssertionError("unknown severity must raise")
        except ValueError:
            pass
        await db.close()

    run(go())


# --- R4: internal actions execute on approval ------------------------------------

def test_approve_executes_internal():
    _reset_env()
    calls = []

    async def handler(payload):
        calls.append(payload)
        return {"task_id": 7}

    mdo_feed.register_action("add_task", "internal", handler)

    async def go():
        db = await _fresh_db()
        item = await mdo_feed.publish(
            db, key="k", title="Chase the CA", severity="important",
            action_type="add_task", action_payload={"title": "Call Vimal"})
        out = await mdo_feed.decide(db, item["id"], "approve")
        assert out["outcome"] == "executed"
        assert out["status"] == "executed"
        assert calls == [{"title": "Call Vimal"}], "handler receives the drafted payload"
        assert out["executed_at"]
        await db.close()

    run(go())
    _reset_env()


def test_item_without_action_is_acknowledged_not_executed():
    _reset_env()

    async def go():
        db = await _fresh_db()
        item = await mdo_feed.publish(db, key="k", title="FYI", severity="info")
        out = await mdo_feed.decide(db, item["id"], "approve")
        assert out["outcome"] == "acknowledged"
        assert out["status"] == "approved"
        await db.close()

    run(go())


def test_double_approval_cannot_execute_twice():
    """A double tap must not fire the action twice."""
    _reset_env()
    calls = []

    async def handler(payload):
        calls.append(payload)
        return {"ok": True}

    mdo_feed.register_action("add_task", "internal", handler)

    async def go():
        db = await _fresh_db()
        item = await mdo_feed.publish(db, key="k", title="t", severity="info",
                                      action_type="add_task", action_payload={})
        await mdo_feed.decide(db, item["id"], "approve")
        again = await mdo_feed.decide(db, item["id"], "approve")
        assert again["outcome"] == "already_decided"
        assert len(calls) == 1, "action must run exactly once"
        await db.close()

    run(go())
    _reset_env()


# --- R5: money never moves from a tap --------------------------------------------

def test_money_action_refused():
    """The headline safety rule: approving a money action does not execute it."""
    _reset_env()
    fired = []

    async def place_order(payload):
        fired.append(payload)
        return {"order_id": "should-never-happen"}

    mdo_feed.register_action("place_order", "money", place_order)

    async def go():
        db = await _fresh_db()
        item = await mdo_feed.publish(
            db, key="k", title="Trim NIFTY exposure", severity="critical",
            action_type="place_order", action_payload={"symbol": "NIFTY", "qty": 75})
        out = await mdo_feed.decide(db, item["id"], "approve")
        assert out["outcome"] == "refused"
        assert out["status"] == "refused"
        assert fired == [], "a money handler must never be called in v1"
        trail = await mdo_feed.audit_trail(db, item["id"])
        assert any(e["event"] == "refused" for e in trail), "refusal must be audited"
        await db.close()

    run(go())
    _reset_env()


def test_money_action_runs_only_when_deliberately_enabled():
    """The switch exists and is off by default — proving the refusal is policy, not absence."""
    _reset_env()
    fired = []

    async def place_order(payload):
        fired.append(payload)
        return {"order_id": "x1"}

    mdo_feed.register_action("place_order", "money", place_order)
    os.environ["MDO_FEED_MONEY_ACTIONS"] = "1"

    async def go():
        db = await _fresh_db()
        item = await mdo_feed.publish(db, key="k", title="t", severity="critical",
                                      action_type="place_order", action_payload={"q": 1})
        out = await mdo_feed.decide(db, item["id"], "approve")
        assert out["outcome"] == "executed"
        assert len(fired) == 1
        await db.close()

    run(go())
    _reset_env()


def test_outward_action_executes_and_is_audited():
    """Messaging a real person is allowed on approval, but always leaves a record."""
    _reset_env()
    sent = []

    async def send_wa(payload):
        sent.append(payload)
        return {"sent": True}

    mdo_feed.register_action("whatsapp_message", "outward", send_wa)

    async def go():
        db = await _fresh_db()
        item = await mdo_feed.publish(
            db, key="k", title="Follow up with site head", severity="important",
            action_type="whatsapp_message",
            action_payload={"to": "site-head", "text": "Please send today's tally"})
        out = await mdo_feed.decide(db, item["id"], "approve")
        assert out["outcome"] == "executed"
        assert len(sent) == 1
        trail = await mdo_feed.audit_trail(db, item["id"])
        assert any(e["event"] == "executed" for e in trail)
        await db.close()

    run(go())
    _reset_env()


# --- R6: rejection never executes ------------------------------------------------

def test_reject_never_executes():
    _reset_env()
    fired = []

    async def handler(payload):
        fired.append(payload)
        return {}

    mdo_feed.register_action("add_task", "internal", handler)

    async def go():
        db = await _fresh_db()
        item = await mdo_feed.publish(db, key="k", title="t", severity="info",
                                      action_type="add_task", action_payload={})
        out = await mdo_feed.decide(db, item["id"], "reject")
        assert out["outcome"] == "rejected"
        assert out["status"] == "rejected"
        assert fired == [], "rejection must never run the action"
        await db.close()

    run(go())
    _reset_env()


# --- R7: failures are recorded, never lost ---------------------------------------

def test_failed_action_is_recorded():
    _reset_env()

    async def boom(payload):
        raise RuntimeError("broker timed out")

    mdo_feed.register_action("add_task", "internal", boom)

    async def go():
        db = await _fresh_db()
        item = await mdo_feed.publish(db, key="k", title="t", severity="info",
                                      action_type="add_task", action_payload={})
        out = await mdo_feed.decide(db, item["id"], "approve")
        assert out["outcome"] == "failed"
        assert "broker timed out" in out["result"]
        # The item survives so it can be retried or read later.
        assert await mdo_feed.get_item(db, item["id"]) is not None
        await db.close()

    run(go())
    _reset_env()


def test_unregistered_action_cannot_be_published():
    """Catch the producer's mistake at publish, not at approval time."""
    _reset_env()

    async def go():
        db = await _fresh_db()
        try:
            await mdo_feed.publish(db, key="k", title="t", severity="info",
                                   action_type="nope", action_payload={})
            raise AssertionError("unregistered action must raise at publish")
        except ValueError:
            pass
        await db.close()

    run(go())


# --- R8: the audit trail ---------------------------------------------------------

def test_audit_trail_is_appended():
    _reset_env()

    async def handler(payload):
        return {"ok": True}

    mdo_feed.register_action("add_task", "internal", handler)

    async def go():
        db = await _fresh_db()
        item = await mdo_feed.publish(db, key="k", title="t", severity="critical",
                                      action_type="add_task", action_payload={})
        await mdo_feed.mark_notified(db, item["id"], "whatsapp:ok")
        await mdo_feed.decide(db, item["id"], "approve")
        events = [e["event"] for e in await mdo_feed.audit_trail(db, item["id"])]
        assert events == ["published", "notified", "approved", "executed"]
        await db.close()

    run(go())
    _reset_env()


# --- housekeeping ----------------------------------------------------------------

def test_expire_stale_only_touches_undecided():
    _reset_env()
    os.environ["MDO_FEED_EXPIRY_HOURS"] = "0"

    async def go():
        db = await _fresh_db()
        keep = await mdo_feed.publish(db, key="a", title="decided", severity="info")
        await mdo_feed.decide(db, keep["id"], "reject")
        stale = await mdo_feed.publish(db, key="b", title="undecided", severity="info")
        n = await mdo_feed.expire_stale(db)
        assert n == 1
        assert (await mdo_feed.get_item(db, stale["id"]))["status"] == "expired"
        assert (await mdo_feed.get_item(db, keep["id"]))["status"] == "rejected"
        await db.close()

    run(go())
    _reset_env()


def test_counts_reports_pending_only():
    _reset_env()

    async def go():
        db = await _fresh_db()
        await mdo_feed.publish(db, key="a", title="A", severity="critical")
        await mdo_feed.publish(db, key="b", title="B", severity="important")
        done = await mdo_feed.publish(db, key="c", title="C", severity="info")
        await mdo_feed.decide(db, done["id"], "reject")
        c = await mdo_feed.counts(db)
        assert c["critical"] == 1 and c["important"] == 1 and c["info"] == 0
        assert c["pending_total"] == 2
        await db.close()

    run(go())


def test_register_action_rejects_unknown_kind():
    _reset_env()

    async def handler(payload):
        return {}

    try:
        mdo_feed.register_action("x", "dangerous", handler)
        raise AssertionError("unknown kind must raise")
    except ValueError:
        pass


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
                print(f"  ok   {name}")
            except Exception as e:
                failed += 1
                print(f"  FAIL {name}: {type(e).__name__}: {e}")
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


# --- R10: the brain reaches capital depth, sites and the feed ---------------------

def test_brain_has_capital_tools():
    """The keyhole fix: capital questions must not bottom out at one summary tool."""
    import mdo_brain
    names = {t["name"] for t in mdo_brain.TOOLS}
    for expected in ("capital_positions", "capital_exposure", "capital_reconcile",
                     "capital_market_regime", "capital_ideas", "capital_fundamentals",
                     "capital_execution_status"):
        assert expected in names, f"brain is missing {expected}"
    assert "get_portfolio" in names, "the summary tool stays too"


def test_brain_has_site_and_feed_tools():
    import mdo_brain
    names = {t["name"] for t in mdo_brain.TOOLS}
    assert {"get_site_data", "get_site_links", "get_decision_feed"} <= names


def test_every_brain_tool_has_a_dispatch_branch():
    """A tool the model can call but the dispatcher cannot route is a live failure."""
    import inspect
    import mdo_brain
    src = inspect.getsource(mdo_brain._dispatch)
    for t in mdo_brain.TOOLS:
        assert f'"{t["name"]}"' in src, f'{t["name"]} has no dispatch branch'
