/**
 * Market-activity display model for GET /api/pulse.
 *
 * Two independent facts arrive and must STAY independent in the UI:
 *   - `hour`  — how active this UTC hour has HISTORICALLY been (measured over 24
 *     months of 1m bars). Past tense, sourced, auditable.
 *   - `now`   — this tick's live tradability spread from the signal engine.
 *
 * The rules this module exists to enforce:
 *   1. Never render a forecast. There is no "expected", no countdown, no next-hour
 *      claim — the backend does not send one and this must not invent one.
 *   2. A dead signal plane must never look like a calm market. Unknown is rendered
 *      as unknown, with the reason, in a neutral tone that cannot be mistaken for
 *      "conditions are quiet".
 *   3. Numbers keep their provenance. The tooltip states the sample behind the rank
 *      so a user (or an auditor) can check the claim.
 */

export type PulseNow =
    | {
        available: true
        age_ms: number
        symbols_scored: number
        symbols_vetoed: number
        tradability_max: number
        tradability_median: number
    }
    | { available: false; reason: string; age_ms?: number }

export type PulseHour =
    | {
        hour_utc: number
        rank: number
        of: number
        score: number
        in_top_window: boolean
        top_window_utc: number[]
        sample: {
            bars?: number
            symbols?: string[]
            from_ms?: number
            to_ms?: number
            metric?: string
            per_year_agreement?: Record<string, number>
        }
        caveat?: string
    }
    | { available: false; reason: string }

export type PulseResponse = { now: PulseNow; hour: PulseHour }

/** Neutral = unknown/absent. Never use a positive tone for missing data. */
export type ActivityTone = "peak" | "active" | "quiet" | "neutral"

export type ActivityDisplay = {
    /** Short strip label, e.g. "Activity". */
    label: string
    /** The measured rank, e.g. "#1/24" — or "—" when unknown. */
    rank: string
    /** Live tradability summary, e.g. "live 71" — or "" when the plane is down. */
    live: string
    tone: ActivityTone
    /** Full hover text: the claim, its sample, and the caveat. */
    title: string
}

const REASON_TEXT: Record<string, string> = {
    signal_plane_unavailable: "signal plane not reachable",
    no_pulse_published: "no pulse published yet",
    pulse_stale: "last pulse is stale",
    profile_unavailable: "activity profile not shipped",
}

function reasonText(reason: string): string {
    return REASON_TEXT[reason] ?? reason.replace(/_/g, " ")
}

function isoDay(ms?: number): string | null {
    if (typeof ms !== "number" || !Number.isFinite(ms) || ms <= 0) return null
    const d = new Date(ms)
    return Number.isNaN(d.getTime()) ? null : d.toISOString().slice(0, 10)
}

/**
 * Fold the API response into something renderable, degrading honestly.
 * `null` (request failed) is treated exactly like an unavailable plane: unknown.
 */
export function describeActivity(res: PulseResponse | null): ActivityDisplay {
    const hour = res?.hour
    const now = res?.now

    const hourKnown = !!hour && !("available" in hour && hour.available === false)
    const nowKnown = !!now && now.available === true

    let rank = "—"
    let tone: ActivityTone = "neutral"
    const titleParts: string[] = []

    if (hourKnown) {
        const h = hour as Exclude<PulseHour, { available: false; reason: string }>
        rank = `#${h.rank}/${h.of}`
        // Tone reflects the MEASURED past only. Top-6 is the window the data marks
        // out; rank 1-2 is the pair that stood clear of it.
        tone = h.rank <= 2 ? "peak" : h.in_top_window ? "active" : "quiet"

        const from = isoDay(h.sample?.from_ms)
        const to = isoDay(h.sample?.to_ms)
        const bars = typeof h.sample?.bars === "number" ? h.sample.bars.toLocaleString() : null
        const span = from && to ? `${from} to ${to}` : null
        titleParts.push(
            `This UTC hour (${String(h.hour_utc).padStart(2, "0")}:00) has historically been the ` +
            `${ordinal(h.rank)} most active of ${h.of}` +
            (bars || span
                ? ` — measured over ${[bars && `${bars} 1m bars`, span].filter(Boolean).join(", ")}`
                : "") +
            "."
        )
        if (h.sample?.symbols?.length) titleParts.push(`Symbols: ${h.sample.symbols.join(", ")}.`)
        titleParts.push(h.caveat ?? "Backward-looking measurement, not a forecast.")
    } else {
        const reason = hour && "reason" in hour ? hour.reason : "unavailable"
        titleParts.push(`Historical activity rank unavailable (${reasonText(reason)}).`)
    }

    let live = ""
    if (nowKnown) {
        const n = now as Extract<PulseNow, { available: true }>
        live = `live ${n.tradability_max}`
        titleParts.push(
            `Right now: max tradability ${n.tradability_max}, median ${n.tradability_median} ` +
            `across ${n.symbols_scored} symbol(s)` +
            (n.symbols_vetoed > 0 ? `, ${n.symbols_vetoed} vetoed` : "") + "."
        )
    } else {
        const reason = now && "reason" in now ? now.reason : "unavailable"
        // Deliberately NOT folded into the tone: an absent plane is unknown, and a
        // quiet-looking badge would be a lie about live conditions.
        titleParts.push(`Live conditions unknown — ${reasonText(reason)}.`)
    }

    return { label: "Activity", rank, live, tone, title: titleParts.join(" ") }
}

function ordinal(n: number): string {
    const rem100 = n % 100
    if (rem100 >= 11 && rem100 <= 13) return `${n}th`
    switch (n % 10) {
        case 1: return `${n}st`
        case 2: return `${n}nd`
        case 3: return `${n}rd`
        default: return `${n}th`
    }
}
