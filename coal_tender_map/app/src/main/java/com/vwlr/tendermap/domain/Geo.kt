package com.vwlr.tendermap.domain

import kotlin.math.*

fun haversineKm(lat1: Double, lng1: Double, lat2: Double, lng2: Double): Double {
    val r = 6371.0
    fun rad(x: Double) = x * PI / 180.0
    val dLat = rad(lat2 - lat1); val dLng = rad(lng2 - lng1)
    val a = sin(dLat / 2).pow(2) + cos(rad(lat1)) * cos(rad(lat2)) * sin(dLng / 2).pow(2)
    return r * 2 * atan2(sqrt(a), sqrt(1 - a))
}
