export type Morning = { lines: string[]; at: string }

declare module 'claude-code' {
  interface PluginState {
    'mdo-morning': { view: Morning | null }
  }
}
