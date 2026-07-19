/**
 * Design-token → canvas-color bridge for the terminal chart.
 *
 * The app's tokens are authored in oklch (plus color-mix). klinecharts paints on
 * canvas and expects rgb/hex strings — feeding it `var(--x)` or raw oklch either
 * fails silently or throws. Same trick as the dashboard's ChartWidget: let the
 * browser normalize by applying the var to a throwaway element and reading back
 * getComputedStyle().color (always rgb/rgba).
 *
 * Every fallback below is the token's real value pre-resolved to rgb, so SSR and
 * very-early calls still paint on-brand.
 */

export function token(name: string, fallback: string): string {
    if (typeof window === "undefined") return fallback
    try {
        const el = document.createElement("div")
        el.style.color = `var(${name})`
        el.style.display = "none"
        document.body.appendChild(el)
        const rgb = getComputedStyle(el).color
        document.body.removeChild(el)
        return rgb && rgb.startsWith("rgb") ? rgb : fallback
    } catch {
        return fallback
    }
}

/** rgb()/rgba() string → rgba() at the given alpha (for fills/dimmed lines). */
export function withAlpha(rgb: string, alpha: number): string {
    const m = rgb.match(/rgba?\(([^)]+)\)/)
    if (!m) return rgb
    const [r, g, b] = m[1].split(",").map((s) => s.trim())
    return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

/** The terminal chart's palette, resolved once per mount (client-only). */
export function chartPalette() {
    return {
        profit: token("--profit", "rgb(52, 211, 153)"),
        loss: token("--loss", "rgb(239, 88, 66)"),
        info: token("--info", "rgb(96, 165, 250)"),
        warning: token("--warning", "rgb(245, 179, 66)"),
        accent300: token("--accent-300", "rgb(236, 116, 95)"),
        accent400: token("--accent-400", "rgb(219, 81, 61)"),
        accent500: token("--accent-500", "rgb(196, 51, 38)"),
        foreground: token("--foreground", "rgb(246, 246, 246)"),
        mutedFg: token("--muted-foreground", "rgb(150, 150, 150)"),
        subtleFg: token("--subtle-foreground", "rgb(104, 104, 104)"),
        border: token("--border-strong", "rgba(255, 255, 255, 0.14)"),
        hairline: token("--border", "rgba(255, 255, 255, 0.08)"),
        elevated: token("--elevated", "rgb(23, 23, 23)"),
    }
}

export type ChartPalette = ReturnType<typeof chartPalette>
