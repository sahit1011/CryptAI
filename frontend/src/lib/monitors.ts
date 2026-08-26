import type { MonitorEntry, MonitorStatus } from "@/lib/api";

/*
 * Pure presentation logic for position monitors, unit-tested apart from React.
 */

/** Human label for a monitor exit reason. Unknown reasons pass through humanized. */
export function monitorReasonLabel(reason: string | null | undefined): string {
    switch (reason) {
        case "time_stop":
            return "Time stop — held past its horizon";
        case "profit_protect":
            return "Booked profit before giving it back";
        case "conditions_deteriorated":
            return "Stepped aside as conditions deteriorated";
        default:
            return reason ? reason.replace(/_/g, " ") : "";
    }
}

/** A short badge label for a live monitor state on an open position. */
export function monitorBadge(entry: MonitorEntry | undefined): {
    label: string;
    tone: "watched" | "exiting" | "idle";
} {
    if (!entry || !entry.monitored || !entry.status) {
        return { label: "Not watched", tone: "idle" };
    }
    if (entry.status.decision === "exit") {
        return { label: "Closing", tone: "exiting" };
    }
    return { label: "Watched", tone: "watched" };
}

/** Index monitors by uppercased symbol for O(1) lookup from a positions table. */
export function monitorsBySymbol(monitors: MonitorEntry[]): Record<string, MonitorEntry> {
    const out: Record<string, MonitorEntry> = {};
    for (const m of monitors) out[m.symbol.toUpperCase()] = m;
    return out;
}

/** True once a live status is older than the worker's status TTL — treat as stale
 * (the monitor may be down), matching the backend's 90s live-status expiry. */
export function isMonitorStale(status: MonitorStatus | null, now: Date = new Date()): boolean {
    if (!status?.updated_at) return true;
    const t = Date.parse(status.updated_at);
    if (Number.isNaN(t)) return true;
    return now.getTime() - t > 90_000;
}
