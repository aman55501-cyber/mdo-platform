import React from "react";
import { Placeholder } from "../components";

export default function WatchlistScreen() {
  return (
    <Placeholder
      title="Watchlist"
      tagline="A tight, high-conviction shortlist — names where fundamentals AND technicals agree."
      bullets={[
        "Auto-built from the Analysis scanners (not a manual list)",
        "Corporate-actions calendar: splits, bonus, dividends, results dates",
        "Events tape: hard events + softer news/sentiment buzz (India + global)",
        "Per-name price, DMA/volume signal, fundamental snapshot",
      ]}
    />
  );
}
