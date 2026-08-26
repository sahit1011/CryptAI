import { describe, expect, it } from "vitest"
import { describeActivity, type PulseResponse } from "./pulse"

const SAMPLE = {
    bars: 3_153_600,
    symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    from_ms: Date.UTC(2024, 7, 1),
    to_ms: Date.UTC(2026, 6, 31),
    metric: "z-scores of volume and range",
    per_year_agreement: { "2024": 5.67, "2025": 6.0 },
}

function res(over: Partial<PulseResponse> = {}): PulseResponse {
    return {
        now: {
            available: true, age_ms: 3_000, symbols_scored: 3, symbols_vetoed: 1,
            tradability_max: 71, tradability_median: 42,
        },
        hour: {
            hour_utc: 14, rank: 1, of: 24, score: 2.697, in_top_window: true,
            top_window_utc: [13, 14, 15, 16, 17, 18], sample: SAMPLE,
            caveat: "Backward-looking measurement, not a forecast.",
        },
        ...over,
    }
}

describe("describeActivity", () => {
    it("renders the measured rank with its live companion", () => {
        const d = describeActivity(res())
        expect(d.rank).toBe("#1/24")
        expect(d.live).toBe("live 71")
        expect(d.tone).toBe("peak")
    })

    it("states the claim in the PAST tense and cites the sample", () => {
        const { title } = describeActivity(res())
        expect(title).toContain("has historically been the 1st most active of 24")
        expect(title).toContain("3,153,600 1m bars")
        expect(title).toContain("2024-08-01 to 2026-07-31")
        expect(title).toContain("not a forecast")
    })

    it("never implies a forecast anywhere in the output", () => {
        const d = describeActivity(res())
        const all = `${d.label} ${d.rank} ${d.live} ${d.title}`.toLowerCase()
        for (const word of ["will be", "expected", "forecast:", "next hour", "predict", "upcoming"]) {
            expect(all).not.toContain(word)
        }
    })

    it("tones down outside the measured window", () => {
        expect(describeActivity(res({
            hour: {
                hour_utc: 5, rank: 24, of: 24, score: -0.957, in_top_window: false,
                top_window_utc: [13, 14, 15, 16, 17, 18], sample: SAMPLE,
            },
        })).tone).toBe("quiet")

        expect(describeActivity(res({
            hour: {
                hour_utc: 16, rank: 3, of: 24, score: 1.349, in_top_window: true,
                top_window_utc: [13, 14, 15, 16, 17, 18], sample: SAMPLE,
            },
        })).tone).toBe("active")
    })

    it("a dead signal plane reads UNKNOWN, never quiet", () => {
        const d = describeActivity(res({ now: { available: false, reason: "pulse_stale" } }))
        expect(d.live).toBe("")                       // no fabricated live number
        expect(d.title).toContain("Live conditions unknown")
        expect(d.title).toContain("last pulse is stale")
        // The measured rank still stands — it needs no live plane.
        expect(d.rank).toBe("#1/24")
        expect(d.tone).toBe("peak")
    })

    it("distinguishes WHY live data is missing", () => {
        for (const [reason, text] of [
            ["signal_plane_unavailable", "signal plane not reachable"],
            ["no_pulse_published", "no pulse published yet"],
        ] as const) {
            const d = describeActivity(res({ now: { available: false, reason } }))
            expect(d.title).toContain(text)
        }
    })

    it("a missing profile yields a dash and a neutral tone, not a guess", () => {
        const d = describeActivity(res({
            hour: { available: false, reason: "profile_unavailable" },
        }))
        expect(d.rank).toBe("—")
        expect(d.tone).toBe("neutral")
        expect(d.title).toContain("activity profile not shipped")
    })

    it("a failed request degrades to fully unknown without throwing", () => {
        const d = describeActivity(null)
        expect(d.rank).toBe("—")
        expect(d.live).toBe("")
        expect(d.tone).toBe("neutral")
        expect(d.title).toContain("unavailable")
    })

    it("ordinals read correctly for the awkward ranks", () => {
        const rankTitle = (rank: number) => describeActivity(res({
            hour: {
                hour_utc: 1, rank, of: 24, score: 0, in_top_window: false,
                top_window_utc: [], sample: SAMPLE,
            },
        })).title
        expect(rankTitle(2)).toContain("2nd most active")
        expect(rankTitle(3)).toContain("3rd most active")
        expect(rankTitle(11)).toContain("11th most active")
        expect(rankTitle(21)).toContain("21st most active")
    })
})
