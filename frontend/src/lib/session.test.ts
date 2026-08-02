import { describe, expect, it } from "vitest";

import type { SessionOverview, TradingSession } from "@/lib/api";
import {
    formatClock,
    isRetryableRefusal,
    sessionPhase,
    shelfLifeSeconds,
} from "@/lib/session";

function overview(partial: Partial<SessionOverview>): SessionOverview {
    return {
        session: null,
        daily_quota_seconds: 1800,
        used_today_seconds: 0,
        remaining_today_seconds: 1800,
        ...partial,
    };
}

function session(status: TradingSession["status"]): TradingSession {
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
        started_at: null,
        ended_at: null,
        end_reason: null,
    };
}

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
