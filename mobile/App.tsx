import React, { useState } from "react";
import { View, Text, StyleSheet, TouchableOpacity, SafeAreaView, StatusBar, Platform } from "react-native";
import { T } from "./src/theme";
import DashboardScreen from "./src/screens/DashboardScreen";
import AnalysisScreen from "./src/screens/AnalysisScreen";
import WatchlistScreen from "./src/screens/WatchlistScreen";
import AlertsScreen from "./src/screens/AlertsScreen";
import ReconcileScreen from "./src/screens/ReconcileScreen";

// Minimal 5-tab shell — no navigation library, so no dependency hell on first run.
const TABS = [
  { key: "dash", label: "Dashboard", icon: "📊", Screen: DashboardScreen },
  { key: "analysis", label: "Analysis", icon: "🔍", Screen: AnalysisScreen },
  { key: "watch", label: "Watchlist", icon: "⭐", Screen: WatchlistScreen },
  { key: "alerts", label: "Alerts", icon: "🔔", Screen: AlertsScreen },
  { key: "recon", label: "Reconcile", icon: "⚖️", Screen: ReconcileScreen },
] as const;

export default function App() {
  const [active, setActive] = useState<string>("dash");
  const Current = (TABS.find((t) => t.key === active) ?? TABS[0]).Screen;

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar barStyle="light-content" backgroundColor={T.bg} />
      <View style={styles.body}>
        <Current />
      </View>
      <View style={styles.tabbar}>
        {TABS.map((t) => {
          const on = t.key === active;
          return (
            <TouchableOpacity key={t.key} style={styles.tab} onPress={() => setActive(t.key)}>
              <Text style={[styles.tabIcon, { opacity: on ? 1 : 0.5 }]}>{t.icon}</Text>
              <Text style={[styles.tabLabel, { color: on ? T.blue : T.textDim }]}>{t.label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: T.bg, paddingTop: Platform.OS === "android" ? StatusBar.currentHeight : 0 },
  body: { flex: 1 },
  tabbar: {
    flexDirection: "row",
    borderTopColor: T.border,
    borderTopWidth: 1,
    backgroundColor: T.card,
    paddingBottom: 8,
    paddingTop: 6,
  },
  tab: { flex: 1, alignItems: "center", justifyContent: "center" },
  tabIcon: { fontSize: 20 },
  tabLabel: { fontSize: 11, marginTop: 2 },
});
