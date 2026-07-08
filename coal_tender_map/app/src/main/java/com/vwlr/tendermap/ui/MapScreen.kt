@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.vwlr.tendermap.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.google.android.gms.maps.model.*
import com.google.maps.android.compose.*
import com.vwlr.tendermap.data.TenderWithLocs
import com.vwlr.tendermap.domain.inr
import com.vwlr.tendermap.domain.km

@Composable
fun MapScreen(state: UiState, vm: TenderViewModel) {
    if (state.loading) { Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator() }; return }
    if (state.error != null) {
        Box(Modifier.fillMaxSize(), Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text("Couldn't load tenders", fontWeight = FontWeight.Bold)
                Text(state.error, color = T.Muted, fontSize = 12.sp)
                Spacer(Modifier.height(10.dp))
                Button(onClick = { vm.load() }) { Text("Retry") }
            }
        }
        return
    }
    val org = state.org ?: return
    val base = LatLng(org.lat, org.lng)
    val cam = rememberCameraPositionState { position = CameraPosition.fromLatLngZoom(base, 6f) }
    val selected = state.selected

    LaunchedEffect(state.selectedId, state.visible.size) {
        val pts = mutableListOf(base)
        val target = selected?.let { listOf(it) } ?: state.visible
        target.forEach { tw -> tw.locations.forEach { pts += LatLng(it.lat, it.lng) } }
        if (pts.size >= 2) {
            val b = LatLngBounds.builder().apply { pts.forEach { include(it) } }.build()
            runCatching { cam.animate(com.google.android.gms.maps.CameraUpdateFactory.newLatLngBounds(b, 140)) }
        }
    }

    Box(Modifier.fillMaxSize()) {
        GoogleMap(
            modifier = Modifier.fillMaxSize(),
            cameraPositionState = cam,
            properties = MapProperties(mapType = MapType.NORMAL),
            uiSettings = MapUiSettings(zoomControlsEnabled = false, mapToolbarEnabled = false),
            onMapClick = { vm.select(null) },
        ) {
            Marker(state = MarkerState(base), title = "${org.name} (${org.railwayCode})",
                icon = BitmapDescriptorFactory.defaultMarker(BitmapDescriptorFactory.HUE_AZURE))
            state.visible.forEach { tw ->
                val dim = selected != null && selected.tender.id != tw.tender.id
                tw.mines.forEach { m ->
                    Marker(state = MarkerState(LatLng(m.lat, m.lng)), title = "Mine · ${m.name}",
                        alpha = if (dim) 0.28f else 1f,
                        icon = BitmapDescriptorFactory.defaultMarker(180f),
                        onClick = { vm.select(tw.tender.id); false })
                }
                tw.plant?.let { p ->
                    Marker(state = MarkerState(LatLng(p.lat, p.lng)), title = "Plant · ${p.name}",
                        alpha = if (dim) 0.28f else 1f,
                        icon = BitmapDescriptorFactory.defaultMarker(BitmapDescriptorFactory.HUE_ORANGE),
                        onClick = { vm.select(tw.tender.id); false })
                    tw.mines.firstOrNull()?.let { m ->
                        Polyline(points = listOf(LatLng(m.lat, m.lng), LatLng(p.lat, p.lng)),
                            color = if (selected?.tender?.id == tw.tender.id) T.Plant else T.Route,
                            width = if (selected?.tender?.id == tw.tender.id) 8f else 4f,
                            pattern = listOf(Dash(24f), Gap(14f)))
                    }
                }
            }
            if (state.radius.km != null)
                Circle(center = base, radius = state.radius.km!! * 1000.0,
                    fillColor = Color(0x141E7A80), strokeColor = Color(0x551E7A80), strokeWidth = 2f)
        }

        // Top header + filter chips over a scrim
        Column(Modifier.fillMaxWidth().background(Color(0xE6F7F5F1)).padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("COAL LOGISTICS · INDIA", color = T.Muted, fontSize = 11.sp,
                        fontWeight = FontWeight.SemiBold, letterSpacing = 1.4.sp)
                    Text("Tender Map", fontSize = 23.sp, fontWeight = FontWeight.Bold, color = T.Ink)
                }
                Surface(color = T.Ink, shape = PillShape) {
                    Row(Modifier.padding(horizontal = 12.dp, vertical = 7.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(7.dp).background(T.Amber, RoundedCornerShape(50))); Spacer(Modifier.width(6.dp))
                        Text("${org.railwayCode} HQ", color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChipPill("SORT", state.sort.name.lowercase().replaceFirstChar { it.uppercase() }, false) { vm.cycleSort() }
                FilterChipPill("RADIUS", if (state.radius.km == null) "All" else "${state.radius.km} km", state.radius.km != null) { vm.cycleRadius() }
                FilterChipPill("STATUS", if (state.status == StatusMode.LIVE) "Live" else "All", state.status == StatusMode.LIVE) { vm.toggleStatus() }
            }
        }

        // Bottom sheet: list or detail
        Surface(
            Modifier.align(Alignment.BottomCenter).fillMaxWidth()
                .fillMaxHeight(if (selected == null) 0.46f else 0.66f),
            color = T.Panel, shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp),
            shadowElevation = 16.dp,
        ) {
            if (selected == null) TenderList(state, vm) else DetailContent(state, selected, vm)
        }

        if (state.docOpen && selected != null)
            DocumentScreen(selected) { vm.openDoc(false) }
    }
}

@Composable
private fun FilterChipPill(label: String, value: String, active: Boolean, onClick: () -> Unit) {
    Surface(onClick = onClick, shape = ChipShape,
        color = if (active) T.Ink else T.Panel,
        border = if (active) null else androidx.compose.foundation.BorderStroke(1.dp, T.Border)) {
        Row(Modifier.padding(horizontal = 12.dp, vertical = 8.dp)) {
            Text("$label ", fontSize = 11.sp, fontWeight = FontWeight.SemiBold,
                color = if (active) Color(0xFFCFC7B8) else T.Muted)
            Text(value, fontSize = 12.5.sp, fontWeight = FontWeight.Bold,
                color = if (active) Color.White else T.Ink)
        }
    }
}

@Composable
private fun TenderList(state: UiState, vm: TenderViewModel) {
    Column {
        Row(Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.Center) {
            Box(Modifier.width(40.dp).height(4.dp).background(T.Border, RoundedCornerShape(2.dp)))
        }
        Row(Modifier.padding(16.dp, 10.dp, 16.dp, 4.dp)) {
            LegendDot(T.Mine, "Mine"); Spacer(Modifier.width(14.dp))
            LegendDot(T.Plant, "Plant"); Spacer(Modifier.width(14.dp))
            LegendDot(T.Ink, "HQ")
        }
        LazyColumn(Modifier.padding(horizontal = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(state.visible) { tw -> TenderRow(state, tw) { vm.select(tw.tender.id) } }
            item { Spacer(Modifier.height(16.dp)) }
        }
    }
}

@Composable
private fun TenderRow(state: UiState, tw: TenderWithLocs, onClick: () -> Unit) {
    Surface(onClick = onClick, color = T.CardBg, shape = CardShape,
        border = androidx.compose.foundation.BorderStroke(1.dp, T.Border2)) {
        Column(Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(8.dp).background(T.Mine, RoundedCornerShape(50))); Spacer(Modifier.width(6.dp))
                Text(tw.mines.firstOrNull()?.name ?: tw.tender.authority ?: "Mine",
                    fontWeight = FontWeight.SemiBold, fontSize = 14.5.sp)
                Text("  →  ", color = T.Muted)
                Box(Modifier.size(8.dp).background(T.Plant, RoundedCornerShape(2.dp))); Spacer(Modifier.width(6.dp))
                Text(tw.plant?.name ?: "Plant", fontWeight = FontWeight.SemiBold, fontSize = 14.5.sp,
                    modifier = Modifier.weight(1f))
                StatusBadge(tw.tender.status)
            }
            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                Metric("FROM HQ", km(state.pickupKm(tw)))
                Metric("HAUL", km(state.haulKm(tw)))
                Metric("VALUE", inr(tw.tender.valueInr))
                if (state.eligibleFor(tw)) { Spacer(Modifier.weight(1f)); Text("ELIGIBLE", color = T.OpenFg, fontSize = 10.sp, fontWeight = FontWeight.Bold) }
            }
        }
    }
}

@Composable fun Metric(label: String, value: String) = Column {
    Text(label, fontSize = 9.5.sp, fontWeight = FontWeight.SemiBold, color = T.Muted, letterSpacing = 0.5.sp)
    Text(value, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold, fontFamily = FontFamily.Monospace)
}

@Composable fun LegendDot(color: Color, label: String) =
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(9.dp).background(color, RoundedCornerShape(50))); Spacer(Modifier.width(4.dp))
        Text(label, fontSize = 12.sp, color = T.Muted2)
    }

@Composable
fun StatusBadge(status: String) {
    val (bg, fg, label) = when (status) {
        "live" -> Triple(T.OpenBg, T.OpenFg, "Open")
        "bidding" -> Triple(T.CloseBg, T.CloseFg, "Bidding")
        "won" -> Triple(T.AwardBg, T.AwardFg, "Awarded")
        "lost" -> Triple(T.ClosedBg, T.ClosedFg, "Lost")
        else -> Triple(T.ClosedBg, T.ClosedFg, "Closed")
    }
    Surface(color = bg, shape = RoundedCornerShape(6.dp)) {
        Text(label, color = fg, fontSize = 11.sp, fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp))
    }
}
