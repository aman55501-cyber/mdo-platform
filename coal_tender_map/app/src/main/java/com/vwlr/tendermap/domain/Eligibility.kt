package com.vwlr.tendermap.domain

import com.vwlr.tendermap.data.OrgProfile
import com.vwlr.tendermap.data.Tender

data class Check(val label: String, val pass: Boolean?, val detail: String)

data class Verdict(val checks: List<Check>) {
    val applicable get() = checks.filter { it.pass != null }
    val eligible get() = applicable.isNotEmpty() && applicable.all { it.pass == true }
    val noCriteria get() = applicable.isEmpty()
}

fun assess(t: Tender, o: OrgProfile): Verdict {
    val checks = mutableListOf<Check>()
    val tOver = t.qrMinTurnoverInr; val oOver = o.avgTurnoverInr
    if (tOver != null && oOver != null)
        checks += Check("Turnover", oOver >= tOver,
            "need ${inr(tOver)} · have ${inr(oOver)}")
    val tExp = t.qrExperienceMt; val oExp = o.maxExperienceMt
    if (tExp != null && oExp != null)
        checks += Check("Experience", oExp >= tExp,
            "need ${mt(tExp)} in ${t.qrExperienceWindowMonths ?: "?"} mo · best ${mt(oExp)}")
    val pct = t.qrNetworthPct; val nw = o.netWorthInr; val cap = o.paidUpCapitalInr
    if (pct != null && nw != null && cap != null) {
        val need = pct / 100.0 * cap
        checks += Check("Net worth", nw >= need, "need ≥ $pct% of paid-up capital")
    }
    return Verdict(checks)
}
