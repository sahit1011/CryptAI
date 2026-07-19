/**
 * AI-on-chart lifecycle manager — the handshake grammar.
 *
 *   PROPOSED  — a setup plotted from the cards: dashed aiTradeLevel group
 *               `ai-<signalId>` (entry --info, stop --loss, TPs --profit).
 *   LIVE      — open positions draw their own SOLID level group `pos-<id>`,
 *               synced from position frames.
 *   CLOSED    — the group is removed. The chart never shows dead levels.
 *
 * Focus rule: ONE plotted setup at a time — plotting a new one sweeps the old.
 * Hover linking: dock-row hover re-plots the position group at full opacity
 * (others stay dimmed via extendData.opacity — v1 keeps all at 1).
 *
 * Pure mapping (`signalLevels`, `positionLevels`) is unit-tested; the manager
 * is a thin veneer over chart.createOverlay/removeOverlay.
 */
import type { Chart } from "klinecharts"
import type { Signal, Trade } from "@/store/useStore"
import type { ChartPalette } from "./tokens"
import type { AiLevelData } from "./overlays"

export interface PlotLevel {
    value: number
    data: AiLevelData
}

function pct(from: number, to: number): string {
    if (!Number.isFinite(from) || from === 0 || !Number.isFinite(to)) return ""
    const p = ((to - from) / from) * 100
    return `${p >= 0 ? "+" : "−"}${Math.abs(p).toFixed(1)}%`
}

function fmt(n: number): string {
    return n.toLocaleString("en-US", { maximumFractionDigits: 2 })
}

/** A PROPOSED setup's dashed levels. Pure. */
export function signalLevels(signal: Signal, palette: ChartPalette): PlotLevel[] {
    const levels: PlotLevel[] = []
    if (Number.isFinite(signal.entry) && signal.entry > 0) {
        levels.push({
            value: signal.entry,
            data: { label: `AI ENTRY ${fmt(signal.entry)}`, color: palette.info, lineStyle: "dashed" },
        })
    }
    if (Number.isFinite(signal.stopLoss) && signal.stopLoss > 0) {
        levels.push({
            value: signal.stopLoss,
            data: { label: `STOP ${pct(signal.entry, signal.stopLoss)}`, color: palette.loss, lineStyle: "dashed" },
        })
    }
    signal.takeProfits.forEach((tp, i) => {
        if (!Number.isFinite(tp) || tp <= 0) return
        levels.push({
            value: tp,
            data: { label: `TP${i + 1} ${pct(signal.entry, tp)}`, color: palette.profit, lineStyle: "dashed" },
        })
    })
    return levels
}

/** A LIVE position's solid levels. Pure. */
export function positionLevels(trade: Trade, palette: ChartPalette): PlotLevel[] {
    const levels: PlotLevel[] = []
    if (Number.isFinite(trade.entry) && trade.entry > 0) {
        levels.push({
            value: trade.entry,
            data: { label: `${trade.side} ${fmt(trade.entry)}`, color: palette.info, lineStyle: "solid" },
        })
    }
    if (trade.stopLoss != null && Number.isFinite(trade.stopLoss) && trade.stopLoss > 0) {
        levels.push({
            value: trade.stopLoss,
            data: { label: `SL ${fmt(trade.stopLoss)}`, color: palette.loss, lineStyle: "solid" },
        })
    }
    if (trade.takeProfit != null && Number.isFinite(trade.takeProfit) && trade.takeProfit > 0) {
        levels.push({
            value: trade.takeProfit,
            data: { label: `TP ${fmt(trade.takeProfit)}`, color: palette.profit, lineStyle: "solid" },
        })
    }
    return levels
}

export const AI_GROUP_PREFIX = "ai-"
export const POS_GROUP_PREFIX = "pos-"

export class PlotManager {
    private chart: Chart
    private palette: ChartPalette
    private plottedSignalGroup: string | null = null
    private positionGroups = new Set<string>()

    constructor(chart: Chart, palette: ChartPalette) {
        this.chart = chart
        this.palette = palette
    }

    /** Plot a PROPOSED setup (sweeps any previously plotted one — focus rule). */
    plotSignal(signal: Signal): void {
        this.clearSignal()
        const levels = signalLevels(signal, this.palette)
        if (levels.length === 0) return
        const groupId = `${AI_GROUP_PREFIX}${signal.id}`
        this.chart.createOverlay(
            levels.map((l) => ({
                name: "aiTradeLevel",
                groupId,
                lock: true,
                points: [{ value: l.value }],
                extendData: l.data,
            })),
        )
        this.plottedSignalGroup = groupId
    }

    clearSignal(): void {
        if (this.plottedSignalGroup) {
            this.chart.removeOverlay({ groupId: this.plottedSignalGroup })
            this.plottedSignalGroup = null
        }
    }

    /** Sync LIVE position level groups to the current open positions for a symbol. */
    syncPositions(trades: Trade[], symbol: string): void {
        const open = trades.filter((t) => t.status === "OPEN" && t.symbol === symbol)
        const wanted = new Set(open.map((t) => `${POS_GROUP_PREFIX}${t.id}`))

        // Remove groups whose position closed (the chart never shows dead levels).
        for (const groupId of this.positionGroups) {
            if (!wanted.has(groupId)) {
                this.chart.removeOverlay({ groupId })
                this.positionGroups.delete(groupId)
            }
        }

        // Draw groups for newly-live positions (levels are static per position:
        // entry/SL/TP don't move, so no need to re-draw existing groups per frame).
        for (const trade of open) {
            const groupId = `${POS_GROUP_PREFIX}${trade.id}`
            if (this.positionGroups.has(groupId)) continue
            const levels = positionLevels(trade, this.palette)
            if (levels.length === 0) continue
            this.chart.createOverlay(
                levels.map((l) => ({
                    name: "aiTradeLevel",
                    groupId,
                    lock: true,
                    points: [{ value: l.value }],
                    extendData: l.data,
                })),
            )
            this.positionGroups.add(groupId)
        }
    }

    /** Full teardown (symbol switch / unmount). */
    clearAll(): void {
        this.clearSignal()
        for (const groupId of this.positionGroups) this.chart.removeOverlay({ groupId })
        this.positionGroups.clear()
    }
}
