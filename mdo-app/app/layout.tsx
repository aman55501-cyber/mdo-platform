"use client"

import "./globals.css"
import { useEffect } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Sidebar } from "@/components/layout/Sidebar"
import { AuthGate } from "@/components/AuthGate"
import { BrainDock } from "@/components/BrainDock"
import { connectLiveStream } from "@/lib/store"

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 15_000, refetchInterval: 20_000 } } })

export default function RootLayout({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const cleanup = connectLiveStream()
    return () => cleanup?.()
  }, [])

  return (
    <html lang="en" className="h-full">
      <head>
        <title>AMAN</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="theme-color" content="#080808" />
        <link rel="manifest" href="/manifest.webmanifest" />
        <link rel="icon" href="/icons/icon-192.png" />
        <link rel="apple-touch-icon" href="/icons/icon-192.png" />
        <meta name="mobile-web-app-capable" content="yes" />
      </head>
      <body className="h-full flex" style={{ background: "var(--bg)", color: "var(--text)" }}>
        <QueryClientProvider client={qc}>
          <AuthGate>
            <Sidebar />
            <main className="flex-1 overflow-auto p-4 pt-[70px] md:p-6 md:pt-6">
              {children}
            </main>
            <BrainDock />
          </AuthGate>
        </QueryClientProvider>
      </body>
    </html>
  )
}
