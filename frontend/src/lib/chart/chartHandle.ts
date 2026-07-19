/**
 * Shared imperative handle to the live terminal chart.
 *
 * The chart is a canvas instance owned by ChartPanel; the drawing rail and the
 * AI setup cards need to call it imperatively (createOverlay, plotSignal…)
 * without threading refs through the tree or putting a mutable class in React
 * state. Module-level holder + readiness listeners — same doctrine as klineBus:
 * imperative chart traffic stays out of React.
 */
import type { Chart } from "klinecharts"
import type { PlotManager } from "./plotSetup"

interface Handle {
    chart: Chart | null
    plot: PlotManager | null
}

const handle: Handle = { chart: null, plot: null }
const listeners = new Set<(ready: boolean) => void>()

export function setChartHandle(chart: Chart | null, plot: PlotManager | null): void {
    handle.chart = chart
    handle.plot = plot
    for (const l of listeners) {
        try { l(chart != null) } catch { /* ignore */ }
    }
}

export function getChart(): Chart | null {
    return handle.chart
}

export function getPlotManager(): PlotManager | null {
    return handle.plot
}

/** Subscribe to chart readiness (rail buttons enable/disable). */
export function onChartReady(listener: (ready: boolean) => void): () => void {
    listeners.add(listener)
    listener(handle.chart != null)
    return () => { listeners.delete(listener) }
}
