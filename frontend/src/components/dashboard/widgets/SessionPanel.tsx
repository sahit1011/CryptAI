"use client";

import { useEffect, useState } from "react";
import { Activity, Play, Radar, Square, Timer } from "lucide-react";

import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/ui/states";
import { cn } from "@/lib/utils";
import { useSession } from "@/hooks/useSession";
import { formatClock, isHeartbeatStale, type SessionPhase } from "@/lib/session";
import { TRADING_STYLES } from "@/lib/preferences";
import { getPreferences, type GoalHorizon } from "@/lib/api";
import { ProposalCard } from "./ProposalCard";

/*
 * SessionPanel — the scan console.
 *
 * Find a trade (free tier: a daily allowance of scan time), watch the clock spend only
 * while your agents are scanning, decide on the plan it surfaces, and see the trade
 * open. The server clock is authoritative (useSession polls every 5s); this ticks
 * locally between polls so the timer reads smoothly.
 *
 * Honesty rules this component exists to keep (docs/UX_SPEC.md §5):
 *  - Never claim the agents are working without a fresh timestamp proving it. Silence
 *    is reported as silence, not narrated as progress.
 *  - When analysis is offline the Start control is ABSENT, not disabled: a greyed
 *    button invites "why can't I press this", and the honest answer is about capacity,
 *    not about the user.
 *  - Say what is and is not costing scan time in every state, not in a tooltip.
 */

/** The three-verb model, stated wherever the meter is visible. Scanning is the only
 * thing that spends; deciding and watching are free. This is the whole pricing model,
 * so it is never hidden behind a hover. */
function MeterLegend() {
    return (
        <p className="text-[11px] leading-relaxed text-muted-foreground">
            <span className="text-foreground">Scanning</span> uses your scan time.{" "}
            <span className="text-foreground">Deciding</span> doesn&apos;t — the clock stops the
            moment a plan lands. <span className="text-foreground">Watching</span> never does.
        </p>
    );
}

export function SessionPanel() {
    const { overview, phase, capacity, proposal, loading, error, notice, busy, start, end, approve, reject } =
        useSession();

    // The channel to start with — seeded from the user's persona default, overridable
    // per session before Start.
    const [channel, setChannel] = useState<GoalHorizon>("swing");
    useEffect(() => {
        let cancelled = false;
        getPreferences()
            .then((p) => !cancelled && setChannel(p.goal_horizon))
            .catch(() => { /* keep the default */ });
        return () => {
            cancelled = true;
        };
    }, []);

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

    const session = overview?.session ?? null;
    // Judged from last_cycle_at, not from the phase: a scanning session whose agents
    // have gone quiet must stop being described as working.
    const stale = isHeartbeatStale(session);

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

                {/* IDLE — pick a style, then start */}
                {phase === "idle" ? (
                    <div className="flex flex-col gap-4 py-2">
                        {/* Readiness rows: everything that has to be true before a scan can
                            produce anything, stated before the user spends time on it. */}
                        <dl className="divide-y divide-border/60 rounded-lg border border-border/60 text-xs">
                            <div className="flex items-center justify-between px-3 py-2">
                                <dt className="text-muted-foreground">Analysis</dt>
                                <dd className="font-medium text-profit">online</dd>
                            </div>
                            <div className="flex items-center justify-between px-3 py-2">
                                <dt className="text-muted-foreground">Scan time today</dt>
                                <dd className="font-medium tabular-nums text-foreground">
                                    {formatClock(dailyRemaining)} of{" "}
                                    {formatClock(overview?.daily_quota_seconds ?? 0)} left
                                </dd>
                            </div>
                            <div className="flex items-center justify-between px-3 py-2">
                                <dt className="text-muted-foreground">Style</dt>
                                <dd className="font-medium text-foreground">
                                    {TRADING_STYLES.find((s) => s.value === channel)?.label ?? channel}
                                </dd>
                            </div>
                        </dl>
                        <div>
                            <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                                Trading style this session
                            </p>
                            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                                {TRADING_STYLES.map((s) => {
                                    const active = channel === s.value;
                                    return (
                                        <button
                                            key={s.value}
                                            type="button"
                                            onClick={() => setChannel(s.value)}
                                            aria-pressed={active}
                                            disabled={busy}
                                            className={cn(
                                                "flex flex-col gap-0.5 rounded-lg border px-3 py-2 text-left transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:opacity-60",
                                                active
                                                    ? "border-accent/40 bg-accent-muted/40 text-foreground"
                                                    : "border-border bg-elevated/30 text-muted-foreground hover:text-foreground",
                                            )}
                                        >
                                            {/* Holding period and the R:R bar on the face, not in a
                                                title= — a tooltip is invisible on mobile and to
                                                anyone who never hovers. */}
                                            <span className="text-sm font-medium">{s.label}</span>
                                            <span className="text-[10px] leading-tight text-muted-foreground">
                                                {s.horizon}
                                            </span>
                                            <span className="text-[10px] leading-tight text-muted-foreground">
                                                needs {s.minRR.toFixed(1)}:1
                                            </span>
                                        </button>
                                    );
                                })}
                            </div>
                        </div>
                        <Button
                            className="self-center bg-profit text-background hover:bg-profit/90"
                            onClick={() => start(channel)}
                            disabled={busy}
                        >
                            <Play className="size-4" />
                            {busy ? "Starting…" : "Start session"}
                        </Button>
                    </div>
                ) : null}

                {/* BLOCKED — analysis capacity is down. No Start button at all: the
                    honest answer is about our capacity, not the user's quota. */}
                {phase === "blocked" ? (
                    <div className="flex flex-col gap-2 py-4 text-center">
                        <Radar className="mx-auto size-8 text-muted-foreground/50" />
                        <p className="text-sm font-medium text-foreground">Market analysis is offline.</p>
                        <p className="text-xs leading-relaxed text-muted-foreground">
                            No new trade plans can be produced until it&apos;s back.{" "}
                            <span className="text-foreground">Your scan time is safe</span> — nothing
                            is being counted. Trades you already have are still being watched.
                        </p>
                        {capacity?.eta_seconds ? (
                            <p className="text-[11px] text-muted-foreground">
                                Expected back in about {formatClock(capacity.eta_seconds)}.
                            </p>
                        ) : null}
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
                                <div className="text-[11px] text-muted-foreground">
                                    left this session{session?.channel ? ` · ${session.channel}` : ""}
                                </div>
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
                        {/* Evidence, not reassurance. The sentence this replaced ("The agents
                            are analysing live conditions…") rendered identically whether a
                            sweep had just finished or nothing had run in ten minutes — it was
                            the known bug in sentence form. */}
                        {stale ? (
                            <p className="rounded-md bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
                                <span className="text-foreground">No word from your agents.</span>{" "}
                                Your clock is paused until they report back.
                            </p>
                        ) : (
                            <p className="text-center text-xs text-muted-foreground">
                                {session?.cycles_completed
                                    ? `${session.cycles_completed} sweep${session.cycles_completed === 1 ? "" : "s"} so far — nothing has cleared your bar yet.`
                                    : "First sweep is running. A plan appears here the moment one clears your bar."}
                            </p>
                        )}
                        <MeterLegend />
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

function PhaseBadge({ phase }: { phase: SessionPhase }) {
    const map: Record<SessionPhase, { label: string; cls: string }> = {
        idle: { label: "Ready", cls: "bg-muted/60 text-muted-foreground" },
        blocked: { label: "Analysis offline", cls: "bg-muted/60 text-muted-foreground" },
        exhausted: { label: "No scan time left", cls: "bg-muted/60 text-muted-foreground" },
        scanning: { label: "Scanning", cls: "bg-accent/15 text-accent" },
        proposal: { label: "Your call", cls: "bg-profit/15 text-profit" },
        executing: { label: "Placing", cls: "bg-accent/15 text-accent" },
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
