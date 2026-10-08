"""Shares CFO — a read-only reconciliation & analysis system for a personal book.

Stage A scope (read-first): HDFC Securities adapter, portfolio reads, sector map.

Hard rule enforced by design: this package contains NO order-placement code.
The ability to trade does not exist here. Execution, if ever built, lives in a
separate, explicitly-gated module (Stage C) — never in the read path.
"""

__version__ = "0.1.0"
