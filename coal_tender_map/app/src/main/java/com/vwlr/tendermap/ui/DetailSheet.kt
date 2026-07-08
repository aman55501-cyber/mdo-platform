@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.vwlr.tendermap.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vwlr.tendermap.data.TenderWithLocs
import com.vwlr.tendermap.domain.assess
import com.vwlr.tendermap.domain.inr
import com.vwlr.tendermap.domain.km
import com.vwlr.tendermap.domain.mt

@Composable
fun DetailContent(state: UiState, tw: TenderWithLocs, vm: TenderViewModel) {
    val t = tw.tender
    val org = state.org ?: return
    val verdict = assess(t, org)
    Column(Modifier.padding(16.dp).verticalScroll(rememberScrollState())) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = { vm.select(null) }, contentPadding = PaddingValues(0.dp)) {
                Text("← All tenders", color = T.Muted2, fontSize = 13.sp)
            }
            Spacer(Modifier.weight(1f))
            IconTextHeart(t.hearted) { vm.heart(t.id, !t.hearted) }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(9.dp).background(T.Mine, RoundedCornerShape(50))); Spacer(Modifier.width(6.dp))
            Text(tw.mines.firstOrNull()?.name ?: "Mine", fontSize = 18.sp, fontWeight = FontWeight.Bold)
            Text("  →  ", color = T.Muted)
            Box(Modifier.size(9.dp).background(T.Plant, RoundedCornerShape(2.dp))); Spacer(Modifier.width(6.dp))
            Text(tw.plant?.name ?: "Plant", fontSize = 18.sp, fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.height(6.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            StatusBadge(t.status); Spacer(Modifier.width(8.dp))
            Text(t.authority ?: "", color = T.Muted2, fontWeight = FontWeight.SemiBold)
        }
        Spacer(Modifier.height(14.dp))

        // Distance callout
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Callout(Modifier.weight(1f), "PICKUP FROM HQ", km(state.pickupKm(tw)), Color(0xFFF3F6F6), Color(0xFFDDE9E9))
            Callout(Modifier.weight(1f), "MINE → PLANT HAUL", km(state.haulKm(tw)), Color(0xFFFAF3E8), Color(0xFFEEE0C8))
        }
        Spacer(Modifier.height(14.dp))

        // Eligibility verdict
        EligibilityCard(verdict)
        Spacer(Modifier.height(14.dp))

        // Detail grid
        Surface(color = T.CardBg, shape = CardShape, border = BorderStroke(1.dp, T.Border2)) {
            Column(Modifier.padding(4.dp)) {
                GridRow("Tender value", inr(t.valueInr), "EMD", inr(t.emdInr))
                GridRow("Req. experience", mt(t.qrExperienceMt), "Req. turnover", inr(t.qrMinTurnoverInr))
                GridRow("Closes", t.deadline?.take(10) ?: "—", "Contract", t.contractMonths?.let { "${it.toInt()} mo" } ?: "—")
            }
        }
        Spacer(Modifier.height(14.dp))

        // Document card
        Surface(color = T.Panel, shape = CardShape, border = BorderStroke(1.dp, T.Border),
            onClick = { vm.openDoc(true) }) {
            Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(34.dp).background(Color(0xFFF0EDE6), RoundedCornerShape(6.dp)),
                    Alignment.Center) { Text("PDF", fontSize = 9.sp, fontWeight = FontWeight.Bold, color = T.AmberDeep) }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text("Notice Inviting Tender", fontWeight = FontWeight.SemiBold)
                    Text(t.refNo ?: t.portal ?: "", fontSize = 12.sp, fontFamily = FontFamily.Monospace, color = T.Muted)
                }
                Text("Open ›", color = T.AmberDeep, fontWeight = FontWeight.SemiBold)
            }
        }
        Spacer(Modifier.height(14.dp))

        // Status setter
        Text("Set status", fontSize = 12.sp, color = T.Muted)
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf("live","bidding","won","lost","closed").forEach { s ->
                Surface(onClick = { vm.setStatus(t.id, s) }, shape = ChipShape,
                    color = if (t.status == s) T.Ink else T.Panel,
                    border = if (t.status == s) null else BorderStroke(1.dp, T.Border)) {
                    Text(s, fontSize = 11.sp, color = if (t.status == s) Color.White else T.Ink,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp))
                }
            }
        }
        Spacer(Modifier.height(14.dp))
        Button(onClick = { vm.setStatus(t.id, "bidding") },
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = T.Ink)) {
            Text("Submit expression of interest", color = Color.White)
        }
        Spacer(Modifier.height(20.dp))
    }
}

@Composable
private fun IconTextHeart(on: Boolean, onClick: () -> Unit) =
    TextButton(onClick = onClick) { Text(if (on) "♥ Watching" else "♡ Watch", color = if (on) T.AmberDeep else T.Muted2, fontSize = 13.sp) }

@Composable
private fun Callout(mod: Modifier, label: String, value: String, bg: Color, border: Color) =
    Surface(mod, color = bg, shape = CardShape, border = BorderStroke(1.dp, border)) {
        Column(Modifier.padding(14.dp)) {
            Text(label, fontSize = 9.5.sp, fontWeight = FontWeight.SemiBold, color = T.Muted, letterSpacing = 0.5.sp)
            Row(verticalAlignment = Alignment.Bottom) {
                Text(value.removeSuffix(" km"), fontSize = 22.sp, fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace)
                Text(" km", fontSize = 12.sp, color = T.Muted2)
            }
        }
    }

@Composable
private fun EligibilityCard(v: com.vwlr.tendermap.domain.Verdict) {
    val (color, title) = when {
        v.noCriteria -> T.Muted2 to "No published PQC — check invite"
        v.eligible -> T.OpenFg to "You appear ELIGIBLE"
        else -> Color(0xFFC0392B) to "Gaps vs VWLR profile"
    }
    Surface(color = color.copy(alpha = 0.08f), shape = CardShape) {
        Column(Modifier.padding(14.dp)) {
            Text(title, color = color, fontWeight = FontWeight.Bold, fontSize = 15.sp)
            v.checks.forEach { c ->
                Spacer(Modifier.height(4.dp))
                Row {
                    Text(if (c.pass == true) "✓ " else "✗ ", color = if (c.pass == true) T.OpenFg else Color(0xFFC0392B), fontWeight = FontWeight.Bold)
                    Text("${c.label}: ${c.detail}", fontSize = 12.5.sp)
                }
            }
            if (v.checks.isEmpty()) Text("Eligibility criteria not published for this tender.", fontSize = 12.5.sp)
        }
    }
}

@Composable
private fun GridRow(k1: String, v1: String, k2: String, v2: String) =
    Row {
        Cell(Modifier.weight(1f), k1, v1); Cell(Modifier.weight(1f), k2, v2)
    }

@Composable
private fun Cell(mod: Modifier, k: String, v: String) =
    Column(mod.padding(12.dp)) {
        Text(k, fontSize = 9.5.sp, fontWeight = FontWeight.SemiBold, color = T.Muted, letterSpacing = 0.5.sp)
        Text(v, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold, fontFamily = FontFamily.Monospace)
    }
