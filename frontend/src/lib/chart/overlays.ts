/**
 * Custom klinecharts overlays for the AI layer.
 *
 * `aiTradeLevel` — a horizontal price level with a left-aligned label chip and a
 * right-axis price tag. Used for every AI/position level on the canvas:
 *   entry → --info, stop → --loss, take-profits → --profit  (never crimson:
 * levels speak trading semantics, not brand).
 *
 * PROPOSED setups draw dashed; LIVE position levels draw solid — the lifecycle
 * grammar (proposed → live → gone on close) lives in plotSetup.ts; this file is
 * only the figure geometry.
 *
 * klinecharts is dynamically imported (module-scope `window` access breaks SSR),
 * so registration receives the loaded module. Safe to call repeatedly —
 * re-registering the same name just overwrites the template.
 */
import type { registerOverlay as RegisterOverlayFn } from "klinecharts"

export interface AiLevelData {
    label: string
    color: string
    /** "dashed" for PROPOSED setups, "solid" for LIVE position levels. */
    lineStyle?: "dashed" | "solid"
    /** 0–1 line alpha override (hover-linking dims unrelated groups). */
    opacity?: number
}

type KlinechartsModule = { registerOverlay: typeof RegisterOverlayFn }

let registered = false

export function registerTerminalOverlays(kc: KlinechartsModule): void {
    if (registered) return
    registered = true

    kc.registerOverlay({
        name: "aiTradeLevel",
        totalStep: 2, // one point: { value: price }
        lock: true,
        createPointFigures: ({ overlay, coordinates, bounding }) => {
            const point = coordinates[0]
            if (!point) return []
            const data = (overlay.extendData ?? {}) as AiLevelData
            const { label = "", color = "#60a5fa", lineStyle = "dashed" } = data
            const y = point.y
            return [
                {
                    type: "line",
                    attrs: { coordinates: [{ x: 0, y }, { x: bounding.width, y }] },
                    styles: {
                        style: lineStyle,
                        color,
                        size: 1,
                        dashedValue: lineStyle === "dashed" ? [4, 4] : [1, 0],
                    },
                    ignoreEvent: true,
                },
                {
                    type: "text",
                    attrs: { x: 8, y: y - 4, text: label, baseline: "bottom", align: "left" },
                    styles: {
                        color: "#ffffff",
                        size: 10,
                        family: "var(--font-geist-mono), ui-monospace, monospace",
                        backgroundColor: color,
                        paddingLeft: 5,
                        paddingRight: 5,
                        paddingTop: 2,
                        paddingBottom: 2,
                        borderRadius: 3,
                    },
                },
            ]
        },
        createYAxisFigures: ({ overlay, coordinates, bounding }) => {
            const point = coordinates[0]
            if (!point) return []
            const data = (overlay.extendData ?? {}) as AiLevelData
            const value = overlay.points[0]?.value
            return {
                type: "text",
                attrs: {
                    x: bounding.width,
                    y: point.y,
                    text: value != null ? Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 }) : "",
                    align: "right",
                    baseline: "middle",
                },
                styles: {
                    color: "#ffffff",
                    size: 10,
                    family: "var(--font-geist-mono), ui-monospace, monospace",
                    backgroundColor: data.color ?? "#60a5fa",
                    paddingLeft: 4,
                    paddingRight: 4,
                    paddingTop: 2,
                    paddingBottom: 2,
                    borderRadius: 2,
                },
            }
        },
    })
}
