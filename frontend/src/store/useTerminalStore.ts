import { create } from "zustand"
import { persist, createJSONStorage } from "zustand/middleware"

/**
 * Terminal-route state — the DESK's own slice, separate from the dashboard's
 * `trading-dashboard-storage`. Persists workspace ergonomics (symbol, timeframe,
 * dock, tools, indicators) so a trader's desk looks the same every session.
 * Live market/ticket data is intentionally NOT persisted.
 */

export interface TickerStats {
    last: number
    pctChange: number
    open?: number
    high?: number
    low?: number
    volume?: number
    quoteVolume?: number
    /** Data provenance the UI must disclose: live WS or REST poll. */
    source: "ws" | "poll"
    at: number
}

export interface TicketPrefill {
    direction?: "LONG" | "SHORT"
    entry?: number
    stopLoss?: number
    takeProfits?: number[]
    /** When set, the ticket is loading a specific AI setup (enables lifecycle link). */
    signalId?: string
    /** The AI setup's model confidence — passed through so machine-proposed
     *  brackets stay gated by the risk calculator's confidence floor. */
    confidence?: number
}

export type DockTab = "positions" | "orders" | "history" | "setups" | "wire"

interface TerminalState {
    symbol: string
    setSymbol: (symbol: string) => void

    interval: string
    setInterval: (interval: string) => void

    dockHeight: number
    setDockHeight: (h: number) => void
    dockTab: DockTab
    setDockTab: (t: DockTab) => void
    isDockCollapsed: boolean
    toggleDockCollapsed: () => void

    activeIndicators: string[]
    toggleIndicator: (name: string) => void

    isMagnetOn: boolean
    toggleMagnet: () => void
    isContinuousDrawing: boolean
    toggleContinuousDrawing: () => void

    /** Per-symbol 24h stats (WS for BTC, /api/ticker poll for the rest). */
    tickers: Record<string, TickerStats>
    setTickerStats: (symbol: string, stats: TickerStats) => void

    ticketPrefill: TicketPrefill | null
    setTicketPrefill: (p: TicketPrefill | null) => void

    /** Signal id currently plotted on the chart (focus rule: one per symbol). */
    plottedSignalId: string | null
    setPlottedSignalId: (id: string | null) => void

    /** Position id whose chart lines are hover-brightened from the dock. */
    hoveredPositionId: string | null
    setHoveredPositionId: (id: string | null) => void
}

export const DOCK_MIN = 160
export const DOCK_MAX = 420
export const DOCK_DEFAULT = 240

export const useTerminalStore = create<TerminalState>()(
    persist(
        (set) => ({
            symbol: "BTCUSDT",
            setSymbol: (symbol) => set({ symbol, plottedSignalId: null }),

            interval: "15m",
            setInterval: (interval) => set({ interval }),

            dockHeight: DOCK_DEFAULT,
            setDockHeight: (h) => set({ dockHeight: Math.min(DOCK_MAX, Math.max(DOCK_MIN, Math.round(h))) }),
            dockTab: "positions",
            setDockTab: (dockTab) => set({ dockTab, isDockCollapsed: false }),
            isDockCollapsed: false,
            toggleDockCollapsed: () => set((s) => ({ isDockCollapsed: !s.isDockCollapsed })),

            activeIndicators: ["VOL"],
            toggleIndicator: (name) =>
                set((s) => ({
                    activeIndicators: s.activeIndicators.includes(name)
                        ? s.activeIndicators.filter((n) => n !== name)
                        : [...s.activeIndicators, name],
                })),

            isMagnetOn: false,
            toggleMagnet: () => set((s) => ({ isMagnetOn: !s.isMagnetOn })),
            isContinuousDrawing: false,
            toggleContinuousDrawing: () => set((s) => ({ isContinuousDrawing: !s.isContinuousDrawing })),

            tickers: {},
            setTickerStats: (symbol, stats) =>
                set((s) => ({ tickers: { ...s.tickers, [symbol]: stats } })),

            ticketPrefill: null,
            setTicketPrefill: (ticketPrefill) => set({ ticketPrefill }),

            plottedSignalId: null,
            setPlottedSignalId: (plottedSignalId) => set({ plottedSignalId }),

            hoveredPositionId: null,
            setHoveredPositionId: (hoveredPositionId) => set({ hoveredPositionId }),
        }),
        {
            name: "cryptai-terminal",
            storage: createJSONStorage(() => localStorage),
            partialize: (s) => ({
                symbol: s.symbol,
                interval: s.interval,
                dockHeight: s.dockHeight,
                dockTab: s.dockTab,
                activeIndicators: s.activeIndicators,
                isMagnetOn: s.isMagnetOn,
                isContinuousDrawing: s.isContinuousDrawing,
            }),
        },
    ),
)
