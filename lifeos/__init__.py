"""LIFEOS — one surface Aman opens each morning.

A scheduled 06:30 IST run reads every source, renders one static HTML snapshot,
and serves it behind HTTP Basic auth. A live /ask bar answers questions with the
current run's state injected. Read-and-draft only — it never transacts.

The non-negotiables (see the build brief) are enforced structurally:
  1. Every run reports, especially when it finds nothing (nil states in words).
  2. A failed source never aborts the run (each source is fault-isolated).
  3. The run must prove it ran (runs table + heartbeat; silent death is visible).
  4. Autonomy: anything that moves money/signs/files needs Aman's click.
  5. Never send email — drafts only.
  6. Secrets live in .env only — read from env, fail loudly if missing.
"""

__all__ = ["__version__"]
__version__ = "0.0.0"  # Phase 0 — skeleton
