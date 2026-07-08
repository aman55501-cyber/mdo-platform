package com.vwlr.tendermap.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class OrgProfile(
    val name: String = "VWLR",
    @SerialName("railway_code") val railwayCode: String? = null,
    val lat: Double = 0.0,
    val lng: Double = 0.0,
    val address: String? = null,
    @SerialName("avg_turnover_inr") val avgTurnoverInr: Double? = null,
    @SerialName("net_worth_inr") val netWorthInr: Double? = null,
    @SerialName("paid_up_capital_inr") val paidUpCapitalInr: Double? = null,
    @SerialName("max_experience_mt") val maxExperienceMt: Double? = null,
    @SerialName("experience_window_months") val experienceWindowMonths: Int? = null,
    @SerialName("max_single_month_mt") val maxSingleMonthMt: Double? = null,
    @SerialName("is_msme") val isMsme: Boolean = true,
    @SerialName("operating_radius_km") val operatingRadiusKm: Int = 300,
)

@Serializable
data class TenderLocation(
    val id: String,
    @SerialName("tender_id") val tenderId: String? = null,
    val role: String,               // mine | plant | siding | base
    val name: String,
    val lat: Double,
    val lng: Double,
    val district: String? = null,
    val state: String? = null,
    val pin: String? = null,
    @SerialName("road_km_from_base") val roadKmFromBase: Double? = null,
    val notes: String? = null,
)

@Serializable
data class Tender(
    val id: String,
    @SerialName("ref_no") val refNo: String? = null,
    val title: String,
    val authority: String? = null,
    val portal: String? = null,
    @SerialName("source_field") val sourceField: String? = null,
    @SerialName("value_inr") val valueInr: Double? = null,
    @SerialName("emd_inr") val emdInr: Double? = null,
    @SerialName("pbg_inr") val pbgInr: Double? = null,
    val deadline: String? = null,
    @SerialName("tech_open") val techOpen: String? = null,
    @SerialName("contract_months") val contractMonths: Double? = null,
    @SerialName("qr_min_turnover_inr") val qrMinTurnoverInr: Double? = null,
    @SerialName("qr_experience_mt") val qrExperienceMt: Double? = null,
    @SerialName("qr_experience_window_months") val qrExperienceWindowMonths: Int? = null,
    @SerialName("qr_networth_pct") val qrNetworthPct: Int? = null,
    @SerialName("eligibility_notes") val eligibilityNotes: String? = null,
    @SerialName("pdf_url") val pdfUrl: String? = null,
    val status: String = "live",
    val hearted: Boolean = false,
)

// Convenience holder joining a tender with its locations.
data class TenderWithLocs(val tender: Tender, val locations: List<TenderLocation>) {
    val mines get() = locations.filter { it.role == "mine" }
    val plant get() = locations.firstOrNull { it.role == "plant" }
}
