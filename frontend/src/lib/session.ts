import type { SessionOverview } from "@/lib/api";

/*
 * Pure session-UI logic, kept out of components so it is unit-testable
 * (the vitest suite covers lib logic, not rendering).
 */

/** What the session panel should render. Ended sessions come back as
 * `session: null` from the API (get_active filters them), so "idle" vs
 * "exhausted" is decided by today's remaining quota. */
export type SessionPhase =
    | "idle"          // no session, quota available — show Start
    | "exhausted"     // no session, no time left today — show reset hint
    | "scanning"      // metered analysis running — show timer
    | "proposal"      // clock paused, a setup awaits the user's decision
    | "executing";    // approval in flight

export function sessionPhase(overview: SessionOverview): SessionPhase {
    const s = overview.session;
    if (!s) return overview.remaining_today_seconds > 0 ? "idle" : "exhausted";
    switch (s.status) {
        case "scanning":
            return "scanning";
        case "setup_proposed":
            return "proposal";
        case "executing":
            return "executing";
        default:
            return overview.remaining_today_seconds > 0 ? "idle" : "exhausted";
    }
}

/** 90 -> "1:30", 3661 -> "1:01:01". Never negative. */
export function formatClock(totalSeconds: number): string {
    const s = Math.max(0, Math.floor(totalSeconds));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    const mm = h > 0 ? String(m).padStart(2, "0") : String(m);
    const ss = String(sec).padStart(2, "0");
    return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

/** Whole seconds until a proposal's shelf life lapses; 0 once past (never negative). */
export function shelfLifeSeconds(expiresAt: string | null, now: Date = new Date()): number {
    if (!expiresAt) return 0;
    const t = Date.parse(expiresAt);
    if (Number.isNaN(t)) return 0;
    return Math.max(0, Math.floor((t - now.getTime()) / 1000));
}

/** A 409 refusal whose proposal is still live invites a retry ("price moved — you can
 * retry or reject"); terminal refusals do not. The backend encodes this in the detail. */
export function isRetryableRefusal(message: string): boolean {
    return /retry/i.test(message);
}
