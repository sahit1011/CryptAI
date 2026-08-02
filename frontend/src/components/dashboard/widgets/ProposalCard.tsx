"use client";

import { useEffect, useState } from "react";
import { ArrowDownRight, ArrowUpRight, Clock, ShieldAlert } from "lucide-react";

import { Value, PnL } from "@/components/ui/value";
import { Button } from "@/components/ui/button";
import { cn, safeNum } from "@/lib/utils";
import { formatClock, shelfLifeSeconds } from "@/lib/session";
import type { Proposal } from "@/lib/api";

/*
 * ProposalCard — the AI's setup on the table, with the shelf-life clock ticking.
 *
 * Every number is the backend's (deterministic sizing against the user's own risk
 * prefs); nothing is fabricated. The card is the whole consent surface: the user
 * either approves (the daemon re-validates at the live price) or rejects.
 */

interface ProposalCardProps {
    proposal: Proposal;
    busy: boolean;
    onApprove: () => void;
    onReject: () => void;
}

export function ProposalCard({ proposal, busy, onApprove, onReject }: ProposalCardProps) {
    const isLong = proposal.direction === "LONG";
    const DirIcon = isLong ? ArrowUpRight : ArrowDownRight;

    // Local shelf-life countdown between the hook's 5s polls.
    const [remaining, setRemaining] = useState(() => shelfLifeSeconds(proposal.expires_at));
    useEffect(() => {
        setRemaining(shelfLifeSeconds(proposal.expires_at));
        const t = setInterval(() => setRemaining(shelfLifeSeconds(proposal.expires_at)), 1000);
        return () => clearInterval(t);
    }, [proposal.expires_at]);

    const lapsed = remaining <= 0;
    const targets = (proposal.take_profit_levels || []).map((t) => t.price);

    return (
        <div className="overflow-hidden rounded-xl border border-profit/30 bg-profit/[0.025]">
            {/* header: instrument + direction + shelf life */}
            <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
                <div className="flex items-center gap-2.5">
                    <span
                        className={cn(
                            "flex size-7 items-center justify-center rounded-md",
                            isLong ? "bg-profit/15 text-profit" : "bg-loss/15 text-loss",
                        )}
                    >
                        <DirIcon className="size-4" />
                    </span>
                    <div className="leading-tight">
                        <div className="text-sm font-semibold text-foreground">{proposal.symbol}</div>
                        <div
                            className={cn(
                                "text-[11px] font-medium uppercase tracking-wide",
                                isLong ? "text-profit" : "text-loss",
                            )}
                        >
                            {proposal.direction}
                            {proposal.strategy_type ? ` · ${proposal.strategy_type}` : ""}
                        </div>
                    </div>
                </div>
                <div
                    className={cn(
                        "flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium tabular-nums",
                        lapsed ? "bg-loss/10 text-loss" : "bg-muted/50 text-muted-foreground",
                    )}
                    title="Shelf life — the setup is re-validated at the live price on approval"
                >
                    <Clock className="size-3.5" />
                    {lapsed ? "expiring…" : formatClock(remaining)}
                </div>
            </div>

            {/* the trade geometry */}
            <div className="grid grid-cols-3 gap-px bg-border/60">
                <Metric label="Entry" node={<Value money value={safeNum(proposal.entry_price)} />} />
                <Metric
                    label="Stop"
                    node={<Value className="text-loss" money value={safeNum(proposal.stop_loss)} />}
                />
                <Metric
                    label="Target"
                    node={
                        targets.length ? (
                            <Value className="text-profit" money value={safeNum(targets[0])} />
                        ) : (
                            <span className="text-muted-foreground">—</span>
                        )
                    }
                />
            </div>

            {/* sizing + conviction */}
            <div className="grid grid-cols-3 gap-px bg-border/60">
                <Metric label="Size" node={<Value value={safeNum(proposal.position_size)} decimals={4} />} />
                <Metric
                    label="Risk"
                    node={<Value money value={safeNum(proposal.risk_amount)} />}
                    sub={`${safeNum(proposal.leverage).toFixed(0)}× lev`}
                />
                <Metric
                    label="R:R"
                    node={<PnL value={safeNum(proposal.risk_reward_ratio)} decimals={2} showSign={false} />}
                    sub={
                        proposal.confidence_score != null
                            ? `${Math.round(proposal.confidence_score * 100)}% conf`
                            : undefined
                    }
                />
            </div>

            {proposal.thesis ? (
                <p className="border-t border-border/60 px-4 py-3 text-[13px] leading-relaxed text-muted-foreground">
                    {proposal.thesis}
                </p>
            ) : null}

            {/* consent */}
            <div className="flex items-center gap-2 border-t border-border/60 p-3">
                <Button
                    variant="outline"
                    className="flex-1"
                    onClick={onReject}
                    disabled={busy}
                >
                    Reject
                </Button>
                <Button
                    className="flex-1 bg-profit text-background hover:bg-profit/90"
                    onClick={onApprove}
                    disabled={busy || lapsed}
                >
                    {busy ? "Working…" : lapsed ? "Expired" : "Approve & execute"}
                </Button>
            </div>

            <p className="flex items-center gap-1.5 border-t border-border/60 px-4 py-2 text-[11px] text-muted-foreground">
                <ShieldAlert className="size-3 shrink-0" />
                Re-checked against the live price on approval — a drifted setup is refused, not filled.
            </p>
        </div>
    );
}

function Metric({ label, node, sub }: { label: string; node: React.ReactNode; sub?: string }) {
    return (
        <div className="bg-card px-4 py-2.5">
            <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
            <div className="mt-0.5 text-sm">{node}</div>
            {sub ? <div className="text-[10px] text-muted-foreground">{sub}</div> : null}
        </div>
    );
}
