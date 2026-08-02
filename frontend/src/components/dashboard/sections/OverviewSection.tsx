"use client";

import { SectionHeader } from "../ui/SectionHeader";
import { Card } from "@/components/ui/card";
import { Value, PnL } from "@/components/ui/value";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { ArrowRight, History, Radar } from "lucide-react";
import { SignalsFeed } from "../widgets/SignalsFeed";
import { EquityCurve } from "../widgets/EquityCurve";
import { SessionPanel } from "../widgets/SessionPanel";
import { useStore } from "@/store/useStore";
import { useMarketStore } from "@/hooks/useMarketData";
import { useClosedTrades } from "@/hooks/useClosedTrades";
import { computeTradeStats } from "@/lib/tradeStats";
import { cn } from "@/lib/utils";

export function OverviewSection() {
    const { portfolio, activeTrades } = useStore();
    const { isConnected } = useMarketStore();
    const { trades, closed, loading: loadingTrades, error } = useClosedTrades();

    const stats = computeTradeStats(trades);
    const recentClosed = [...closed]
        .sort((a, b) => (b.exitTime ? Date.parse(b.exitTime) : 0) - (a.exitTime ? Date.parse(a.exitTime) : 0))
        .slice(0, 10);
    const dbActiveTrades = trades.filter(
        (t) => (!t.status || t.status.toUpperCase() === "OPEN") && !t.exitTime,
    );

    // Portfolio is seeded via REST (paper $10k or persisted/live state), so it's
    // present without needing a live WS connection. Realized history is a further
    // fallback if even that is unavailable.
    const isPaper = portfolio.mode !== "live";
    const hasPortfolio = portfolio.totalValue > 0 || portfolio.balance > 0;
    const hasRealized = stats.closedCount > 0;
    const mode: "live" | "realized" | "empty" = hasPortfolio ? "live" : hasRealized ? "realized" : "empty";
    void isConnected;

    return (
        <div className="space-y-8">
            <SectionHeader
                title="Overview"
                description={
                    mode === "empty"
                        ? "Monitor live trading performance and multi-agent system health"
                        : isPaper
                            ? "Your paper desk — virtual funds, real prices. Connect an exchange to trade live."
                            : "Live trading performance and multi-agent system health"
                }
            />

            {/* KPI band — the account (seeded paper or live), else realized history. */}
            <div className="grid gap-px overflow-hidden rounded-xl border border-border bg-border md:grid-cols-2 lg:grid-cols-4">
                {mode === "live" ? (
                    <>
                        <StatCard label="Portfolio Value" tag={isPaper ? "paper" : "live"}>
                            <Value value={portfolio.totalValue} money decimals={2} className="financial-lg text-foreground" />
                            {portfolio.totalPnlPercent !== 0 ? (
                                <PnL value={portfolio.totalPnlPercent} percent className="body-sm font-medium" suffix=" total" />
                            ) : (
                                <span className="body-sm text-subtle-foreground">No change yet</span>
                            )}
                        </StatCard>
                        <StatCard label="Total P&L">
                            <PnL value={portfolio.totalPnl} money className="financial-lg" />
                            {portfolio.totalPnlPercent !== 0 ? (
                                <PnL value={portfolio.totalPnlPercent} percent className="body-sm font-medium" />
                            ) : (
                                <span className="body-sm text-subtle-foreground">Flat</span>
                            )}
                        </StatCard>
                        <StatCard label="Active Trades">
                            <Value value={activeTrades.length} className="financial-lg text-foreground" />
                            <span className="body-sm text-subtle-foreground">
                                {portfolio.totalTrades > 0 ? `${portfolio.totalTrades} total trades` : "No trades executed"}
                            </span>
                        </StatCard>
                        <StatCard label="Win Rate">
                            {(portfolio.winRate ?? 0) > 0 ? (
                                <Value value={portfolio.winRate} decimals={1} suffix="%" className="financial-lg text-foreground" />
                            ) : (
                                <span className="financial-lg text-subtle-foreground">—</span>
                            )}
                            <span className="body-sm text-subtle-foreground">
                                {portfolio.totalTrades > 0 ? `${portfolio.totalTrades} trades` : "No data"}
                            </span>
                        </StatCard>
                    </>
                ) : mode === "realized" ? (
                    <>
                        <StatCard label="Realized P&L" tag="paper">
                            <PnL value={stats.realizedPnl} money className="financial-lg" />
                            <span className="body-sm text-subtle-foreground">{stats.closedCount} closed trades</span>
                        </StatCard>
                        <StatCard label="Win Rate">
                            <Value value={stats.winRate} decimals={0} suffix="%" className="financial-lg text-foreground" />
                            <span className="num body-sm text-subtle-foreground">
                                {stats.wins}W · {stats.losses}L
                            </span>
                        </StatCard>
                        <StatCard label="Best Trade">
                            <PnL value={stats.best} money className="financial-lg" />
                            <span className="body-sm text-subtle-foreground">
                                worst <PnL value={stats.worst} money className="text-xs" />
                            </span>
                        </StatCard>
                        <StatCard label="Profit Factor">
                            <Value
                                value={Number.isFinite(stats.profitFactor) ? stats.profitFactor : 99}
                                decimals={2}
                                className="financial-lg text-foreground"
                            />
                            <span className="body-sm text-subtle-foreground">gross win ÷ loss</span>
                        </StatCard>
                    </>
                ) : (
                    ["Portfolio Value", "Total P&L", "Active Trades", "Win Rate"].map((label) => (
                        <StatCard key={label} label={label}>
                            <span className="financial-lg text-subtle-foreground">—</span>
                            <span className="body-sm text-subtle-foreground">Waiting for data…</span>
                        </StatCard>
                    ))
                )}
            </div>

            {/* The metered trading session — start the swarm, decide on its proposal. */}
            <SessionPanel />

            {/* Realized equity curve — the settled-P&L run, whenever there's history. */}
            {stats.equityCurve.length > 1 && (
                <Card className="gap-0 overflow-hidden py-0">
                    <div className="flex items-center justify-between border-b border-border px-4 py-3">
                        <div className="flex items-baseline gap-3">
                            <h3 className="heading-4 text-foreground">Realized P&amp;L</h3>
                            <PnL value={stats.realizedPnl} money className="num text-sm font-semibold" />
                        </div>
                        <span className="num text-xs text-subtle-foreground">{stats.closedCount} closed · paper</span>
                    </div>
                    <div className="px-2 pb-2 pt-3">
                        <EquityCurve series={stats.equityCurve} height={140} />
                    </div>
                </Card>
            )}

            {/* Live AI trade setups (behavior follows the user's trading mode) */}
            <div>
                <div className="mb-3 flex items-center gap-2">
                    <Radar className="size-4 text-subtle-foreground" />
                    <h3 className="heading-4 text-foreground">AI Signals</h3>
                </div>
                <SignalsFeed limit={4} />
            </div>

            {/* Recent Closed Trades — historical closed trades from the database */}
            <Card className="gap-0 overflow-hidden py-0">
                <div className="flex items-center justify-between border-b border-border px-4 py-3">
                    <div className="flex items-center gap-2">
                        <History className="size-4 text-subtle-foreground" />
                        <h3 className="heading-4 text-foreground">Recent Closed Trades</h3>
                    </div>
                    <span className="num text-xs text-subtle-foreground">
                        {recentClosed.length > 0 ? `Last ${recentClosed.length} closed` : "No history"}
                    </span>
                </div>

                {loadingTrades && recentClosed.length === 0 ? (
                    <LoadingState title="Loading trade history…" />
                ) : error && recentClosed.length === 0 ? (
                    <ErrorState
                        icon={<History />}
                        title="Couldn't load trade history"
                        description="The trades endpoint is unreachable. Live positions still update in the Agents tab."
                        error={error}
                    />
                ) : recentClosed.length === 0 ? (
                    <EmptyState
                        icon={<History />}
                        title={isConnected ? "No closed trades yet" : "Trade history unavailable"}
                        description={
                            isConnected
                                ? dbActiveTrades.length > 0
                                    ? `${dbActiveTrades.length} active ${dbActiveTrades.length === 1 ? "trade is" : "trades are"} running — closed trades appear here once they settle.`
                                    : "Closed trades will appear here after positions are settled."
                                : "Connect to the backend to see settled trade history."
                        }
                    />
                ) : (
                    <div className="divide-y divide-border/60">
                        {recentClosed.map((trade) => {
                            const tradePnl = trade.pnl ?? 0;
                            const isProfitable = tradePnl >= 0;
                            const pnlPercent = trade.pnlPercent ?? 0;
                            const fmt = (t: string | null | undefined) =>
                                t
                                    ? new Date(t).toLocaleString("en-US", {
                                          month: "short",
                                          day: "numeric",
                                          hour: "2-digit",
                                          minute: "2-digit",
                                      })
                                    : "N/A";
                            return (
                                <div
                                    key={trade.id}
                                    className="flex items-center justify-between gap-4 px-4 py-3 transition-colors hover:bg-elevated/40"
                                >
                                    <div className="flex min-w-0 flex-1 items-center gap-3">
                                        <span className={cn("size-1.5 shrink-0 rounded-full", isProfitable ? "bg-profit" : "bg-loss")} />
                                        <div className="min-w-0 flex-1">
                                            <div className="flex items-center gap-2">
                                                <span className="num text-sm font-medium text-foreground">
                                                    {trade.side} {trade.symbol}
                                                </span>
                                                {trade.exitReason ? (
                                                    <span
                                                        className={cn(
                                                            "num rounded-sm border px-1.5 py-px text-[10px] uppercase tracking-wider",
                                                            /profit|tp/i.test(trade.exitReason)
                                                                ? "border-profit/25 bg-profit/10 text-profit"
                                                                : /stop|loss|sl/i.test(trade.exitReason)
                                                                    ? "border-loss/25 bg-loss/10 text-loss"
                                                                    : "border-border bg-elevated text-subtle-foreground",
                                                        )}
                                                    >
                                                        {trade.exitReason.replace(/_/g, " ")}
                                                    </span>
                                                ) : null}
                                            </div>
                                            <div className="mt-1 flex items-center gap-2 text-xs text-subtle-foreground">
                                                <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                                                    <Value value={trade.entry} money className="text-xs" />
                                                    <ArrowRight className="size-3 text-subtle-foreground" />
                                                    <Value value={trade.current} money className="text-xs" />
                                                </span>
                                                <span className="text-border-strong">·</span>
                                                <span className="num">{fmt(trade.exitTime)}</span>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="shrink-0 text-right">
                                        <PnL value={tradePnl} money className="financial-sm block" />
                                        <PnL value={pnlPercent} percent className="body-xs block" />
                                    </div>
                                </div>
                            );
                        })}
                        {dbActiveTrades.length > 0 ? (
                            <div className="px-4 py-3 text-center">
                                <span className="text-xs text-muted-foreground">
                                    {dbActiveTrades.length} active {dbActiveTrades.length === 1 ? "trade" : "trades"} running —
                                    monitored in the Agents tab
                                </span>
                            </div>
                        ) : null}
                    </div>
                )}
            </Card>
        </div>
    );
}

/**
 * A single overview KPI cell inside the bordered band — quiet surface, small
 * caps label, mono value, optional context tag (e.g. "paper").
 */
function StatCard({ label, tag, children }: { label: string; tag?: string; children: React.ReactNode }) {
    return (
        <div className="bg-surface p-5 transition-colors duration-150 hover:bg-elevated/60">
            <div className="flex items-center gap-2">
                <span className="label-md">{label}</span>
                {tag ? (
                    <span className="num rounded border border-border px-1 py-0.5 text-[9px] uppercase tracking-wider text-subtle-foreground">
                        {tag}
                    </span>
                ) : null}
            </div>
            <div className="mt-2.5 flex flex-col items-start gap-1">{children}</div>
        </div>
    );
}
