package com.vwlr.tendermap.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Design tokens from the handoff
object T {
    val Ink = Color(0xFF16130F)
    val Bg = Color(0xFFF7F5F1)
    val CardBg = Color(0xFFFBFAF7)
    val Panel = Color(0xFFFFFFFF)
    val Border = Color(0xFFE3DED4)
    val Border2 = Color(0xFFEFEBE2)
    val Muted = Color(0xFF9A9082)
    val Muted2 = Color(0xFF7A7266)
    val Mine = Color(0xFF1E7A80)
    val Plant = Color(0xFFC88A2E)
    val Amber = Color(0xFFE9B44C)
    val AmberDeep = Color(0xFFB26A0F)
    val Route = Color(0xFFC8B48E)
    // status bg/fg
    val OpenBg = Color(0xFFE7F1EB); val OpenFg = Color(0xFF2E7D5B)
    val CloseBg = Color(0xFFF7ECD9); val CloseFg = Color(0xFFB26A0F)
    val AwardBg = Color(0xFFE6EDF3); val AwardFg = Color(0xFF3A5A7A)
    val ClosedBg = Color(0xFFECEAE6); val ClosedFg = Color(0xFF8A8272)
}

private val scheme = lightColorScheme(
    primary = T.Ink, background = T.Bg, surface = T.Panel, onPrimary = Color.White,
    onBackground = T.Ink, onSurface = T.Ink,
)

@Composable
fun TenderTheme(content: @Composable () -> Unit) =
    MaterialTheme(colorScheme = scheme, typography = Typography(), content = content)
