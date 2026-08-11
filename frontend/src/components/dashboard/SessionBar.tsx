"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AlertTriangle, Pause, Radar } from "lucide-react";

import { cn } from "@/lib/utils";
import { useSession } from "@/hooks/useSession";
import { formatClock, isHeartbeatStale } from "@/lib/session";

/**
 * SessionBar — the scan, wherever you are.
 *
 * A trade plan is valid for about three minutes. Before this, that countdown existed on
 * one page: navigate to the Chart to check the price you were being asked about and the
 * plan simply vanished from view. Nothing in the app may be less visible than a deadline
 * that short.
 *
 * Renders only when there is something to say — a scan running, a plan waiting, or
 * capacity lost mid-scan. Silent otherwise, so it never becomes furniture users learn
 * to ignore.
 */
export function SessionBar() {
    const { overview, phase, proposal } = useSession();
    const pathname = usePathname();

    // Local tick so the countdowns move between the hook's 5s polls.
    const [, setTick] = useState(0);
    useEffect(() => {
        const t = setInterval(() => setTick((n) => n + 1), 1000);
        return () => clearInterval(t);
    }, []);

    const session = overview?.session ?? null;
    const onDesk = pathname === "/desk";

    if (phase === "proposal" && proposal) {
        const validFor = Math.max(
            0,
            Math.floor((Date.parse(proposal.expires_at ?? "") - Date.now()) / 1000),
        );
        return (
            <Bar tone="decide">
                <Pause className="size-3.5 shrink-0" />
                <span className="font-medium">Clock paused — your call</span>
                <span className="text-muted-foreground">
                    {proposal.symbol} plan valid{" "}
                    <span className="tabular-nums text-foreground">
                        {Number.isFinite(validFor) ? formatClock(validFor) : "—"}
                    </span>
                </span>
                {!onDesk ? <Action href="/desk">Decide</Action> : null}
            </Bar>
        );
    }

    if (phase === "scanning" && session) {
        const stale = isHeartbeatStale(session);
        return (
            <Bar tone={stale ? "warn" : "scan"}>
                {stale ? (
                    <>
                        <AlertTriangle className="size-3.5 shrink-0" />
                        <span className="font-medium">No word from your agents</span>
                        <span className="text-muted-foreground">clock paused until they report</span>
                    </>
                ) : (
                    <>
                        <Radar className="size-3.5 shrink-0 animate-pulse" />
                        <span className="font-medium">Scanning</span>
                        <span className="tabular-nums text-muted-foreground">
                            {formatClock(session.remaining_seconds)} left
                        </span>
                        {session.channel ? (
                            <span className="text-muted-foreground">· {session.channel}</span>
                        ) : null}
                    </>
                )}
                {!onDesk ? <Action href="/desk">View</Action> : null}
            </Bar>
        );
    }

    return null;
}

function Bar({
    tone,
    children,
}: {
    tone: "scan" | "decide" | "warn";
    children: React.ReactNode;
}) {
    return (
        <div
            className={cn(
                "sticky top-0 z-[70] flex items-center gap-2 border-b px-4 py-2 text-xs backdrop-blur",
                tone === "scan" && "border-accent/30 bg-accent/[0.06] text-accent",
                tone === "decide" && "border-profit/30 bg-profit/[0.06] text-profit",
                tone === "warn" && "border-border bg-muted/60 text-muted-foreground",
            )}
        >
            {children}
        </div>
    );
}

function Action({ href, children }: { href: string; children: React.ReactNode }) {
    return (
        <Link
            href={href}
            className="ml-auto rounded-md border border-current/30 px-2 py-0.5 font-medium hover:bg-current/10"
        >
            {children}
        </Link>
    );
}
