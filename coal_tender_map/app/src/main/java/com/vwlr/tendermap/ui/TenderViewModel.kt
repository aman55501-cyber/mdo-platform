package com.vwlr.tendermap.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vwlr.tendermap.data.OrgProfile
import com.vwlr.tendermap.data.Repository
import com.vwlr.tendermap.data.TenderWithLocs
import com.vwlr.tendermap.domain.assess
import com.vwlr.tendermap.domain.haversineKm
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

enum class SortMode { DISTANCE, VALUE, DEADLINE }
enum class RadiusMode(val km: Int?) { ALL(null), R1000(1000), R750(750), R500(500) }
enum class StatusMode { ALL, LIVE }

data class UiState(
    val loading: Boolean = true,
    val error: String? = null,
    val org: OrgProfile? = null,
    val all: List<TenderWithLocs> = emptyList(),
    val selectedId: String? = null,
    val docOpen: Boolean = false,
    val sort: SortMode = SortMode.DISTANCE,
    val radius: RadiusMode = RadiusMode.ALL,
    val status: StatusMode = StatusMode.ALL,
) {
    fun pickupKm(tw: TenderWithLocs): Double? {
        val o = org ?: return null
        val m = tw.mines.firstOrNull() ?: return null
        return haversineKm(o.lat, o.lng, m.lat, m.lng)
    }
    fun haulKm(tw: TenderWithLocs): Double? {
        val m = tw.mines.firstOrNull() ?: return null
        val p = tw.plant ?: return null
        return haversineKm(m.lat, m.lng, p.lat, p.lng)
    }
    val visible: List<TenderWithLocs>
        get() {
            var list = all
            radius.km?.let { r -> list = list.filter { (pickupKm(it) ?: 0.0) <= r } }
            if (status == StatusMode.LIVE)
                list = list.filter { it.tender.status == "live" || it.tender.status == "bidding" }
            return when (sort) {
                SortMode.DISTANCE -> list.sortedBy { pickupKm(it) ?: Double.MAX_VALUE }
                SortMode.VALUE -> list.sortedByDescending { it.tender.valueInr ?: 0.0 }
                SortMode.DEADLINE -> list.sortedBy { it.tender.deadline ?: "9999" }
            }
        }
    val selected: TenderWithLocs? get() = all.firstOrNull { it.tender.id == selectedId }
    fun eligibleFor(tw: TenderWithLocs) = org?.let { assess(tw.tender, it).eligible } ?: false
}

class TenderViewModel : ViewModel() {
    private val repo = Repository()
    private val _s = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _s

    init { load() }

    fun load() {
        _s.value = _s.value.copy(loading = true, error = null)
        viewModelScope.launch {
            try {
                val org = repo.orgProfile()
                val tenders = repo.tenders()
                _s.value = _s.value.copy(loading = false, org = org, all = tenders)
            } catch (e: Exception) {
                _s.value = _s.value.copy(loading = false, error = e.message ?: "load failed")
            }
        }
    }

    fun select(id: String?) { _s.value = _s.value.copy(selectedId = id, docOpen = false) }
    fun openDoc(open: Boolean) { _s.value = _s.value.copy(docOpen = open) }
    fun cycleSort() { _s.value = _s.value.copy(sort = SortMode.values()[(_s.value.sort.ordinal + 1) % 3]) }
    fun cycleRadius() { _s.value = _s.value.copy(radius = RadiusMode.values()[(_s.value.radius.ordinal + 1) % 4]) }
    fun toggleStatus() {
        _s.value = _s.value.copy(status = if (_s.value.status == StatusMode.ALL) StatusMode.LIVE else StatusMode.ALL)
    }
    fun heart(id: String, hearted: Boolean) = viewModelScope.launch {
        try { repo.setHeart(id, hearted); load() } catch (_: Exception) {}
    }
    fun setStatus(id: String, status: String) = viewModelScope.launch {
        try { repo.setStatus(id, status); load() } catch (_: Exception) {}
    }
}
