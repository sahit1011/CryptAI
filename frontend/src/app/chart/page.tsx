"use client"

import { useMarketData } from "@/hooks/useMarketData"
import { TerminalShell } from "@/components/terminal/TerminalShell"

/**
 * /chart — the full-viewport workspace: pro chart + drawing tools, live order book,
 * mode-aware trade ticket, positions/history dock, and the AI layer.
 *
 * Was /terminal, and absorbed the old "Markets" section, which was a strictly worse
 * subset of this (a second chart implementation, fewer tools). Two nav items that both
 * meant "look at the price" asked users to learn a distinction the product doesn't make.
 *
 * `useMarketData()` owns the app WebSocket here because this route sits outside the
 * (app) shell that otherwise holds it — the two never render at once, so there is
 * always exactly one socket.
 */
export default function ChartPage() {
    useMarketData()
    return <TerminalShell />
}
