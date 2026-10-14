export type Armed = { until: number } | null

declare module 'claude-code' {
  interface PluginState {
    'mdo-guard': { armed: Armed }
  }
}
