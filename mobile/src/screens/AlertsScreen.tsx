import React from "react";
import { Placeholder } from "../components";

export default function AlertsScreen() {
  return (
    <Placeholder
      title="Alerts"
      tagline="Only what matters — classified 🔴 critical / 🟡 important / 🟢 info."
      bullets={[
        "Concentration (stock & sector), D/E, promoter pledge, stop-loss, drawdown",
        "Momentum: 50/200-DMA cross + volume surge (whole universe)",
        "Every field normalised before compare — no unit-mismatch false alerts",
        "Push only high-severity NEW alerts (max 5/run, 72h cooldown)",
      ]}
    />
  );
}
