"use client";

import { useEffect, useState } from "react";
import { SectionHeader } from "../ui/SectionHeader";
import { GlassCard } from "@/components/ui/glass-card";
import { Button } from "@/components/ui/button";
import {
    LayoutDashboard,
    TrendingUp,
    Activity,
    Zap,
    BarChart3,
    ArrowUpRight,
    ArrowDownRight,
} from "lucide-react";
import { useStore, Trade } from "@/store/useStore";
import { useMarketStore } from "@/hooks/useMarketData";
import { API_URL, apiHeaders } from "@/lib/api";

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
                    cache: 'no-store',
                    headers: apiHeaders(),
                });

                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

                const data = await response.json();
                if (data.trades && Array.isArray(data.trades)) {
                    setRecentTrades(data.trades);
                    console.log('📊 Loaded recent trades from database:', data.trades);
                } else {
                    throw new Error('Invalid data format received');
                }
            } catch (error) {
                console.error('Failed to fetch recent trades:', error);
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

    // Helper to format values with fallback for empty state
    const formatCurrency = (value: number | undefined) => {
        if (value === undefined || value === null) return "---";
        if (!isConnected && value === 0) return "---";
        return `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    };

    const formatPercent = (value: number | undefined) => {
        if (value === undefined || value === null) return "---";
        if (!isConnected && value === 0) return "---";
        return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
    };

    const isPnlPositive = portfolio.totalPnl >= 0;
    const hasData = isConnected && (portfolio.totalValue > 0 || portfolio.balance > 0);

    // Filter trades - more robust check
    const closedTrades = recentTrades.filter(trade =>
        (trade.status && trade.status.toUpperCase() === 'CLOSED') ||
        trade.exitTime !== null
    ).slice(0, 10);

    const dbActiveTrades = recentTrades.filter(trade =>
        (!trade.status || trade.status.toUpperCase() === 'OPEN') &&
        !trade.exitTime
    );

    return (
        <div className="space-y-8">
            {/* Header with Connection Status */}
            <div className="flex items-center justify-between">
                <SectionHeader
                    title="Overview"
                    description="Monitor live trading performance and multi-agent system health"
                    icon={LayoutDashboard}
                    iconColor="bg-emerald-500/10 text-emerald-400"
                />
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/5 border border-white/10">
                    <div className={`h-2 w-2 rounded-full ${isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`} />
                    <span className={`text-xs font-medium ${isConnected ? 'text-emerald-400' : 'text-red-400'}`}>
                        {isConnected ? 'Connected' : 'Disconnected'}
                    </span>
                </div>
            </div>

            {/* Stats Grid */}
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
                <GlassCard className="p-6 relative overflow-hidden group hover:border-emerald-500/20 transition-all">
                    <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
                        <TrendingUp className="w-20 h-20" />
                    </div>
                    <div className="relative z-10 space-y-4">
                        <div className="flex items-center justify-between">
                            <span className="label-md text-muted-foreground">Portfolio Value</span>
                            <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
                                <TrendingUp className="h-4 w-4" />
                            </div>
                        </div>
                        <div className="financial-lg text-white">{formatCurrency(portfolio.totalValue)}</div>
                        {hasData && portfolio.totalPnlPercent !== 0 && (
                            <div className={`flex items-center gap-1 ${isPnlPositive ? 'text-emerald-400' : 'text-red-400'}`}>
                                {isPnlPositive ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                                <span className="body-sm font-medium">{formatPercent(portfolio.totalPnlPercent)} total</span>
                            </div>
                        )}
                        {!hasData && (
                            <div className="text-muted-foreground body-sm">
                                Waiting for data...
                            </div>
                        )}
                    </div>
                </GlassCard>

                <GlassCard className="p-6 relative overflow-hidden group hover:border-cyan-500/20 transition-all">
                    <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
                        <Activity className="w-20 h-20" />
                    </div>
                    <div className="relative z-10 space-y-4">
                        <div className="flex items-center justify-between">
                            <span className="label-md text-muted-foreground">Total P&L</span>
                            <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400">
                                <Activity className="h-4 w-4" />
                            </div>
                        </div>
                        <div className={`financial-lg ${isPnlPositive ? 'text-emerald-400' : 'text-red-400'}`}>
                            {formatCurrency(portfolio.totalPnl)}
                        </div>
                        {hasData && portfolio.totalPnlPercent !== 0 && (
                            <div className={`flex items-center gap-1 ${isPnlPositive ? 'text-emerald-400' : 'text-red-400'}`}>
                                {isPnlPositive ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                                <span className="body-sm font-medium">{formatPercent(portfolio.totalPnlPercent)}</span>
                            </div>
                        )}
                        {!hasData && (
                            <div className="text-muted-foreground body-sm">
                                No trades yet
                            </div>
                        )}
                    </div>
                </GlassCard>

                <GlassCard className="p-6 relative overflow-hidden group hover:border-purple-500/20 transition-all">
                    <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
                        <Zap className="w-20 h-20" />
                    </div>
                    <div className="relative z-10 space-y-4">
                        <div className="flex items-center justify-between">
                            <span className="label-md text-muted-foreground">Active Trades</span>
                            <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400">
                                <Zap className="h-4 w-4" />
                            </div>
                        </div>
                        <div className="financial-lg text-white">{activeTrades.length}</div>
                        <div className="flex items-center gap-1 text-muted-foreground">
                            <span className="body-sm">
                                {portfolio.totalTrades > 0 ? `${portfolio.totalTrades} total trades` : 'No trades executed'}
                            </span>
                        </div>
                    </div>
                </GlassCard>

                <GlassCard className="p-6 relative overflow-hidden group hover:border-orange-500/20 transition-all">
                    <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
                        <BarChart3 className="w-20 h-20" />
                    </div>
                    <div className="relative z-10 space-y-4">
                        <div className="flex items-center justify-between">
                            <span className="label-md text-muted-foreground">Win Rate</span>
                            <div className="p-2 rounded-lg bg-orange-500/10 text-orange-400">
                                <BarChart3 className="h-4 w-4" />
                            </div>
                        </div>
                        <div className="financial-lg text-white">
                            {!isConnected && (!portfolio.winRate || portfolio.winRate === 0) ? '---' : `${(portfolio.winRate || 0).toFixed(1)}%`}
                        </div>
                        <div className="flex items-center gap-1 text-muted-foreground">
                            <span className="body-sm">
                                {portfolio.totalTrades > 0 ? `${portfolio.totalTrades} trades` : 'No data'}
                            </span>
                        </div>
                    </div>
                </GlassCard>
            </div>

            {/* Recent Closed Trades - Shows historical closed trades from database */}
            <GlassCard className="p-6">
                <div className="flex items-center justify-between mb-4">
                    <div className="heading-4 text-white">Recent Closed Trades</div>
                    <div className="text-xs text-muted-foreground">
                        Last {closedTrades.length} closed trades
                    </div>
                </div>
                <div className="space-y-2">
                    {loadingTrades && (
                        <div className="text-center text-muted-foreground text-sm py-10">
                            Loading trade history...
                        </div>
                    )}
                    {!loadingTrades && closedTrades.length === 0 && (
                        <div className="text-center text-muted-foreground text-sm py-10">
                            {isConnected ? 'No closed trades found' : 'Connect to backend to see trade history'}
                            <div className="text-xs mt-2 opacity-50">
                                {dbActiveTrades.length > 0 ? `${dbActiveTrades.length} active trades are currently running` : 'Trades will appear here after they are closed'}
                            </div>
                        </div>
                    )}
                    {/* Show only closed trades from database */}
                    {closedTrades.map((trade) => {
                        const tradePnl = trade.pnl ?? 0;
                        const isProfitable = tradePnl >= 0;

                        // Format dates
                        const entryDate = trade.entryTime ? new Date(trade.entryTime).toLocaleString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit'
                        }) : 'N/A';

                        const exitDate = trade.exitTime ? new Date(trade.exitTime).toLocaleString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit'
                        }) : 'N/A';

                        return (
                            <div
                                key={trade.id}
                                className="flex items-center justify-between py-3 px-4 border border-white/5 rounded-lg hover:bg-white/5 transition-colors"
                            >
                                <div className="flex items-center gap-3 flex-1">
                                    <div className={`w-2 h-2 rounded-full ${isProfitable ? 'bg-emerald-400' : 'bg-red-400'}`} />
                                    <div className="flex-1">
                                        <div className="flex items-center gap-2 mb-1">
                                            <span className="body-sm text-white font-medium">
                                                {trade.side} {trade.symbol}
                                            </span>
                                            <span className="text-xs text-muted-foreground">
                                                ● CLOSED
                                            </span>
                                        </div>
                                        <div className="body-xs text-muted-foreground space-y-0.5">
                                            <div className="flex items-center gap-3">
                                                <span>Entry: ${trade.entry?.toLocaleString() ?? 'N/A'}</span>
                                                <span className="text-white/40">→</span>
                                                <span>Exit: ${trade.current?.toLocaleString() ?? 'N/A'}</span>
                                            </div>
                                            <div className="flex items-center gap-3">
                                                <span>Opened: {entryDate}</span>
                                                <span className="text-white/40">→</span>
                                                <span>Closed: {exitDate}</span>
                                            </div>
                                            {trade.exitReason && (
                                                <div className="text-xs text-white/30">
                                                    Reason: {trade.exitReason}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                                <div className="text-right ml-4">
                                    <div className={`financial-sm font-medium ${isProfitable ? 'text-emerald-400' : 'text-red-400'}`}>
                                        {isProfitable ? '+' : ''}${tradePnl.toFixed(2)}
                                    </div>
                                    <div className={`body-xs ${isProfitable ? 'text-emerald-400/70' : 'text-red-400/70'}`}>
                                        {(trade.pnlPercent ?? 0) >= 0 ? '+' : ''}{(trade.pnlPercent ?? 0).toFixed(2)}%
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
                {/* Footer showing active trades count */}
                {dbActiveTrades.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-white/5 text-center">
                        <span className="text-xs text-blue-400/70">
                            {dbActiveTrades.length} active trades currently running (monitored separately)
                        </span>
                    </div>
                )}

                {/* Surface fetch errors without dumping raw trade JSON into the UI. */}
                {error && (
                    <div className="mt-4 text-xs text-red-400">
                        Failed to load trade history: {error}
                    </div>
                )}
            </GlassCard>
        </div>
    );
}
