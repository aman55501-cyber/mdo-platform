package com.vwlr.tendermap.domain

fun inr(v: Double?): String {
    if (v == null) return "—"
    return when {
        v >= 1_00_00_000 -> "₹%.2f Cr".format(v / 1_00_00_000)
        v >= 1_00_000 -> "₹%.2f L".format(v / 1_00_000)
        else -> "₹%.0f".format(v)
    }
}

fun mt(v: Double?): String = if (v == null) "—" else "%,.0f MT".format(v)
fun km(v: Double?): String = if (v == null) "—" else "%.0f km".format(v)
