package com.vwlr.tendermap.ui

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
import com.vwlr.tendermap.domain.inr
import com.vwlr.tendermap.domain.mt

// Full-screen NIT overlay, generated from tender fields (mirrors the design prototype).
@Composable
fun DocumentScreen(tw: TenderWithLocs, onClose: () -> Unit) {
    val t = tw.tender
    Column(Modifier.fillMaxSize().background(Color(0xFFEDEAE3))) {
        Row(Modifier.fillMaxWidth().background(T.Ink).padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("TENDER DOCUMENT", color = T.Amber, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                Text(t.refNo ?: t.title, color = Color.White, fontSize = 13.sp, fontFamily = FontFamily.Monospace)
            }
            TextButton(onClick = onClose) { Text("✕", color = Color.White, fontSize = 18.sp) }
        }
        Column(Modifier.padding(16.dp).verticalScroll(rememberScrollState())) {
            Surface(color = Color.White, shape = RoundedCornerShape(6.dp), shadowElevation = 6.dp) {
                Column(Modifier.padding(20.dp)) {
                    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(t.authority ?: "Government of India Enterprise", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                        Text("(A Government of India Enterprise)", fontSize = 10.sp, color = T.Muted)
                        Spacer(Modifier.height(8.dp))
                        Text("NOTICE INVITING TENDER", fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                        Text(t.refNo ?: "", fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = T.Muted2)
                    }
                    Spacer(Modifier.height(16.dp))
                    Sec("1. Scope of Work")
                    Body(t.title + (t.sourceField?.let { "  Source: $it." } ?: ""))
                    Sec("2. Quantity & Specification")
                    Body("Quantity: ${mt(t.qrExperienceMt)} class of execution expected. Material as per NIT grade.")
                    Sec("3. Financials")
                    Body("Estimated value: ${inr(t.valueInr)}\nEMD / Bid security: ${inr(t.emdInr)}\nPerformance BG: ${inr(t.pbgInr)}\nBid mode: ${t.portal ?: "e-Reverse Auction (GeM)"}")
                    Sec("4. Key Dates")
                    Body("Submission close: ${t.deadline?.take(16) ?: "see portal"}\nTechnical opening: ${t.techOpen?.take(16) ?: "close + 2 days"}\nBid validity: 120 days")
                    Sec("5. Eligibility Criteria")
                    Body(t.eligibilityNotes ?: "As per tender document on the portal.")
                    Spacer(Modifier.height(12.dp))
                    Text("Disclaimer: generated summary. Verify all terms against the official NIT on the portal.",
                        fontSize = 10.sp, color = T.Muted)
                }
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable private fun Sec(s: String) {
    Spacer(Modifier.height(12.dp))
    Text(s.uppercase(), color = T.AmberDeep, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 0.5.sp)
    Spacer(Modifier.height(4.dp))
}
@Composable private fun Body(s: String) = Text(s, fontSize = 12.5.sp, color = T.Ink, lineHeight = 18.sp)
