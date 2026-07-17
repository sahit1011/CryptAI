"use client";

import { TrendingUp, PieChart, Wallet } from "lucide-react";

import { SectionHeader } from "../ui/SectionHeader";
import { Card } from "@/components/ui/card";
import { StatTile } from "@/components/ui/stat-tile";
import { Value, PnL } from "@/components/ui/value";
import { EmptyState } from "@/components/ui/states";
import { EquityCurve } from "../widgets/EquityCurve";
import { useStore } from "@/store/useStore";
import { useMarketStore } from "@/hooks/useMarketData";
import { useClosedTrades } from "@/hooks/useClosedTrades";
import { computeTradeStats } from "@/lib/tradeStats";
import { safeDiv, cn } from "@/lib/utils";

/**
 * PortfolioSection — account equity + performance.
 *
 * Live account equity/balances stream from the WS feed. When that feed hasn't
 * delivered (no exchange connected / engine idle), we don't show a dead "no
 * data" screen — we render REALIZED performance from the settled-trade record
 * (/api/trades), clearly labelled as paper history. No fabricated balances.
 */
export function PortfolioSection() {
    const { portfolio, activeTrades } = useStore();
    const status = useMarketStore((s) => s.status);
    const { trades } = useClosedTrades();
    const stats = computeTradeStats(trades);

    const hasLive = portfolio.totalValue > 0 || portfolio.balance > 0;
    const hasRealized = stats.closedCount > 0;

    const usdtAllocationPct = safeDiv(portfolio.balance, portfolio.totalValue) * 100;
    const positionAllocations = activeTrades.map((trade) => {
        const notional = Math.abs((trade.qty ?? 0) * (trade.current || trade.entry));
        return { trade, notional, pct: safeDiv(notional, portfolio.totalValue) * 100 };
    });

    const maxAbsSymbolPnl = Math.max(1, ...stats.perSymbol.map((s) => Math.abs(s.pnl)));

    return (
        <div className="space-y-8">
            <SectionHeader
                title="Portfolio"
                description={
                    !hasLive && hasRealized
                        ? "Realized performance from settled paper trades. Live equity and open positions appear once an exchange is connected."
                        : "Account equity, allocation, and lifetime performance"
                }
            />

            {hasLive ? (
                <>
                    {/* Equity + balance breakdown (live feed) */}
                    <div className="grid gap-4 md:grid-cols-3">
                        <Card className="gap-4 md:col-span-2">
                            <div className="flex items-start justify-between px-4">
                                <div className="space-y-1.5">
                                    <div className="label-md">Total Portfolio Value</div>
                                    <Value value={portfolio.totalValue} money decimals={2} className="financial-lg text-foreground" />
                                    <div className="flex items-center gap-2">
                                        <PnL value={portfolio.totalPnl} money className="financial-xs" />
                                        <PnL value={portfolio.totalPnlPercent} percent chip className="text-[11px]" />
                                        <span className="body-xs text-subtle-foreground">total</span>
                                    </div>
                                </div>
                                <div className="rounded-lg bg-accent-muted p-2.5 text-accent-300">
                                    <TrendingUp className="h-5 w-5" />
                                </div>
                            </div>
                            <div className="grid grid-cols-3 gap-4 border-t border-border px-4 pt-4">
                                <div className="space-y-1">
                                    <div className="body-xs">Available Balance</div>
                                    <Value value={portfolio.balance} money decimals={2} className="financial-xs text-foreground" />
                                </div>
                                <div className="space-y-1">
                                    <div className="body-xs">Total Invested</div>
                                    <Value value={portfolio.totalInvested} money decimals={2} className="financial-xs text-foreground" />
                                </div>
                                <div className="space-y-1">
                                    <div className="body-xs">Unrealized P&amp;L</div>
                                    <PnL value={portfolio.unrealizedPnl} money className="financial-xs" />
                                </div>
                            </div>
                        </Card>

                        <Card className="gap-4">
                            <div className="flex items-center gap-2 px-4">
                                <PieChart className="h-4 w-4 text-muted-foreground" />
                                <div className="label-md">Asset Allocation</div>
                            </div>
                            <div className="space-y-3 px-4">
                                <div className="space-y-1.5">
                                    <div className="flex items-center justify-between">
                                        <span className="body-sm text-foreground">USDT</span>
                                        <Value value={Number.isFinite(usdtAllocationPct) ? usdtAllocationPct : 0} decimals={1} suffix="%" className="body-sm text-muted-foreground" />
                                    </div>
                                    <div className="h-1.5 overflow-hidden rounded-full bg-elevated">
                                        <div className="h-full rounded-full bg-accent" style={{ width: `${Math.min(Math.max(usdtAllocationPct, 0), 100)}%` }} />
                                    </div>
                                </div>
                                {positionAllocations.length === 0 ? (
                                    <p className="body-xs text-subtle-foreground">No open positions — capital is fully in USDT.</p>
                                ) : (
                                    positionAllocations.map(({ trade, pct }) => (
                                        <div key={trade.id} className="space-y-1.5">
                                            <div className="flex items-center justify-between">
                                                <span className="body-sm text-foreground">{trade.symbol}</span>
                                                <Value value={Number.isFinite(pct) ? pct : 0} decimals={1} suffix="%" className="body-sm text-muted-foreground" />
                                            </div>
                                            <div className="h-1.5 overflow-hidden rounded-full bg-elevated">
                                                <div className="h-full rounded-full bg-accent-600" style={{ width: `${Math.min(Math.max(pct, 0), 100)}%` }} />
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>
                        </Card>
                    </div>

                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                        <StatTile label="Win Rate" value={portfolio.winRate} decimals={1} suffix="%" hint="Lifetime" />
                        <StatTile label="Total Trades" value={portfolio.totalTrades} hint="Executed" />
                        <StatTile label="Realized P&L" hint="Locked in">
                            <PnL value={portfolio.realizedPnl} money className="text-lg font-semibold" />
                        </StatTile>
                        <StatTile label="Risk Score" value="—" hint="Not available yet" />
                    </div>
                </>
            ) : hasRealized ? (
                <>
                    {/* Realized equity curve — the settled paper-trade run. */}
                    <Card className="gap-0 overflow-hidden py-0">
                        <div className="flex items-center justify-between border-b border-border px-4 py-3">
                            <div className="flex items-baseline gap-3">
                                <div className="label-md">Realized P&amp;L</div>
                                <PnL value={stats.realizedPnl} money className="num text-xl font-semibold" />
                            </div>
                            <span className="num text-xs text-subtle-foreground">{stats.closedCount} closed · paper</span>
                        </div>
                        <div className="px-2 pb-3 pt-4">
                            <EquityCurve series={stats.equityCurve} height={200} />
                        </div>
                    </Card>

                    {/* Realized performance metrics */}
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                        <StatTile label="Win Rate" hint={`${stats.wins}W · ${stats.losses}L`}>
                            <Value value={stats.winRate} decimals={0} suffix="%" className="text-lg font-semibold text-foreground" />
                        </StatTile>
                        <StatTile label="Profit Factor" hint="Gross win ÷ loss">
                            <Value value={Number.isFinite(stats.profitFactor) ? stats.profitFactor : 99} decimals={2} className="text-lg font-semibold text-foreground" />
                        </StatTile>
                        <StatTile label="Avg Win / Loss" hint="Per trade">
                            <span className="flex items-baseline gap-1.5">
                                <PnL value={stats.avgWin} money className="text-lg font-semibold" />
                                <span className="num text-sm text-subtle-foreground">/</span>
                                <PnL value={stats.avgLoss} money className="text-sm" />
                            </span>
                        </StatTile>
                        <StatTile label="Best / Worst" hint="Single trade">
                            <span className="flex items-baseline gap-1.5">
                                <PnL value={stats.best} money className="text-lg font-semibold" />
                                <span className="num text-sm text-subtle-foreground">/</span>
                                <PnL value={stats.worst} money className="text-sm" />
                            </span>
                        </StatTile>
                    </div>

                    {/* Realized P&L by symbol — replaces the live-only allocation chart. */}
                    <Card className="gap-0 overflow-hidden py-0">
                        <div className="flex items-center justify-between border-b border-border px-4 py-3">
                            <div className="flex items-center gap-2">
                                <PieChart className="size-4 text-subtle-foreground" />
                                <h3 className="heading-4 text-foreground">Realized P&amp;L by market</h3>
                            </div>
                            <span className="num text-xs text-subtle-foreground">{stats.perSymbol.length} markets</span>
                        </div>
                        <div className="divide-y divide-border/60">
                            {stats.perSymbol.map((s) => {
                                const positive = s.pnl >= 0;
                                const width = `${(Math.abs(s.pnl) / maxAbsSymbolPnl) * 100}%`;
                                return (
                                    <div key={s.symbol} className="px-4 py-3">
                                        <div className="mb-1.5 flex items-center justify-between">
                                            <span className="num text-sm font-medium text-foreground">{s.symbol}</span>
                                            <div className="flex items-baseline gap-2.5">
                                                <span className="num text-xs text-subtle-foreground">
                                                    {s.trades} {s.trades === 1 ? "trade" : "trades"} · {Math.round((s.wins / s.trades) * 100)}% win
                                                </span>
                                                <PnL value={s.pnl} money className="num text-sm font-semibold" />
                                            </div>
                                        </div>
                                        <div className="h-1.5 overflow-hidden rounded-full bg-elevated">
                                            <div className={cn("h-full rounded-full", positive ? "bg-profit" : "bg-loss")} style={{ width }} />
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </Card>
                </>
            ) : (
                <Card>
                    <EmptyState
                        icon={<Wallet />}
                        title={status === "open" ? "No account data yet" : "Waiting for the live feed"}
                        description={
                            status === "open"
                                ? "Account equity and settled trades will appear here as soon as the backend reports them."
                                : "Portfolio metrics stream from the trading backend. They’ll populate once the feed connects."
                        }
                    />
                </Card>
            )}
        </div>
    );
}
