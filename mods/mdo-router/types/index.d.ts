export type Route = { model: string; effort: 'low' | 'medium' | 'high'; why: string; calm: number }

declare module 'claude-code' {
  interface PluginState {
    'mdo-router': { route: Route | null; isOn: boolean }
  }
}
