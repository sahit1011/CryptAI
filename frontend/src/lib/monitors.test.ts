import { describe, expect, it } from "vitest";

import type { MonitorEntry, MonitorStatus } from "@/lib/api";
import {
    isMonitorStale,
    monitorBadge,
    monitorReasonLabel,
    monitorsBySymbol,
} from "@/lib/monitors";

function status(over: Partial<MonitorStatus> = {}): MonitorStatus {
    return {
        symbol: "BTCUSDT", position_id: "POS_1", decision: "hold", reason: null,
        checks: 2, favorable_pct: 0.4, peak_favorable_pct: 0.9, adverse_streak: 0,
        updated_at: "2026-08-03T12:00:00Z", ...over,
    };
}

describe("monitorReasonLabel", () => {
    it("labels the known reasons", () => {
        expect(monitorReasonLabel("time_stop")).toMatch(/time stop/i);
        expect(monitorReasonLabel("profit_protect")).toMatch(/booked profit/i);
        expect(monitorReasonLabel("conditions_deteriorated")).toMatch(/deteriorat/i);
    });
    it("humanizes an unknown reason and empties a null", () => {
        expect(monitorReasonLabel("some_new_reason")).toBe("some new reason");
        expect(monitorReasonLabel(null)).toBe("");
    });
});

describe("monitorBadge", () => {
    it("is idle when unmonitored or missing", () => {
        expect(monitorBadge(undefined).tone).toBe("idle");
        expect(monitorBadge({ symbol: "X", monitored: false, status: null }).tone).toBe("idle");
    });
    it("is watched on hold and exiting on exit", () => {
        const held: MonitorEntry = { symbol: "BTCUSDT", monitored: true, status: status() };
        expect(monitorBadge(held).tone).toBe("watched");
        const exiting: MonitorEntry = {
            symbol: "BTCUSDT", monitored: true, status: status({ decision: "exit", reason: "time_stop" }),
        };
        expect(monitorBadge(exiting).tone).toBe("exiting");
    });
});

describe("monitorsBySymbol", () => {
    it("indexes case-insensitively", () => {
        const idx = monitorsBySymbol([{ symbol: "btcusdt", monitored: true, status: status() }]);
        expect(idx["BTCUSDT"].monitored).toBe(true);
    });
});

describe("isMonitorStale", () => {
    const now = new Date("2026-08-03T12:01:00Z");  // 60s after the status
    it("is fresh within the TTL", () => {
        expect(isMonitorStale(status(), now)).toBe(false);
    });
    it("is stale past 90s", () => {
        expect(isMonitorStale(status({ updated_at: "2026-08-03T11:59:00Z" }), now)).toBe(true);
    });
    it("treats missing/garbage timestamps as stale", () => {
        expect(isMonitorStale(null, now)).toBe(true);
        expect(isMonitorStale(status({ updated_at: "nope" }), now)).toBe(true);
    });
});
