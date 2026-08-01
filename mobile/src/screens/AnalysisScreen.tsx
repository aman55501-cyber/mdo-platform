import React from "react";
import { Placeholder } from "../components";

export default function AnalysisScreen() {
  return (
    <Placeholder
      title="Analysis"
      tagline="Your idea engine — fundamentals + technicals, and where they disagree."
      bullets={[
        "Technicals: DMAs, volume signals, momentum (price & volume)",
        "Fundamentals with a confidence flag (Screener Premium as master)",
        "Explicit flag when fundamentals and technicals conflict",
        "Broad-universe scan for high-conviction setups (positional / daily)",
      ]}
    />
  );
}
