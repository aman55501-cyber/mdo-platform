"""Execution module — SEPARATE from the read layer, OFF by default.

This is the only place in Shares CFO that can express an order. It is guarded by:
  * a hard master switch (CFO_TRADING_ENABLED) that defaults OFF,
  * hard per-order and per-day caps,
  * a daily-loss halt,
  * an allow-list of underlyings,
  * a kill-switch,
  * a two-step propose -> confirm flow (with a fresh confirm code), and
  * an audit log of every action.

Even with the switch ON, the final broker send is a distinct, clearly-marked step
that is wired only from the broker's official order docs — never guessed.
"""
