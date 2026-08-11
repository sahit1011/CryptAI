import { isCapacityDown, type SessionOverview, type TradingSession } from "@/lib/api";

/*
 * Pure session-UI logic, kept out of components so it is unit-testable
 * (the vitest suite covers lib logic, not rendering).
 */

/** What the session panel should render. Ended sessions come back as
 * `session: null` from the API (get_active filters them), so "idle" vs
 * "exhausted" is decided by today's remaining quota. */
export type SessionPhase =
    | "idle"          // no session, quota available — show Start
    | "blocked"       // analysis capacity down — nothing can be started, quota is safe
    | "exhausted"     // no session, no time left today — show reset hint
    | "scanning"      // metered analysis running — show timer
    | "proposal"      // clock paused, a setup awaits the user's decision
    | "executing";    // approval in flight

export function sessionPhase(overview: SessionOverview): SessionPhase {
    // Preflight outranks quota: with analysis down there is nothing to start, so
    // "you're out of time today" is the wrong answer and hides the real cause.
    // A session that is already live keeps its own phase — deciding on a pending
    // plan, or watching an execution land, needs no capacity.
    const startable = (): SessionPhase =>
        isCapacityDown(overview)
            ? "blocked"
            : overview.remaining_today_seconds > 0
              ? "idle"
              : "exhausted";
    const s = overview.session;
    if (!s) return startable();
    switch (s.status) {
        case "scanning":
            return "scanning";
        case "setup_proposed":
            return "proposal";
        case "executing":
            return "executing";
        default:
            return startable();
    }
}

/** True when the UI must stop claiming the agents are working: no cycle has reported
 * for longer than two expected cycles. A scanning session that has not reported yet is
 * judged against `started_at` with one cycle of grace — the first sweep takes time.
 *
 * Only `scanning` can be stale: everywhere else the clock is deliberately paused, so
 * silence is expected rather than evidence of a dead engine. Missing or unparsable
 * timestamps and a non-positive cycle length read as NOT stale — the honest failure
 * here is saying nothing, not accusing a live engine of being dead. */
export function isHeartbeatStale(
    session: TradingSession | null | undefined,
    now: Date = new Date(),
): boolean {
    if (!session || session.status !== "scanning") return false;
    const cycle = session.expected_cycle_seconds;
    if (!Number.isFinite(cycle) || cycle <= 0) return false;
    const [mark, budgetSeconds] = session.last_cycle_at
        ? [session.last_cycle_at, 2 * cycle]
        : [session.started_at, cycle];
    if (!mark) return false;
    const t = Date.parse(mark);
    if (Number.isNaN(t)) return false;
    return now.getTime() - t > budgetSeconds * 1000;
}

/** The auditable figures behind the scan receipt. Seconds; the caller formats them.
 *
 * NOT derivable from the session payload, so deliberately absent: how many plans were
 * shown and how many were taken. Those live in `proposals` / `session_events`, not on
 * `TradingSession` — a receipt line must never be guessed. */
export interface ScanReceipt {
    /** Metered seconds charged for this scan. Refunds are already deducted server-side
     * (`elapsed_seconds` derives from `metered_seconds_accrued`). */
    chargedSeconds: number;
    /** Wall time inside the scan that was NOT charged — the clock paused while deciding,
     * or paused on a stale heartbeat. null when `started_at` is missing: not derivable,
     * so the line is dropped rather than invented. */
    freeSeconds: number | null;
    /** Seconds returned to the balance after a mid-scan capacity loss. A subset of
     * `freeSeconds`, not an addition to it. */
    refundedSeconds: number;
    /** Today's balance after this scan. Lives on the overview, not the session, so the
     * caller passes it; null when unknown. */
    remainingTodaySeconds: number | null;
}

/** Receipt figures for a scan (pass the ended session returned by `endSession`, or the
 * live one for an in-flight total). Returns null when there is no session to account
 * for. `now` only matters while the session is still running. */
export function scanReceipt(
    session: TradingSession | null | undefined,
    remainingTodaySeconds?: number | null,
    now: Date = new Date(),
): ScanReceipt | null {
    if (!session) return null;
    const charged = Math.max(0, Math.floor(session.elapsed_seconds || 0));
    const start = session.started_at ? Date.parse(session.started_at) : NaN;
    const end = session.ended_at ? Date.parse(session.ended_at) : now.getTime();
    const spanKnown = !Number.isNaN(start) && !Number.isNaN(end);
    return {
        chargedSeconds: charged,
        freeSeconds: spanKnown ? Math.max(0, Math.round((end - start) / 1000) - charged) : null,
        refundedSeconds: Math.max(0, session.seconds_refunded || 0),
        remainingTodaySeconds: remainingTodaySeconds ?? null,
    };
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
