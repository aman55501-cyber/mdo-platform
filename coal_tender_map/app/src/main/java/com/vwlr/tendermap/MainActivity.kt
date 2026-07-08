package com.vwlr.tendermap

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import com.vwlr.tendermap.ui.MapScreen
import com.vwlr.tendermap.ui.T
import com.vwlr.tendermap.ui.TenderTheme
import com.vwlr.tendermap.ui.TenderViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            TenderTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = T.Bg) {
                    App()
                }
            }
        }
    }
}

@Composable
fun App(vm: TenderViewModel = viewModel()) {
    val state by vm.state.collectAsState()
    MapScreen(state = state, vm = vm)
}
