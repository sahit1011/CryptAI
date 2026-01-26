
"use client";

import { SectionHeader } from "../ui/SectionHeader";
import { GlassCard } from "@/components/ui/glass-card";
import { PortfolioCard } from "../widgets/PortfolioCard";
import { Wallet, Download, TrendingUp, ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useStore } from "@/store/useStore";

export function PortfolioSection() {
    const { portfolio, activeTrades } = useStore();

    return (
        <div className="space-y-8">
            {/* Header */}
            <SectionHeader
                title="Portfolio"
                description="Track your crypto assets and performance metrics"
                icon={Wallet}
                iconColor="bg-emerald-500/10 text-emerald-400"
                actions={
                    <Button
                        variant="outline"
                        className="border-white/10 bg-white/5 hover:bg-white/10 hover:text-white"
                    >
                        <Download className="mr-2 h-4 w-4" /> Export Report
                    </Button>
                }
            />

            {/* Portfolio Summary */}
            <div className="grid gap-6 md:grid-cols-3">
                <GlassCard className="p-6 md:col-span-2">
                    <div className="space-y-4">
                        <div className="flex items-start justify-between">
                            <div>
                                <div className="label-md text-muted-foreground mb-2">
                                    Total Portfolio Value
                                </div>
                                <div className="financial-lg text-white">${portfolio.totalValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                            </div>
                            <div className="p-3 rounded-xl bg-emerald-500/10 text-emerald-400">
                                <TrendingUp className="w-6 h-6" />
                            </div>
                        </div>

                        <div className="grid grid-cols-3 gap-4 pt-4 border-t border-white/10">
                            <div>
                                <div className="body-xs text-muted-foreground mb-1">24h Change</div>
                                <div className={`flex items-center gap-1 ${portfolio.totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                    <ArrowUpRight className={`w-3 h-3 ${portfolio.totalPnl < 0 ? 'rotate-180' : ''}`} />
                                    <span className="financial-sm">{portfolio.totalPnl >= 0 ? '+' : ''}${portfolio.totalPnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                                </div>
                                <div className={`body-xs ${portfolio.totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{portfolio.totalPnl >= 0 ? '+' : ''}{portfolio.totalPnlPercent.toFixed(2)}%</div>
                            </div>
                            <div>
                                <div className="body-xs text-muted-foreground mb-1">Total Invested</div>
                                <div className="financial-sm text-white">${portfolio.totalInvested.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                            </div>
                            <div>
                                <div className="body-xs text-muted-foreground mb-1">Available Balance</div>
                                <div className="financial-sm text-white">${portfolio.balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                            </div>
                        </div>
                    </div>
                </GlassCard>

                <GlassCard className="p-6">
                    <div className="space-y-4">
                        <div className="label-md text-muted-foreground">Asset Allocation</div>
                        <div className="space-y-3">
                            <div>
                                <div className="flex items-center justify-between mb-2">
                                    <span className="body-sm text-white">USDT</span>
                                    <span className="body-sm text-muted-foreground">
                                        {portfolio.totalValue > 0
                                            ? `${(portfolio.balance / portfolio.totalValue * 100).toFixed(1)}%`
                                            : '0.0%'}
                                    </span>
                                </div>
                                <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-gradient-to-r from-emerald-400 to-cyan-400"
                                        style={{ width: `${portfolio.totalValue > 0 ? (portfolio.balance / portfolio.totalValue * 100) : 0}%` }}
                                    />
                                </div>
                            </div>
                            {/* Dynamically list other assets based on active trades */}
                            {activeTrades.map(trade => (
                                <div key={trade.symbol}>
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="body-sm text-white">{trade.symbol}</span>
                                        <span className="body-sm text-muted-foreground">Active</span>
                                    </div>
                                    <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                                        <div
                                            className="h-full bg-gradient-to-r from-purple-400 to-pink-400"
                                            style={{ width: "100%" }}
                                        />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </GlassCard>
            </div>

            {/* Asset Holdings */}
            <div>
                <div className="heading-4 text-white mb-6">Your Assets</div>
                <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                    <PortfolioCard
                        symbol="USDT"
                        name="Tether"
                        amount={portfolio.balance}
                        value={portfolio.balance}
                        change={0}
                        changePercent={0}
                    />
                    {/* Add other assets here if we had a full wallet manager */}
                </div>
            </div>

            {/* Performance Metrics */}
            <div className="grid gap-6 md:grid-cols-4">
                <GlassCard className="p-6">
                    <div className="label-md text-muted-foreground mb-3">Win Rate</div>
                    <div className="financial-md text-white mb-1">{portfolio.winRate.toFixed(1)}%</div>
                    <div className="body-xs text-muted-foreground">Lifetime</div>
                </GlassCard>

                <GlassCard className="p-6">
                    <div className="label-md text-muted-foreground mb-3">Total Trades</div>
                    <div className="financial-md text-white mb-1">{portfolio.totalTrades}</div>
                    <div className="body-xs text-emerald-400">Executed</div>
                </GlassCard>

                <GlassCard className="p-6">
                    <div className="label-md text-muted-foreground mb-3">Realized P&L</div>
                    <div className={`financial-md mb-1 ${portfolio.realizedPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>${portfolio.realizedPnl.toLocaleString()}</div>
                    <div className="body-xs text-muted-foreground">Locked in</div>
                </GlassCard>

                <GlassCard className="p-6">
                    <div className="label-md text-muted-foreground mb-3">Risk Score</div>
                    <div className="financial-md text-orange-400 mb-1">4.2/10</div>
                    <div className="body-xs text-muted-foreground">Moderate</div>
                </GlassCard>
            </div>
        </div>
    );
}
