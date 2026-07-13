import React from "react";
import { View, Text, StyleSheet, ScrollView } from "react-native";
import { T } from "./theme";

export function Card({ children, style }: { children: React.ReactNode; style?: any }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Row({ children, style }: { children: React.ReactNode; style?: any }) {
  return <View style={[styles.row, style]}>{children}</View>;
}

// A clean "coming soon" screen that honestly states what the tab will do.
export function Placeholder({ title, tagline, bullets }: { title: string; tagline: string; bullets: string[] }) {
  return (
    <ScrollView style={styles.screen} contentContainerStyle={{ padding: T.pad }}>
      <Text style={styles.h1}>{title}</Text>
      <Text style={styles.dim}>{tagline}</Text>
      <Card style={{ marginTop: 16 }}>
        <Text style={[styles.dim, { marginBottom: 8 }]}>Coming in a later build:</Text>
        {bullets.map((b, i) => (
          <Text key={i} style={styles.bullet}>•  {b}</Text>
        ))}
      </Card>
      <Text style={[styles.dim, { marginTop: 16, fontStyle: "italic" }]}>
        This tab is intentionally empty — it lights up as its backend is built. No fake data.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: T.bg },
  card: {
    backgroundColor: T.card,
    borderColor: T.border,
    borderWidth: 1,
    borderRadius: T.radius,
    padding: T.pad,
  },
  row: { flexDirection: "row", alignItems: "center" },
  h1: { color: T.text, fontSize: 24, fontWeight: "700" },
  dim: { color: T.textDim, fontSize: 14 },
  bullet: { color: T.text, fontSize: 14, marginVertical: 3 },
});
