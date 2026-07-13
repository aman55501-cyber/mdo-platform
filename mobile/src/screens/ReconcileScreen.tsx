import React from "react";
import { Placeholder } from "../components";

export default function ReconcileScreen() {
  return (
    <Placeholder
      title="Reconcile"
      tagline="Daily diff + weekly deep tie-out — corporate-action aware."
      bullets={[
        "Daily: new trades, qty changes, cash moves, breaks vs yesterday",
        "Weekly: holdings ↔ contract notes ↔ ledger ↔ bank ↔ CAS",
        "Docs auto-pulled from Gmail (read-only, scoped senders)",
        "Degraded accounts flagged; the book is never silently incomplete",
      ]}
    />
  );
}
