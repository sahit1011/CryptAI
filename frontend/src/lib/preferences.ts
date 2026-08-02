import type { GoalHorizon, RiskAppetite, TradingPreferences } from "@/lib/api";

/*
 * Pure preferences logic — the trading-persona form's model, kept out of React so it
 * is unit-tested. The backend clamps risk fields to the plan; this layer only shapes
 * input and computes the minimal diff to send.
 */

export interface TradingStyle {
    value: GoalHorizon;
    label: string;
    blurb: string;
}

/** The four trading styles (the "channels" of the vision) as a persistent default. */
export const TRADING_STYLES: TradingStyle[] = [
    { value: "scalp", label: "Scalp", blurb: "Minutes. Many small, fast trades." },
    { value: "intraday", label: "Intraday", blurb: "Hours. In and out within the day." },
    { value: "swing", label: "Swing", blurb: "Days. Ride a multi-session move." },
    { value: "position", label: "Position", blurb: "Weeks. Fewer, larger convictions." },
];

export const RISK_APPETITES: { value: RiskAppetite; label: string }[] = [
    { value: "conservative", label: "Conservative" },
    { value: "moderate", label: "Moderate" },
    { value: "aggressive", label: "Aggressive" },
];

/** Parse a free-text symbol list ("btc, eth  sol") into a normalized, de-duped universe.
 * Empty input returns null (meaning "use the platform default"), never an empty array. */
export function parseSymbolUniverse(raw: string): string[] | null {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const token of raw.split(/[\s,]+/)) {
        let s = token.trim().toUpperCase();
        if (!s) continue;
        // Accept "BTC" or "BTCUSDT"; normalize a bare base to the USDT perp symbol.
        if (!/USDT?$/.test(s) && /^[A-Z0-9]{2,15}$/.test(s)) s = `${s}USDT`;
        if (!seen.has(s)) {
            seen.add(s);
            out.push(s);
        }
    }
    return out.length ? out : null;
}

/** Render a symbol universe back to editable text; null → empty string. */
export function symbolUniverseText(universe: string[] | null | undefined): string {
    return (universe ?? []).join(", ");
}

/** Fields whose display differs from the underlying value (percent vs fraction). */
export function toPercent(fraction: number): number {
    return Math.round(fraction * 1000) / 10; // 0.65 -> 65 (1 dp)
}

export function fromPercent(percent: number): number {
    return Math.round((percent / 100) * 10000) / 10000;
}

/** Only the fields that actually changed, so a partial POST never re-sends (and never
 * re-clamps) untouched values. Compares arrays by content, not reference. */
export function changedFields(
    original: TradingPreferences,
    edited: Partial<TradingPreferences>,
): Partial<TradingPreferences> {
    const out: Partial<TradingPreferences> = {};
    for (const key of Object.keys(edited) as (keyof TradingPreferences)[]) {
        const a = original[key];
        const b = edited[key];
        if (Array.isArray(a) || Array.isArray(b)) {
            if (JSON.stringify(a ?? null) !== JSON.stringify(b ?? null)) {
                (out[key] as unknown) = b;
            }
        } else if (a !== b) {
            (out[key] as unknown) = b;
        }
    }
    return out;
}
