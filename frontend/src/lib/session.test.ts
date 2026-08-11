import { describe, expect, it } from "vitest";

import { isCapacityDown, type SessionOverview, type TradingSession } from "@/lib/api";
import {
    formatClock,
    isHeartbeatStale,
    isRetryableRefusal,
    scanReceipt,
    sessionPhase,
    shelfLifeSeconds,
} from "@/lib/session";

function overview(partial: Partial<SessionOverview>): SessionOverview {
    return {
        session: null,
        capacity: { available: true, reason: null, eta_seconds: null },
        daily_quota_seconds: 1800,
        used_today_seconds: 0,
        remaining_today_seconds: 1800,
        ...partial,
    };
}

function session(
    status: TradingSession["status"],
    partial: Partial<TradingSession> = {},
): TradingSession {
    return {
        session_id: "s1",
        status,
        channel: null,
        quota_seconds_granted: 1800,
        elapsed_seconds: 60,
        remaining_seconds: 1740,
        clock_running: status === "scanning",
        llm_tokens_used: 0,
        llm_cost_micros: 0,
        llm_cost_cap_micros: 500_000,
        cycles_completed: 1,
        last_cycle_at: null,
        expected_cycle_seconds: 20,
        seconds_refunded: 0,
        started_at: null,
        ended_at: null,
        end_reason: null,
        ...partial,
    };
}

const DOWN = { available: false, reason: "paused" as const, eta_seconds: 3600 };

describe("sessionPhase", () => {
    it("is idle with no session and quota left", () => {
        expect(sessionPhase(overview({}))).toBe("idle");
    });

    it("is exhausted with no session and no time left today", () => {
        expect(
            sessionPhase(overview({ remaining_today_seconds: 0, used_today_seconds: 1800 })),
        ).toBe("exhausted");
    });

    it("maps live statuses to their phases", () => {
        expect(sessionPhase(overview({ session: session("scanning") }))).toBe("scanning");
        expect(sessionPhase(overview({ session: session("setup_proposed") }))).toBe("proposal");
        expect(sessionPhase(overview({ session: session("executing") }))).toBe("executing");
    });

    // Preflight outranks quota (spec §5 rule 3): with analysis down, "out of time" is
    // both wrong and hides the real cause.
    it("is blocked instead of idle when capacity is down", () => {
        expect(sessionPhase(overview({ capacity: DOWN }))).toBe("blocked");
    });

    it("is blocked instead of exhausted when capacity is down", () => {
        expect(
            sessionPhase(
                overview({
                    capacity: DOWN,
                    remaining_today_seconds: 0,
                    used_today_seconds: 1800,
                }),
            ),
        ).toBe("blocked");
    });

    it("is blocked when an ended session lingers in the payload", () => {
        expect(sessionPhase(overview({ capacity: DOWN, session: session("ended") }))).toBe(
            "blocked",
        );
    });

    // Deciding on a pending plan needs no capacity, and hiding a live scan or a plan
    // with a shelf life behind an offline banner would lose the user's decision.
    it("does not hijack a live session's own phase", () => {
        expect(sessionPhase(overview({ capacity: DOWN, session: session("scanning") }))).toBe(
            "scanning",
        );
        expect(sessionPhase(overview({ capacity: DOWN, session: session("setup_proposed") }))).toBe(
            "proposal",
        );
        expect(sessionPhase(overview({ capacity: DOWN, session: session("executing") }))).toBe(
            "executing",
        );
    });

    it("falls back to idle against a backend that predates the capacity key", () => {
        const legacy = overview({});
        delete (legacy as Partial<SessionOverview>).capacity;
        expect(sessionPhase(legacy)).toBe("idle");
    });
});

describe("isCapacityDown", () => {
    it("is true only when the payload says available: false", () => {
        expect(isCapacityDown(overview({ capacity: DOWN }))).toBe(true);
        expect(isCapacityDown(overview({}))).toBe(false);
        expect(isCapacityDown(null)).toBe(false);
    });
});

describe("isHeartbeatStale", () => {
    const now = new Date("2026-08-02T10:00:00Z");
    // expected_cycle_seconds 20 → the stale threshold is 40s since the last cycle.
    const scanning = (partial: Partial<TradingSession>) => session("scanning", partial);

    it("is fresh well inside two cycles", () => {
        expect(
            isHeartbeatStale(scanning({ last_cycle_at: "2026-08-02T09:59:52Z" }), now),
        ).toBe(false);
    });

    it("is not stale exactly at the two-cycle threshold", () => {
        expect(
            isHeartbeatStale(scanning({ last_cycle_at: "2026-08-02T09:59:20Z" }), now),
        ).toBe(false);
    });

    it("is stale one second past the threshold", () => {
        expect(
            isHeartbeatStale(scanning({ last_cycle_at: "2026-08-02T09:59:19Z" }), now),
        ).toBe(true);
    });

    it("gives a session that has not reported yet one cycle of grace", () => {
        expect(
            isHeartbeatStale(
                scanning({ last_cycle_at: null, started_at: "2026-08-02T09:59:40Z" }),
                now,
            ),
        ).toBe(false);
    });

    it("is stale when nothing has reported a cycle after the start", () => {
        expect(
            isHeartbeatStale(
                scanning({ last_cycle_at: null, started_at: "2026-08-02T09:59:00Z" }),
                now,
            ),
        ).toBe(true);
    });

    it("never calls a paused clock stale — silence is expected there", () => {
        const stale = { last_cycle_at: "2026-08-02T09:50:00Z" };
        expect(isHeartbeatStale(session("setup_proposed", stale), now)).toBe(false);
        expect(isHeartbeatStale(session("executing", stale), now)).toBe(false);
        expect(isHeartbeatStale(session("ended", stale), now)).toBe(false);
    });

    it("says nothing rather than accusing the engine when the data is missing", () => {
        expect(isHeartbeatStale(null, now)).toBe(false);
        expect(isHeartbeatStale(scanning({ started_at: null }), now)).toBe(false);
        expect(isHeartbeatStale(scanning({ last_cycle_at: "not-a-date" }), now)).toBe(false);
        expect(
            isHeartbeatStale(
                scanning({ last_cycle_at: "2026-08-02T09:50:00Z", expected_cycle_seconds: 0 }),
                now,
            ),
        ).toBe(false);
    });
});

describe("scanReceipt", () => {
    const now = new Date("2026-08-02T10:00:00Z");

    it("splits charged from unmetered time across the scan's span", () => {
        const r = scanReceipt(
            session("ended", {
                elapsed_seconds: 380, // 6:20 charged
                started_at: "2026-08-02T09:49:35Z",
                ended_at: "2026-08-02T10:00:00Z", // 625s wall → 245s (4:05) free
            }),
            1295,
            now,
        );
        expect(r).toEqual({
            chargedSeconds: 380,
            freeSeconds: 245,
            refundedSeconds: 0,
            remainingTodaySeconds: 1295,
        });
    });

    it("carries a refund through without double-counting it as charged", () => {
        const r = scanReceipt(
            session("ended", {
                elapsed_seconds: 200,
                seconds_refunded: 200, // 3:20 returned after capacity died
                started_at: "2026-08-02T09:53:20Z",
                ended_at: "2026-08-02T10:00:00Z",
            }),
            1660,
            now,
        );
        expect(r?.chargedSeconds).toBe(200);
        expect(r?.refundedSeconds).toBe(200);
        expect(r?.freeSeconds).toBe(200);
    });

    it("measures a still-running scan against now", () => {
        const r = scanReceipt(
            session("scanning", { elapsed_seconds: 100, started_at: "2026-08-02T09:58:00Z" }),
            1700,
            now,
        );
        expect(r?.freeSeconds).toBe(20);
    });

    it("drops the free line rather than inventing it without a start time", () => {
        expect(scanReceipt(session("ended", { started_at: null }), 1000, now)?.freeSeconds).toBe(
            null,
        );
    });

    it("has no receipt without a session, and no daily figure without an overview", () => {
        expect(scanReceipt(null)).toBe(null);
        expect(scanReceipt(session("ended"))?.remainingTodaySeconds).toBe(null);
    });
});

describe("formatClock", () => {
    it("formats minutes and seconds", () => {
        expect(formatClock(0)).toBe("0:00");
        expect(formatClock(90)).toBe("1:30");
        expect(formatClock(1799)).toBe("29:59");
    });

    it("adds an hours field past 60 minutes", () => {
        expect(formatClock(3661)).toBe("1:01:01");
    });

    it("never renders negative time", () => {
        expect(formatClock(-5)).toBe("0:00");
    });
});

describe("shelfLifeSeconds", () => {
    const now = new Date("2026-08-02T10:00:00Z");

    it("counts down to the expiry", () => {
        expect(shelfLifeSeconds("2026-08-02T10:02:00Z", now)).toBe(120);
    });

    it("clamps at zero once lapsed", () => {
        expect(shelfLifeSeconds("2026-08-02T09:59:00Z", now)).toBe(0);
    });

    it("treats missing or garbage timestamps as lapsed", () => {
        expect(shelfLifeSeconds(null, now)).toBe(0);
        expect(shelfLifeSeconds("not-a-date", now)).toBe(0);
    });
});

describe("isRetryableRefusal", () => {
    it("recognises the backend's retry hint", () => {
        expect(
            isRetryableRefusal(
                "Not executed: price_moved_beyond_tolerance — you can retry or reject",
            ),
        ).toBe(true);
    });

    it("treats terminal refusals as final", () => {
        expect(isRetryableRefusal("Not executed: execution_rejected")).toBe(false);
        expect(isRetryableRefusal("The proposal has expired")).toBe(false);
    });
});
