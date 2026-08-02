"use client";

import { useEffect, useState } from "react";
import { Activity, Play, Radar, Square, Timer } from "lucide-react";

import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/ui/states";
import { cn } from "@/lib/utils";
import { useSession } from "@/hooks/useSession";
import { formatClock, sessionPhase } from "@/lib/session";
import { ProposalCard } from "./ProposalCard";

/*
 * SessionPanel — the metered-session control surface.
 *
 * Start a session (free tier: a daily quota), watch the clock spend only while
 * the swarm is scanning, decide on the proposal it surfaces, and see the trade
 * open. The server clock is authoritative (useSession polls every 5s); this
 * ticks locally between polls so the timer reads smoothly.
 */

export function SessionPanel() {
    const { overview, proposal, loading, error, notice, busy, start, end, approve, reject } =
        useSession();

    // Smooth local tick for the scanning timer, reset on every server poll.
    const [tick, setTick] = useState(0);
    useEffect(() => {
        setTick(0);
        if (overview?.session?.status !== "scanning") return;
        const t = setInterval(() => setTick((n) => n + 1), 1000);
        return () => clearInterval(t);
    }, [overview?.session?.status, overview?.session?.elapsed_seconds]);

    if (loading && !overview) {
        return (
            <div className="rounded-xl border border-border bg-card p-5">
                <LoadingState title="Loading session…" />
            </div>
        );
    }

    const phase = overview ? sessionPhase(overview) : "idle";
    const session = overview?.session ?? null;

    const dailyRemaining = overview?.remaining_today_seconds ?? 0;
    const liveElapsed = (session?.elapsed_seconds ?? 0) + (session?.status === "scanning" ? tick : 0);
    const liveRemaining = Math.max(0, (session?.remaining_seconds ?? 0) - (session?.status === "scanning" ? tick : 0));

    return (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <div className="flex items-center gap-2">
                    <Radar className="size-4 text-accent" />
                    <h2 className="text-sm font-semibold text-foreground">Trading session</h2>
                </div>
                <PhaseBadge phase={phase} />
            </div>

            <div className="p-4">
                {error ? (
                    <p className="mb-3 rounded-md bg-loss-muted px-3 py-2 text-xs text-loss">{error}</p>
                ) : null}
                {notice ? (
                    <p className="mb-3 rounded-md bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
                        {notice}
                    </p>
                ) : null}

                {/* IDLE — offer to start */}
                {phase === "idle" ? (
                    <div className="flex flex-col items-center gap-3 py-4 text-center">
                        <Timer className="size-8 text-muted-foreground/60" />
                        <div>
                            <p className="text-sm font-medium text-foreground">Ready when you are</p>
                            <p className="mt-1 text-xs text-muted-foreground">
                                {formatClock(dailyRemaining)} of analysis time left today. The clock only
                                runs while the swarm is scanning — it pauses when a setup is on the table.
                            </p>
                        </div>
                        <Button
                            className="bg-profit text-background hover:bg-profit/90"
                            onClick={start}
                            disabled={busy}
                        >
                            <Play className="size-4" />
                            {busy ? "Starting…" : "Start session"}
                        </Button>
                    </div>
                ) : null}

                {/* EXHAUSTED */}
                {phase === "exhausted" ? (
                    <div className="flex flex-col items-center gap-2 py-6 text-center">
                        <Timer className="size-8 text-muted-foreground/50" />
                        <p className="text-sm font-medium text-foreground">Daily analysis time spent</p>
                        <p className="text-xs text-muted-foreground">
                            Your free quota resets at 00:00 UTC. Any open position keeps being monitored.
                        </p>
                    </div>
                ) : null}

                {/* SCANNING — live timer */}
                {phase === "scanning" ? (
                    <div className="space-y-4">
                        <div className="flex items-end justify-between">
                            <div>
                                <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-accent">
                                    <span className="relative flex size-2">
                                        <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent/60" />
                                        <span className="relative inline-flex size-2 rounded-full bg-accent" />
                                    </span>
                                    Scanning the market
                                </div>
                                <div className="mt-1 font-mono text-3xl font-semibold tabular-nums text-foreground">
                                    {formatClock(liveRemaining)}
                                </div>
                                <div className="text-[11px] text-muted-foreground">left this session</div>
                            </div>
                            <Button variant="outline" size="sm" onClick={end} disabled={busy}>
                                <Square className="size-3.5" />
                                End
                            </Button>
                        </div>
                        <QuotaBar
                            elapsed={liveElapsed}
                            granted={session?.quota_seconds_granted ?? 0}
                        />
                        <p className="text-center text-xs text-muted-foreground">
                            The agents are analysing live conditions against your preferences. A setup
                            will appear here the moment one qualifies.
                        </p>
                    </div>
                ) : null}

                {/* PROPOSAL — the decision */}
                {phase === "proposal" && proposal ? (
                    <div className="space-y-3">
                        <ProposalCard
                            proposal={proposal}
                            busy={busy}
                            onApprove={approve}
                            onReject={reject}
                        />
                        <button
                            onClick={end}
                            disabled={busy}
                            className="w-full text-center text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50"
                        >
                            End session instead
                        </button>
                    </div>
                ) : null}

                {/* PROPOSAL phase but the card hasn't loaded yet */}
                {phase === "proposal" && !proposal ? (
                    <LoadingState title="Loading the proposal…" />
                ) : null}

                {/* EXECUTING */}
                {phase === "executing" ? (
                    <div className="flex flex-col items-center gap-2 py-6 text-center">
                        <Activity className="size-7 animate-pulse text-accent" />
                        <p className="text-sm font-medium text-foreground">Placing your trade…</p>
                        <p className="text-xs text-muted-foreground">
                            Re-validating at the live price and routing the bracket.
                        </p>
                    </div>
                ) : null}
            </div>
        </div>
    );
}

function PhaseBadge({ phase }: { phase: ReturnType<typeof sessionPhase> }) {
    const map: Record<string, { label: string; cls: string }> = {
        idle: { label: "Idle", cls: "bg-muted/60 text-muted-foreground" },
        exhausted: { label: "Quota spent", cls: "bg-muted/60 text-muted-foreground" },
        scanning: { label: "Scanning", cls: "bg-accent/15 text-accent" },
        proposal: { label: "Awaiting you", cls: "bg-profit/15 text-profit" },
        executing: { label: "Executing", cls: "bg-accent/15 text-accent" },
    };
    const { label, cls } = map[phase] ?? map.idle;
    return (
        <span className={cn("rounded-full px-2.5 py-1 text-[11px] font-medium", cls)}>{label}</span>
    );
}

function QuotaBar({ elapsed, granted }: { elapsed: number; granted: number }) {
    const pct = granted > 0 ? Math.min(100, (elapsed / granted) * 100) : 0;
    return (
        <div className="space-y-1">
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                <div
                    className="h-full rounded-full bg-accent transition-[width] duration-1000 ease-linear"
                    style={{ width: `${pct}%` }}
                />
            </div>
            <div className="flex justify-between text-[10px] tabular-nums text-muted-foreground">
                <span>{formatClock(elapsed)} used</span>
                <span>{formatClock(granted)} session</span>
            </div>
        </div>
    );
}
