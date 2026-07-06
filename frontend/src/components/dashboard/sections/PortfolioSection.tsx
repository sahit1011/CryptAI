"use client";

import { Wallet, TrendingUp, PieChart } from "lucide-react";

import { SectionHeader } from "../ui/SectionHeader";
import { Card } from "@/components/ui/card";
import { StatTile } from "@/components/ui/stat-tile";
import { Value, PnL } from "@/components/ui/value";
import { EmptyState } from "@/components/ui/states";
import { useStore } from "@/store/useStore";
import { useMarketStore } from "@/hooks/useMarketData";
import { safeDiv } from "@/lib/utils";

/**
 * PortfolioSection — account equity + performance, driven entirely by real data.
 *
 * `portfolio` is populated by the WS `balance_update` frame (see useMarketData);
 * `activeTrades` is the live open-positions set. There are NO fabricated numbers:
 * before the feed delivers anything we show an honest waiting state, and any
 * metric the backend doesn't provide renders as "—" via the primitives.
 */
export function PortfolioSection() {
    const { portfolio, activeTrades } = useStore();
    const status = useMarketStore((s) => s.status);

    // Have we ever received real account data? balance_update sets these > 0.
    const hasData =
        portfolio.totalValue > 0 ||
        portfolio.balance > 0 ||
        portfolio.totalTrades > 0;

    const usdtAllocationPct = safeDiv(portfolio.balance, portfolio.totalValue) * 100;

    return (
        <div className="space-y-8">
            <SectionHeader
                title="Portfolio"
                description="Account equity, allocation, and lifetime performance"
                icon={Wallet}
                iconColor="bg-accent-muted text-accent-300"
            />

            {!hasData ? (
                <Card>
                    <EmptyState
                        icon={<Wallet />}
                        title={status === "open" ? "No account data yet" : "Waiting for the live feed"}
                        description={
                            status === "open"
                                ? "Account equity and balances will appear here as soon as the backend reports them."
                                : "Portfolio metrics stream from the trading backend. They’ll populate once the feed connects."
                        }
                    />
                </Card>
            ) : (
                <>
                    {/* Equity + balance breakdown */}
                    <div className="grid gap-4 md:grid-cols-3">
                        <Card className="gap-4 md:col-span-2">
                            <div className="flex items-start justify-between px-4">
                                <div className="space-y-1.5">
                                    <div className="label-md">Total Portfolio Value</div>
                                    <Value
                                        value={portfolio.totalValue}
                                        prefix="$"
                                        decimals={2}
                                        className="financial-lg text-foreground"
                                    />
                                    <div className="flex items-center gap-2">
                                        <PnL value={portfolio.totalPnl} prefix="$" className="financial-xs" />
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
                                    <Value
                                        value={portfolio.balance}
                                        prefix="$"
                                        decimals={2}
                                        className="financial-xs text-foreground"
                                    />
                                </div>
                                <div className="space-y-1">
                                    <div className="body-xs">Total Invested</div>
                                    <Value
                                        value={portfolio.totalInvested}
                                        prefix="$"
                                        decimals={2}
                                        className="financial-xs text-foreground"
                                    />
                                </div>
                                <div className="space-y-1">
                                    <div className="body-xs">Unrealized P&amp;L</div>
                                    <PnL value={portfolio.unrealizedPnl} prefix="$" className="financial-xs" />
                                </div>
                            </div>
                        </Card>

                        {/* Real allocation: USDT balance + live open positions only. */}
                        <Card className="gap-4">
                            <div className="flex items-center gap-2 px-4">
                                <PieChart className="h-4 w-4 text-muted-foreground" />
                                <div className="label-md">Asset Allocation</div>
                            </div>
                            <div className="space-y-3 px-4">
                                <div className="space-y-1.5">
                                    <div className="flex items-center justify-between">
                                        <span className="body-sm text-foreground">USDT</span>
                                        <Value
                                            value={Number.isFinite(usdtAllocationPct) ? usdtAllocationPct : 0}
                                            decimals={1}
                                            suffix="%"
                                            className="body-sm text-muted-foreground"
                                        />
                                    </div>
                                    <div className="h-1.5 overflow-hidden rounded-full bg-elevated">
                                        <div
                                            className="h-full rounded-full bg-accent"
                                            style={{
                                                width: `${Math.min(Math.max(usdtAllocationPct, 0), 100)}%`,
                                            }}
                                        />
                                    </div>
                                </div>

                                {activeTrades.length === 0 ? (
                                    <p className="body-xs text-subtle-foreground">
                                        No open positions — capital is fully in USDT.
                                    </p>
                                ) : (
                                    activeTrades.map((trade) => (
                                        <div key={trade.id} className="space-y-1.5">
                                            <div className="flex items-center justify-between">
                                                <span className="body-sm text-foreground">{trade.symbol}</span>
                                                <PnL value={trade.pnl} prefix="$" className="text-xs" />
                                            </div>
                                            <div className="h-1.5 overflow-hidden rounded-full bg-elevated">
                                                <div className="h-full rounded-full bg-info" style={{ width: "100%" }} />
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>
                        </Card>
                    </div>

                    {/* Performance metrics — only real, backend-sourced values. */}
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                        <StatTile
                            label="Win Rate"
                            value={portfolio.winRate}
                            decimals={1}
                            suffix="%"
                            hint="Lifetime"
                        />
                        <StatTile
                            label="Total Trades"
                            value={portfolio.totalTrades}
                            hint="Executed"
                        />
                        <StatTile label="Realized P&L" hint="Locked in">
                            <PnL
                                value={portfolio.realizedPnl}
                                prefix="$"
                                className="text-lg font-semibold"
                            />
                        </StatTile>
                        <StatTile
                            label="Risk Score"
                            value="—"
                            hint="Not available yet"
                        />
                    </div>
                </>
            )}
        </div>
    );
}
