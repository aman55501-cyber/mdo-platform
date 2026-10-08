"""Scoring engine — turns Screener fundamentals (+ optional technicals) into a
0–100 quality score with plain-language flags, driven by a single RULE dict.

One engine powers four things:
  * score my holdings   -> watchdog view of what I own
  * hunt for ideas      -> rank the uploaded universe
  * custom scoring rule -> the caller supplies its own thresholds/weights
  * fundamental + technical -> combined score when price data is available

Unit contract (matches analysis/fundamentals.py — canonical at ingestion):
  pe, pb, de           -> ratios       (de 0.72 == 0.72x)
  roe, promoter_holding, pledge, dividend_yield -> PERCENT numbers (14.0 == 14%)
Every threshold below is stated in those units, so nothing is compared across
mismatched units (the false-alert bug the charter guards against).
"""

from __future__ import annotations

import json
from pathlib import Path

_RULE_FILE = Path(__file__).resolve().parent.parent / "data" / "state" / "score_rule.json"

# The default definition of "good". Override any subset via a custom rule.
DEFAULT_RULE: dict = {
    "weights": {"roe": 0.30, "de": 0.25, "pe": 0.20, "pledge": 0.15, "promoter": 0.10},
    # ROE (percent): higher is better
    "roe_great": 20, "roe_good": 15, "roe_ok": 10, "roe_weak": 5,
    # Debt/equity (ratio): lower is better
    "de_great": 0.25, "de_good": 0.5, "de_high": 1.0, "de_bad": 2.0,
    # P/E (ratio): a band is best; extremes penalised
    "pe_cheap": 10, "pe_fair": 25, "pe_rich": 40, "pe_bubble": 70,
    # Promoter pledge (percent): lower is better
    "pledge_ok": 5, "pledge_high": 10, "pledge_bad": 20,
    # Promoter holding (percent): higher is better (skin in the game)
    "promoter_good": 50, "promoter_ok": 40, "promoter_low": 25,
    # Verdict cut-offs on the fundamental score
    "fund_green": 65, "fund_red": 40,
    # How much technicals count in the blended score (0 = fundamentals only)
    "tech_weight": 0.40,
}


def load_rule() -> dict:
    """DEFAULT_RULE merged with a saved custom rule (data/state/score_rule.json)."""
    rule = {**DEFAULT_RULE, "weights": dict(DEFAULT_RULE["weights"])}
    try:
        if _RULE_FILE.exists():
            custom = json.loads(_RULE_FILE.read_text(encoding="utf-8"))
            if isinstance(custom.get("weights"), dict):
                rule["weights"].update(custom.pop("weights"))
            rule.update({k: v for k, v in custom.items() if k in DEFAULT_RULE})
    except (OSError, ValueError):
        pass
    return rule


def save_rule(custom: dict) -> dict:
    """Persist a custom rule (only known keys) and return the effective rule."""
    clean: dict = {}
    if isinstance(custom.get("weights"), dict):
        clean["weights"] = {k: float(v) for k, v in custom["weights"].items()
                            if k in DEFAULT_RULE["weights"]}
    for k, v in custom.items():
        if k in DEFAULT_RULE and k != "weights":
            clean[k] = float(v)
    _RULE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _RULE_FILE.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    return load_rule()


def _band(value, cuts: list[tuple[float, float]], default: float) -> float:
    """Return the score for the first (threshold, score) whose test passes."""
    for threshold, sc in cuts:
        if value <= threshold:
            return sc
    return default


def _score_roe(v, r) -> float | None:
    if v is None:
        return None
    if v >= r["roe_great"]: return 100.0
    if v >= r["roe_good"]:  return 80.0
    if v >= r["roe_ok"]:    return 60.0
    if v >= r["roe_weak"]:  return 40.0
    return 20.0


def _score_de(v, r) -> float | None:
    if v is None:
        return None
    return _band(v, [(r["de_great"], 100.0), (r["de_good"], 85.0),
                     (r["de_high"], 60.0), (r["de_bad"], 30.0)], 10.0)


def _score_pe(v, r) -> float | None:
    if v is None:
        return None
    if v <= 0:               return 25.0   # loss-making / negative P/E
    if v < r["pe_cheap"]:    return 75.0   # cheap, but could be a value trap
    if v <= r["pe_fair"]:    return 100.0  # the sweet spot
    if v <= r["pe_rich"]:    return 65.0
    if v <= r["pe_bubble"]:  return 35.0
    return 15.0


def _score_pledge(v, r) -> float | None:
    if v is None:
        return None
    return _band(v, [(0.01, 100.0), (r["pledge_ok"], 80.0),
                     (r["pledge_high"], 55.0), (r["pledge_bad"], 30.0)], 10.0)


def _score_promoter(v, r) -> float | None:
    if v is None:
        return None
    if v >= r["promoter_good"]: return 100.0
    if v >= r["promoter_ok"]:   return 75.0
    if v >= r["promoter_low"]:  return 55.0
    return 35.0


def score_fundamental(fields: dict, rule: dict | None = None) -> dict:
    """Weighted 0–100 fundamental score + flags. Weights renormalise over the
    fields that are actually present, so partial data never fakes a low score."""
    r = rule or load_rule()
    subs = {
        "roe": _score_roe(fields.get("roe"), r),
        "de": _score_de(fields.get("de"), r),
        "pe": _score_pe(fields.get("pe"), r),
        "pledge": _score_pledge(fields.get("pledge"), r),
        "promoter": _score_promoter(fields.get("promoter_holding"), r),
    }
    w = r["weights"]
    num = sum(w[k] * s for k, s in subs.items() if s is not None)
    den = sum(w[k] for k, s in subs.items() if s is not None)
    score = round(num / den, 1) if den else None

    flags = []
    de, pe, pledge = fields.get("de"), fields.get("pe"), fields.get("pledge")
    roe, prom = fields.get("roe"), fields.get("promoter_holding")
    if de is not None and de > r["de_high"]:
        flags.append(("🔴" if de > r["de_bad"] else "🟡", f"high debt (D/E {de})"))
    if pe is not None and pe > r["pe_rich"]:
        flags.append(("🔴" if pe > r["pe_bubble"] else "🟡", f"expensive (P/E {pe:.0f})"))
    if pledge is not None and pledge > r["pledge_ok"]:
        flags.append(("🔴" if pledge > r["pledge_bad"] else "🟡", f"promoter pledge {pledge:.0f}%"))
    if roe is not None and roe < r["roe_ok"]:
        flags.append(("🟡", f"low ROE {roe:.0f}%"))
    if prom is not None and prom < r["promoter_low"]:
        flags.append(("🟡", f"low promoter holding {prom:.0f}%"))

    return {"score": score, "subscores": {k: v for k, v in subs.items() if v is not None},
            "flags": [{"sev": s, "text": t} for s, t in flags],
            "coverage": round(den / sum(w.values()), 2) if den else 0.0}


def score_technical(tech: dict, rule: dict | None = None) -> dict:
    """0–100 trend/momentum score from the technicals block (+ flags)."""
    if not tech:
        return {"score": None, "flags": []}
    score = 50.0
    flags = []
    if tech.get("above_200dma") is True:
        score += 25
    elif tech.get("above_200dma") is False:
        score -= 25; flags.append({"sev": "🟡", "text": "below 200-DMA (downtrend)"})
    if tech.get("dma_signal") in ("golden_cross", "above_slow"):
        score += 15
    elif tech.get("dma_signal") in ("death_cross", "below_slow"):
        score -= 15
    rsi = tech.get("rsi14")
    if rsi is not None:
        if rsi > 75:
            score -= 10; flags.append({"sev": "🟡", "text": f"overbought (RSI {rsi:.0f})"})
        elif rsi < 30:
            flags.append({"sev": "🟢", "text": f"oversold (RSI {rsi:.0f})"})
    if tech.get("volume_alert"):
        flags.append({"sev": "🟢", "text": "volume surge"})
    return {"score": round(max(0.0, min(100.0, score)), 1), "flags": flags}


def combine(symbol: str, fields: dict, tech: dict | None,
            rule: dict | None = None) -> dict:
    """Blend fundamental + (optional) technical into one score + a 🟢/🟡/🔴 verdict."""
    r = rule or load_rule()
    fund = score_fundamental(fields, r)
    techr = score_technical(tech or {}, r)
    fs, ts = fund["score"], techr["score"]

    if fs is not None and ts is not None:
        tw = r["tech_weight"]
        overall = round(fs * (1 - tw) + ts * tw, 1)
    else:
        overall = fs if fs is not None else ts

    all_flags = fund["flags"] + techr["flags"]
    has_red = any(f["sev"] == "🔴" for f in all_flags)
    if fs is None:
        verdict = "⚪"  # no fundamental data at all
    elif has_red or fs < r["fund_red"]:
        verdict = "🔴"
    elif fs >= r["fund_green"] and not any(f["sev"] == "🟡" for f in fund["flags"]):
        verdict = "🟢"
    else:
        verdict = "🟡"

    return {
        "symbol": symbol.upper(),
        "verdict": verdict,
        "score": overall,
        "fundamental_score": fs,
        "technical_score": ts,
        "flags": all_flags,
        "fields": fields,
        "coverage": fund["coverage"],
    }
