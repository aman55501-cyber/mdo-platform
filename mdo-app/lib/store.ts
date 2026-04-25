import { create } from "zustand"
import type { Position, WatchlistItem, LiveEvent } from "./types"

interface LiveStore {
  prices: Record<string, number>        // ticker → ltp
  sentiments: Record<string, number>    // ticker → score
  signals: LiveEvent[]
  connected: boolean

  setPrice: (ticker: string, ltp: number) => void
  setSentiment: (ticker: string, score: number) => void
  addSignal: (e: LiveEvent) => void
  setConnected: (v: boolean) => void
}

export const useLiveStore = create<LiveStore>((set) => ({
  prices: {},
  sentiments: {},
  signals: [],
  connected: false,

  setPrice: (ticker, ltp) =>
    set((s) => ({ prices: { ...s.prices, [ticker]: ltp } })),

  setSentiment: (ticker, score) =>
    set((s) => ({ sentiments: { ...s.sentiments, [ticker]: score } })),

  addSignal: (e) =>
    set((s) => ({ signals: [e, ...s.signals].slice(0, 20) })),

  setConnected: (connected) => set({ connected }),
}))


// SSE connection — call once at app startup
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

export function connectLiveStream() {
  if (typeof window === "undefined") return

  const store = useLiveStore.getState()
  const es = new EventSource(`${BASE}/api/stream`)

  es.onopen = () => store.setConnected(true)
  es.onerror = () => store.setConnected(false)

  es.addEventListener("market", (e) => {
    const d = JSON.parse(e.data)
    store.setPrice(d.ticker, d.ltp)
  })

  es.addEventListener("sentiment", (e) => {
    const d = JSON.parse(e.data)
    store.setSentiment(d.ticker, d.score)
  })

  es.addEventListener("signal", (e) => {
    const d = JSON.parse(e.data)
    store.addSignal(d)
  })

  return () => es.close()
}
