"use client"

import { useMarketData } from "@/hooks/useMarketData"
import { TerminalShell } from "@/components/terminal/TerminalShell"

/**
 * /terminal — the DESK. Full-viewport professional trading workspace:
 * pro chart + drawing tools, live order book, mode-aware trade ticket,
 * positions/history dock, and the AI layer (setups on the canvas, the Wire).
 *
 * `useMarketData()` owns the app WebSocket + portfolio hydration exactly like
 * the dashboard does — routes never render simultaneously, so there is always
 * one socket.
 */
export default function TerminalPage() {
    useMarketData()
    return <TerminalShell />
}
