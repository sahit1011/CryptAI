/**
 * CryptAI klinecharts theme — the DESK's canvas contract.
 *
 * Built at mount time from live design tokens (resolved to rgb — canvas can't
 * parse oklch). Candles/wicks speak the untouchable trading semantics
 * (--profit emerald / --loss red); the ONE structural crimson mark on the canvas
 * is the crosshair (accent-400 dashed lines, accent-500 label chips). Grid is
 * horizontal-only hairlines; the canvas itself is transparent — the container
 * div owns the background.
 *
 * Shape is a DeepPartial<Styles> merged over klinecharts' built-in 'dark'
 * template via chart.setStyles.
 */
import { chartPalette, withAlpha } from "./tokens"

const MONO = "var(--font-geist-mono), ui-monospace, monospace"

export function buildChartStyles() {
    const p = chartPalette()
    return {
        grid: {
            show: true,
            horizontal: { show: true, size: 1, color: withAlpha(p.foreground, 0.05), style: "solid" as const },
            vertical: { show: false },
        },
        candle: {
            type: "candle_solid" as const,
            bar: {
                upColor: p.profit,
                downColor: p.loss,
                noChangeColor: p.subtleFg,
                upBorderColor: p.profit,
                downBorderColor: p.loss,
                noChangeBorderColor: p.subtleFg,
                upWickColor: p.profit,
                downWickColor: p.loss,
                noChangeWickColor: p.subtleFg,
            },
            priceMark: {
                show: true,
                high: { show: true, color: p.subtleFg, textSize: 10, textFamily: MONO },
                low: { show: true, color: p.subtleFg, textSize: 10, textFamily: MONO },
                last: {
                    show: true,
                    upColor: p.profit,
                    downColor: p.loss,
                    noChangeColor: p.subtleFg,
                    line: { show: true, style: "dashed" as const, dashedValue: [4, 4], size: 1 },
                    text: {
                        show: true, size: 10, family: MONO, weight: "normal",
                        color: "#ffffff", borderRadius: 2,
                        paddingLeft: 4, paddingRight: 4, paddingTop: 2, paddingBottom: 2,
                    },
                },
            },
            tooltip: {
                showRule: "follow_cross" as const,
                showType: "standard" as const,
                title: { show: false, template: "" },
                legend: {
                    color: p.mutedFg,
                    size: 11,
                    family: MONO,
                    template: [
                        { title: "O", value: "{open}" },
                        { title: "H", value: "{high}" },
                        { title: "L", value: "{low}" },
                        { title: "C", value: "{close}" },
                        { title: "Vol", value: "{volume}" },
                    ],
                },
            },
        },
        indicator: {
            ohlc: { upColor: p.profit, downColor: p.loss, noChangeColor: p.subtleFg },
            bars: [{
                style: "fill" as const, borderStyle: "solid" as const, borderSize: 1, borderDashedValue: [2, 2],
                upColor: withAlpha(p.profit, 0.45), downColor: withAlpha(p.loss, 0.45), noChangeColor: p.subtleFg,
            }],
            lines: [
                { style: "solid" as const, smooth: false, size: 1, dashedValue: [2, 2], color: p.warning },
                { style: "solid" as const, smooth: false, size: 1, dashedValue: [2, 2], color: p.info },
                { style: "solid" as const, smooth: false, size: 1, dashedValue: [2, 2], color: p.accent300 },
                { style: "solid" as const, smooth: false, size: 1, dashedValue: [2, 2], color: p.profit },
                { style: "solid" as const, smooth: false, size: 1, dashedValue: [2, 2], color: p.mutedFg },
            ],
            tooltip: { legend: { color: p.mutedFg, size: 11, family: MONO } },
        },
        xAxis: {
            axisLine: { show: true, color: p.hairline, size: 1 },
            tickText: { show: true, color: p.subtleFg, size: 11, family: MONO, weight: "normal" },
            tickLine: { show: false },
        },
        yAxis: {
            axisLine: { show: true, color: p.hairline, size: 1 },
            tickText: { show: true, color: p.subtleFg, size: 11, family: MONO, weight: "normal" },
            tickLine: { show: false },
        },
        separator: { size: 1, color: p.hairline, fill: true, activeBackgroundColor: withAlpha(p.accent500, 0.12) },
        crosshair: {
            show: true,
            horizontal: {
                show: true,
                line: { show: true, style: "dashed" as const, dashedValue: [4, 2], size: 1, color: withAlpha(p.accent400, 0.5) },
                text: {
                    show: true, size: 10, family: MONO, weight: "normal", color: "#ffffff",
                    borderRadius: 2, borderSize: 0, borderColor: p.accent500,
                    paddingLeft: 4, paddingRight: 4, paddingTop: 2, paddingBottom: 2,
                    backgroundColor: p.accent500,
                },
            },
            vertical: {
                show: true,
                line: { show: true, style: "dashed" as const, dashedValue: [4, 2], size: 1, color: withAlpha(p.accent400, 0.5) },
                text: {
                    show: true, size: 10, family: MONO, weight: "normal", color: "#ffffff",
                    borderRadius: 2, borderSize: 0, borderColor: p.accent500,
                    paddingLeft: 4, paddingRight: 4, paddingTop: 2, paddingBottom: 2,
                    backgroundColor: p.accent500,
                },
            },
        },
        // User drawings (the tool rail). Neutral ink so they never fight AI levels.
        overlay: {
            point: { color: p.accent400, borderColor: withAlpha(p.accent400, 0.35), borderSize: 1, radius: 4, activeColor: p.accent300, activeBorderColor: withAlpha(p.accent300, 0.35), activeBorderSize: 1, activeRadius: 5 },
            line: { style: "solid" as const, smooth: false, color: p.mutedFg, size: 1, dashedValue: [2, 2] },
            rect: { style: "fill" as const, color: withAlpha(p.mutedFg, 0.12), borderColor: p.mutedFg, borderSize: 1, borderRadius: 0, borderStyle: "solid" as const, borderDashedValue: [2, 2] },
            polygon: { style: "fill" as const, color: withAlpha(p.mutedFg, 0.12), borderColor: p.mutedFg, borderSize: 1, borderStyle: "solid" as const, borderDashedValue: [2, 2] },
            circle: { style: "fill" as const, color: withAlpha(p.mutedFg, 0.12), borderColor: p.mutedFg, borderSize: 1, borderStyle: "solid" as const, borderDashedValue: [2, 2] },
            arc: { style: "solid" as const, color: p.mutedFg, size: 1, dashedValue: [2, 2] },
            text: { style: "fill" as const, color: "#ffffff", size: 11, family: MONO, weight: "normal", borderStyle: "solid" as const, borderDashedValue: [2, 2], borderSize: 0, borderRadius: 2, borderColor: p.elevated, paddingLeft: 4, paddingRight: 4, paddingTop: 2, paddingBottom: 2, backgroundColor: p.elevated },
        },
    }
}
