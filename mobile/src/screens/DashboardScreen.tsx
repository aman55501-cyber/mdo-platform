import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, RefreshControl, ActivityIndicator } from "react-native";
import { getPortfolio, Portfolio } from "../api";
import { CONFIG } from "../config";
import { Card, Row } from "../components";
import { T, formatINR, pct, timeAgo } from "../theme";

export default function DashboardScreen() {
  const [data, setData] = useState<Portfolio | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const p = await getPortfolio();
      setData(p);
      setError(null);
    } catch (e: any) {
      setError(e?.message ?? "Could not reach the backend.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, CONFIG.REFRESH_MS);
    return () => clearInterval(id);
  }, [load]);

  const onRefresh = () => { setRefreshing(true); load(); };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={T.blue} />
        <Text style={[styles.dim, { marginTop: 10 }]}>Loading your book…</Text>
      </View>
    );
  }

  if (error) {
    return (
      <ScrollView
        style={styles.screen}
        contentContainerStyle={{ padding: T.pad }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={T.blue} />}
      >
        <Text style={styles.h1}>Dashboard</Text>
        <Card style={{ marginTop: 16, borderColor: T.red }}>
          <Text style={{ color: T.red, fontWeight: "700", marginBottom: 6 }}>Can't reach your backend</Text>
          <Text style={styles.dim}>{error}</Text>
          <Text style={[styles.dim, { marginTop: 10 }]}>
            Check: PC server is running, {CONFIG.API_BASE} is your PC's LAN IP (not localhost),
            phone is on the same Wi-Fi, and the token matches. Pull down to retry.
          </Text>
        </Card>
      </ScrollView>
    );
  }

  const p = data!;
  const degraded = p.book_health.degraded > 0;

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={{ padding: T.pad, paddingBottom: 40 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={T.blue} />}
    >
      <Row style={{ justifyContent: "space-between" }}>
        <Text style={styles.h1}>Dashboard</Text>
        <Text style={styles.dim}>{timeAgo(p.as_of)}</Text>
      </Row>

      {/* Hero: net worth */}
      <Card style={{ marginTop: 12 }}>
        <Text style={styles.dim}>Net worth</Text>
        <Text style={styles.hero}>{formatINR(p.net_worth)}</Text>
        <Text style={{ color: p.day_change >= 0 ? T.green : T.red, fontSize: 15, fontWeight: "600", marginTop: 2 }}>
          {p.day_change >= 0 ? "▲" : "▼"} {formatINR(Math.abs(p.day_change))} ({pct(Math.abs(p.day_change_pct))}) today
        </Text>
        <Row style={{ marginTop: 8, justifyContent: "space-between" }}>
          <View>
            <Text style={styles.dim}>Holdings</Text>
            <Text style={styles.metric}>{formatINR(p.holdings_value)}</Text>
          </View>
          <View>
            <Text style={styles.dim}>Cash</Text>
            <Text style={styles.metric}>{formatINR(p.cash)}</Text>
          </View>
          <View>
            <Text style={styles.dim}>F&O P&L</Text>
            <Text style={[styles.metric, { color: p.positions_pnl >= 0 ? T.green : T.red }]}>
              {formatINR(p.positions_pnl)}
            </Text>
          </View>
        </Row>
      </Card>

      {/* Book health — honesty over false green */}
      <Card style={{ marginTop: 12, borderColor: degraded ? T.red : T.border }}>
        <Row style={{ justifyContent: "space-between" }}>
          <Text style={{ color: degraded ? T.red : T.green, fontWeight: "700" }}>
            {degraded ? "Book incomplete" : "Book complete"}
          </Text>
          <Text style={styles.dim}>
            {p.book_health.fresh}/{p.book_health.accounts} accounts fresh
          </Text>
        </Row>
        {p.book_health.degraded_accounts.map((d) => (
          <Text key={d.creds_key} style={[styles.dim, { color: T.amber, marginTop: 6 }]}>
            ⚠ {d.creds_key}: {d.reason}
          </Text>
        ))}
      </Card>

      {/* Sector concentration */}
      {p.sector_concentration.length > 0 && (
        <Card style={{ marginTop: 12 }}>
          <Text style={[styles.dim, { marginBottom: 8 }]}>Sector concentration</Text>
          {p.sector_concentration.map((s) => (
            <View key={s.sector} style={{ marginVertical: 5 }}>
              <Row style={{ justifyContent: "space-between" }}>
                <Text style={styles.rowText}>{s.sector}</Text>
                <Text style={styles.rowText}>{pct(s.pct)}</Text>
              </Row>
              <View style={styles.barBg}>
                <View style={[styles.barFill, { width: `${Math.min(100, s.pct * 100)}%` }]} />
              </View>
            </View>
          ))}
          {p.unmapped_sectors.length > 0 && (
            <Text style={[styles.dim, { marginTop: 8, color: T.amber }]}>
              Unmapped tickers (add to sectors.json): {p.unmapped_sectors.join(", ")}
            </Text>
          )}
        </Card>
      )}

      {/* Holdings */}
      {p.accounts.map((acc) => (
        <Card key={acc.creds_key} style={{ marginTop: 12 }}>
          <Row style={{ justifyContent: "space-between", marginBottom: 8 }}>
            <Text style={{ color: T.text, fontWeight: "700" }}>{acc.label || acc.creds_key}</Text>
            <Text style={styles.dim}>{acc.client_code}</Text>
          </Row>
          {acc.holdings.length === 0 && <Text style={styles.dim}>No holdings returned.</Text>}
          {acc.holdings.map((h) => (
            <Row key={h.ticker} style={styles.holdingRow}>
              <View style={{ flex: 2 }}>
                <Text style={styles.rowText}>{h.ticker}</Text>
                <Text style={styles.dim}>{h.quantity} @ {formatINR(h.average_price)}</Text>
              </View>
              <View style={{ flex: 1, alignItems: "flex-end" }}>
                <Text style={styles.rowText}>{formatINR(h.market_value)}</Text>
                <Text style={{ color: h.pnl >= 0 ? T.green : T.red, fontSize: 12 }}>
                  {h.pnl >= 0 ? "+" : ""}{formatINR(h.pnl)}
                </Text>
              </View>
            </Row>
          ))}
        </Card>
      ))}

      <Text style={[styles.dim, { marginTop: 16, textAlign: "center" }]}>
        Read-only • prices as of last pull • {timeAgo(p.as_of)}
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: T.bg },
  center: { flex: 1, backgroundColor: T.bg, alignItems: "center", justifyContent: "center" },
  h1: { color: T.text, fontSize: 24, fontWeight: "700" },
  hero: { color: T.text, fontSize: 40, fontWeight: "800", marginTop: 2 },
  metric: { color: T.text, fontSize: 18, fontWeight: "600", marginTop: 2 },
  dim: { color: T.textDim, fontSize: 13 },
  rowText: { color: T.text, fontSize: 15, fontWeight: "500" },
  holdingRow: { justifyContent: "space-between", paddingVertical: 7, borderTopColor: T.border, borderTopWidth: StyleSheet.hairlineWidth },
  barBg: { height: 8, backgroundColor: T.cardAlt, borderRadius: 4, marginTop: 4, overflow: "hidden" },
  barFill: { height: 8, backgroundColor: T.blue, borderRadius: 4 },
});
