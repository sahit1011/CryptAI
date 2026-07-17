"use client";

import { useEffect, useState } from "react";
import { SectionHeader } from "../ui/SectionHeader";
import { Card } from "@/components/ui/card";
import { Value, PnL } from "@/components/ui/value";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import {
    LayoutDashboard,
    TrendingUp,
    Activity,
    Zap,
    BarChart3,
    ArrowRight,
    History,
    Radar,
} from "lucide-react";
import { SignalsFeed } from "../widgets/SignalsFeed";
import { useStore, Trade } from "@/store/useStore";
import { useMarketStore } from "@/hooks/useMarketData";
import { API_URL, authHeaders } from "@/lib/api";
import { cn } from "@/lib/utils";

export function OverviewSection() {
    const { portfolio, activeTrades } = useStore();
    const { isConnected } = useMarketStore();
    const [recentTrades, setRecentTrades] = useState<Trade[]>([]);
    const [loadingTrades, setLoadingTrades] = useState(false);

    const [error, setError] = useState<string | null>(null);

    // Fetch recent trades from database on mount
    useEffect(() => {
        const fetchRecentTrades = async () => {
            setLoadingTrades(true);
            setError(null);
            try {
                // Backend REST URL comes from NEXT_PUBLIC_API_URL (falls back to
                // localhost for dev). Send the bearer token when one is configured.
                const response = await fetch(`${API_URL}/api/trades?limit=50`, {
                    cache: "no-store",
                    headers: await authHeaders(),
                });

                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

                const data = await response.json();
                if (data.trades && Array.isArray(data.trades)) {
                    setRecentTrades(data.trades);
                } else {
                    throw new Error("Invalid data format received");
                }
            } catch (error) {
                console.error("Failed to fetch recent trades:", error);
                setError(error instanceof Error ? error.message : String(error));
            } finally {
                setLoadingTrades(false);
            }
        };

        fetchRecentTrades();
        // Refresh every 30 seconds
        const interval = setInterval(fetchRecentTrades, 30000);
        return () => clearInterval(interval);
    }, []);

    const isPnlPositive = portfolio.totalPnl >= 0;
    const hasData = isConnected && (portfolio.totalValue > 0 || portfolio.balance > 0);
    // Only trust win-rate once the feed is live (0% pre-connect is honest-dash territory).
    const hasWinRate = isConnected && (portfolio.winRate ?? 0) > 0;

    // Filter trades - more robust check
    const closedTrades = recentTrades
        .filter(
            (trade) =>
                (trade.status && trade.status.toUpperCase() === "CLOSED") ||
                trade.exitTime !== null,
        )
        .slice(0, 10);

    const dbActiveTrades = recentTrades.filter(
        (trade) =>
            (!trade.status || trade.status.toUpperCase() === "OPEN") && !trade.exitTime,
    );

    return (
        <div className="space-y-8">
            {/* Header (connection status lives in the global top bar) */}
            <SectionHeader
                title="Overview"
                description="Monitor live trading performance and multi-agent system health"
                icon={LayoutDashboard}
                iconColor="bg-accent-muted text-accent-300"
            />

            {/* KPI band — one bordered strip with hairline dividers (mirrors the
                landing stats band), mono numbers, semantic P&L only */}
            <div className="grid gap-px overflow-hidden rounded-xl border border-border bg-border md:grid-cols-2 lg:grid-cols-4">
                {/* Portfolio Value */}
                <StatCard
                    label="Portfolio Value"
                    icon={<TrendingUp className="size-4" />}
                    watermark={<TrendingUp className="size-20" />}
                >
                    {hasData ? (
                        <Value
                            value={portfolio.totalValue}
                            money
                            decimals={2}
                            className="financial-lg text-foreground"
                        />
                    ) : (
                        <span className="financial-lg text-subtle-foreground">—</span>
                    )}
                    {hasData && portfolio.totalPnlPercent !== 0 ? (
                        <PnL
                            value={portfolio.totalPnlPercent}
                            percent
                            className="body-sm font-medium"
                            suffix=" total"
                        />
                    ) : (
                        <span className="body-sm text-subtle-foreground">
                            {hasData ? "No change yet" : "Waiting for data…"}
                        </span>
                    )}
                </StatCard>

                {/* Total P&L */}
                <StatCard
                    label="Total P&L"
                    icon={<Activity className="size-4" />}
                    watermark={<Activity className="size-20" />}
                >
                    {hasData ? (
                        <PnL
                            value={portfolio.totalPnl}
                            money
                            className={cn(
                                "financial-lg",
                                isPnlPositive ? "text-profit" : "text-loss",
                            )}
                        />
                    ) : (
                        <span className="financial-lg text-subtle-foreground">—</span>
                    )}
                    {hasData && portfolio.totalPnlPercent !== 0 ? (
                        <PnL
                            value={portfolio.totalPnlPercent}
                            percent
                            className="body-sm font-medium"
                        />
                    ) : (
                        <span className="body-sm text-subtle-foreground">
                            {hasData ? "Flat" : "No trades yet"}
                        </span>
                    )}
                </StatCard>

                {/* Active Trades */}
                <StatCard
                    label="Active Trades"
                    icon={<Zap className="size-4" />}
                    watermark={<Zap className="size-20" />}
                >
                    <Value
                        value={activeTrades.length}
                        className="financial-lg text-foreground"
                    />
                    <span className="body-sm text-subtle-foreground">
                        {portfolio.totalTrades > 0
                            ? `${portfolio.totalTrades} total trades`
                            : "No trades executed"}
                    </span>
                </StatCard>

                {/* Win Rate */}
                <StatCard
                    label="Win Rate"
                    icon={<BarChart3 className="size-4" />}
                    watermark={<BarChart3 className="size-20" />}
                >
                    {hasWinRate ? (
                        <Value
                            value={portfolio.winRate}
                            decimals={1}
                            suffix="%"
                            className="financial-lg text-foreground"
                        />
                    ) : (
                        <span className="financial-lg text-subtle-foreground">—</span>
                    )}
                    <span className="body-sm text-subtle-foreground">
                        {portfolio.totalTrades > 0
                            ? `${portfolio.totalTrades} trades`
                            : "No data"}
                    </span>
                </StatCard>
            </div>

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
                        {closedTrades.length > 0
                            ? `Last ${closedTrades.length} closed`
                            : "No history"}
                    </span>
                </div>

                {loadingTrades && closedTrades.length === 0 ? (
                    <LoadingState title="Loading trade history…" />
                ) : error && closedTrades.length === 0 ? (
                    <ErrorState
                        icon={<History />}
                        title="Couldn't load trade history"
                        description="The trades endpoint is unreachable. Live positions still update in the Agents tab."
                        error={error}
                    />
                ) : closedTrades.length === 0 ? (
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
                        {closedTrades.map((trade) => {
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
                                        <span
                                            className={cn(
                                                "size-1.5 shrink-0 rounded-full",
                                                isProfitable ? "bg-profit" : "bg-loss",
                                            )}
                                        />
                                        <div className="min-w-0 flex-1">
                                            <div className="flex items-center gap-2">
                                                <span className="num text-sm font-medium text-foreground">
                                                    {trade.side} {trade.symbol}
                                                </span>
                                                <span className="label-md">Closed</span>
                                            </div>
                                            <div className="mt-1 space-y-0.5">
                                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                    <span className="inline-flex items-center gap-1.5">
                                                        <Value
                                                            value={trade.entry}
                                                            money
                                                            className="text-xs"
                                                        />
                                                        <ArrowRight className="size-3 text-subtle-foreground" />
                                                        <Value
                                                            value={trade.current}
                                                            money
                                                            className="text-xs"
                                                        />
                                                    </span>
                                                </div>
                                                <div className="flex items-center gap-1.5 text-xs text-subtle-foreground">
                                                    <span className="num">{fmt(trade.entryTime)}</span>
                                                    <ArrowRight className="size-3" />
                                                    <span className="num">{fmt(trade.exitTime)}</span>
                                                </div>
                                                {trade.exitReason ? (
                                                    // Exit reason as a semantic chip — take-profits read green,
                                                    // stops read red, at a glance instead of prose.
                                                    <span
                                                        className={`num inline-block w-fit rounded-sm border px-1.5 py-px text-[10px] uppercase tracking-wider ${
                                                            /profit|tp/i.test(trade.exitReason)
                                                                ? "border-profit/25 bg-profit/10 text-profit"
                                                                : /stop|loss|sl/i.test(trade.exitReason)
                                                                    ? "border-loss/25 bg-loss/10 text-loss"
                                                                    : "border-border bg-elevated text-subtle-foreground"
                                                        }`}
                                                    >
                                                        {trade.exitReason.replace(/_/g, " ")}
                                                    </span>
                                                ) : null}
                                            </div>
                                        </div>
                                    </div>
                                    <div className="shrink-0 text-right">
                                        <PnL
                                            value={tradePnl}
                                            money
                                            className="financial-sm block"
                                        />
                                        <PnL
                                            value={pnlPercent}
                                            percent
                                            className="body-xs block"
                                        />
                                    </div>
                                </div>
                            );
                        })}

                        {dbActiveTrades.length > 0 ? (
                            <div className="px-4 py-3 text-center">
                                <span className="text-xs text-muted-foreground">
                                    {dbActiveTrades.length} active{" "}
                                    {dbActiveTrades.length === 1 ? "trade" : "trades"} running —
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
 * caps label, mono value. No icon chips, watermarks, or glow hovers: the
 * numbers are the interface. (icon/watermark props are accepted for caller
 * compatibility but intentionally unrendered.)
 */
function StatCard({
    label,
    icon,
    watermark,
    children,
}: {
    label: string;
    icon?: React.ReactNode;
    watermark?: React.ReactNode;
    children: React.ReactNode;
}) {
    void icon;
    void watermark;
    return (
        <div className="bg-surface p-5 transition-colors duration-150 hover:bg-elevated/60">
            <span className="label-md">{label}</span>
            {/* flex-col so the value and its hint stack (they render as inline
                spans, on which vertical space-y margins have no effect). */}
            <div className="mt-2.5 flex flex-col items-start gap-1">{children}</div>
        </div>
    );
}
