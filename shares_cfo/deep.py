"""Deep per-position analysis — fundamental + technical + news + sector/macro, fused
into one analyst brief per F&O underlying, with a stance and whether it agrees or
conflicts with how you're positioned.

Every input is transparent (no black box): each pillar lists the concrete bull/bear
factors it saw, then a composite stance is derived and checked against the leg's
directional bias so a position fighting the evidence gets flagged. All data is
already in the app (Screener fundamentals, Angel/EODHD prices, Google-News RSS,
market regime + global backdrop); this only composes and scores it.
"""

from __future__ import annotations

import logging

log = logging.getLogger("shares_cfo.deep")


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fundamental(ff: dict) -> dict:
    """Bull/bear read from Screener ratios. Returns factors + a -2..+2 tilt."""
    factors, tilt = [], 0
    pe, ipe = _f(ff.get("pe")), _f(ff.get("industry_pe"))
    roe, roce = _f(ff.get("roe")), _f(ff.get("roce"))
    de = _f(ff.get("de"))
    prom, pledge = _f(ff.get("promoter_holding")), _f(ff.get("pledge"))
    if pe is not None and ipe:
        if pe < ipe:
            factors.append(("+", f"P/E {pe} below industry {ipe} — cheaper than peers")); tilt += 1
        else:
            factors.append(("-", f"P/E {pe} above industry {ipe} — richer than peers")); tilt -= 1
    if roe is not None:
        if roe >= 15:
            factors.append(("+", f"ROE {roe}% — strong return on equity")); tilt += 1
        elif roe < 8:
            factors.append(("-", f"ROE {roe}% — weak return on equity")); tilt -= 1
    if roce is not None:
        if roce >= 15:
            factors.append(("+", f"ROCE {roce}% — efficient capital use")); tilt += 1
        elif roce < 8:
            factors.append(("-", f"ROCE {roce}% — poor capital efficiency")); tilt -= 1
    if de is not None:
        if de <= 0.5:
            factors.append(("+", f"D/E {de} — low leverage")); tilt += 1
        elif de >= 1.5:
            factors.append(("-", f"D/E {de} — high leverage")); tilt -= 1
    if pledge is not None and pledge >= 10:
        factors.append(("-", f"Promoter pledge {pledge}% — a governance flag")); tilt -= 1
    if prom is not None and prom >= 55:
        factors.append(("+", f"Promoter holding {prom}% — strong skin in the game")); tilt += 1
    verdict = "bullish" if tilt >= 2 else "bearish" if tilt <= -2 else "neutral"
    return {"tilt": max(-2, min(2, tilt)), "verdict": verdict, "factors": factors,
            "have_data": bool(ff)}


def _technical(tech: dict, chart: dict) -> dict:
    factors, tilt = [], 0
    rsi = _f(tech.get("rsi14"))
    above = tech.get("above_200dma")
    dma = tech.get("dma_signal")
    fh = _f(chart.get("from_52w_high_pct"))
    dpct = _f(chart.get("day_change_pct"))
    volx = _f(chart.get("vol_x"))
    if above is True:
        factors.append(("+", "Trading above the 200-DMA — primary trend up")); tilt += 1
    elif above is False:
        factors.append(("-", "Below the 200-DMA — primary trend down")); tilt -= 1
    if dma == "golden" or dma == "bullish":
        factors.append(("+", "50-DMA above 200-DMA (golden)")); tilt += 1
    elif dma == "death" or dma == "bearish":
        factors.append(("-", "50-DMA below 200-DMA (death cross)")); tilt -= 1
    if rsi is not None:
        if rsi >= 70:
            factors.append(("-", f"RSI {rsi} — overbought, prone to a pullback")); tilt -= 1
        elif rsi <= 30:
            factors.append(("+", f"RSI {rsi} — oversold, prone to a bounce")); tilt += 1
        else:
            factors.append(("~", f"RSI {rsi} — neutral momentum"))
    if fh is not None:
        if fh > -3:
            factors.append(("+", f"{fh}% from 52-wk high — near breakout")); tilt += 1
        elif fh < -25:
            factors.append(("-", f"{fh}% from 52-wk high — deep in a downtrend")); tilt -= 1
    if volx is not None and volx >= 2:
        factors.append(("~", f"Volume {volx}× the 20-day average — conviction in today's move"))
    lv = chart.get("levels") or {}
    verdict = "bullish" if tilt >= 2 else "bearish" if tilt <= -2 else "neutral"
    return {"tilt": max(-2, min(2, tilt)), "verdict": verdict, "factors": factors,
            "rsi14": rsi, "day_change_pct": dpct, "from_52w_high_pct": fh,
            "support": lv.get("support"), "resistance": lv.get("resistance"),
            "last": _f(chart.get("last"))}


def _macro_tilt(macro: dict) -> dict:
    reg = (macro.get("regime") or {})
    label = reg.get("regime")
    tilt = 1 if label == "calm" else -1 if label == "stressed" else 0
    factors = []
    if label:
        factors.append(("+" if tilt > 0 else "-" if tilt < 0 else "~",
                        f"Market regime {label} · VIX {reg.get('india_vix', '—')} · "
                        f"risk budget {reg.get('risk_budget_pct', '—')}%"))
    gl = (macro.get("global") or {}).get("markets") or []
    ups = sum(1 for m in gl if (m.get("change_pct") or 0) > 0)
    if gl:
        factors.append(("+" if ups > len(gl) / 2 else "-",
                        f"Global cues {'supportive' if ups > len(gl)/2 else 'soft'} "
                        f"({ups}/{len(gl)} up)"))
    return {"tilt": tilt, "factors": factors, "regime": label}


def analyze_underlying(sym: str, sector: str, macro: dict) -> dict:
    """Compose the four pillars for one underlying into a single brief with a stance."""
    from .analysis import fundamentals as fun, technicals as tech_mod, news as news_mod
    from .analysis.prices import get_ohlcv
    from .analysis import levels as levels_mod

    # --- fundamentals ---
    ff = {}
    try:
        ff = (fun.get(sym) or {}).get("fields") or {}
    except Exception as exc:
        log.info("deep fund %s: %s", sym, exc)
    fnd = _fundamental(ff)

    # --- technicals + chart context ---
    chart, tech = {}, {}
    try:
        data = get_ohlcv(sym)
        closes = data["closes"]
        tech = tech_mod.analyze(closes, data.get("volumes", []))
        highs, lows = data.get("highs", []), data.get("lows", [])
        last = closes[-1] if closes else None
        hi52 = max(highs[-252:]) if highs else (max(closes) if closes else None)
        chart = {"last": last, "source": data.get("source"),
                 "day_change_pct": round((closes[-1] / closes[-2] - 1) * 100, 2) if len(closes) > 1 else None,
                 "from_52w_high_pct": round((last / hi52 - 1) * 100, 1) if (last and hi52) else None,
                 "vol_x": tech.get("vol_x"), "levels": levels_mod.from_ohlcv(data)}
    except Exception as exc:
        log.info("deep tech %s: %s", sym, exc)
    tch = _technical(tech, chart)

    # --- news (company + sector) ---
    news = []
    try:
        news = news_mod.get_news(sym, limit=4) or []
    except Exception as exc:
        log.info("deep news %s: %s", sym, exc)
    sector_news = []
    if sector and sector not in ("Other", ""):
        try:
            sector_news = news_mod.get_news(f"India {sector} sector", limit=2) or []
        except Exception:
            pass

    mac = _macro_tilt(macro)

    # --- composite stance: fundamentals + technicals carry it, macro tilts the edges ---
    score = fnd["tilt"] + tch["tilt"] + (mac["tilt"] * 0.5)
    stance = "bullish" if score >= 1.5 else "bearish" if score <= -1.5 else "neutral"
    bull = [t for pill in (fnd["factors"], tch["factors"], mac["factors"]) for (d, t) in pill if d == "+"]
    bear = [t for pill in (fnd["factors"], tch["factors"], mac["factors"]) for (d, t) in pill if d == "-"]
    return {
        "symbol": sym, "sector": sector,
        "stance": stance, "score": round(score, 1),
        "fundamental": fnd, "technical": tch, "macro": mac,
        "news": news, "sector_news": sector_news,
        "bull": bull, "bear": bear,
        "price": {"last": tch.get("last"), "day_change_pct": tch.get("day_change_pct"),
                  "source": chart.get("source")},
    }
