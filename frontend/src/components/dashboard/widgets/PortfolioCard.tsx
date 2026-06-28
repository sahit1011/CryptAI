"use client";

import { GlassCard } from "@/components/ui/glass-card";
import { ArrowUpRight, ArrowDownRight, TrendingUp } from "lucide-react";
import { safeNum, safeFixed } from "@/lib/utils";

interface PortfolioCardProps {
    symbol?: string;
    name?: string;
    amount?: number;
    value?: number;
    change?: number;
    changePercent?: number;
}

export function PortfolioCard({
    symbol = "BTC",
    name = "Bitcoin",
    amount = 0.5432,
    value = 24500.00,
    change = 1250.00,
    changePercent = 5.4,
}: PortfolioCardProps) {
    // Network-sourced numbers can arrive as NaN/undefined; normalize before math.
    const safeAmount = safeNum(amount);
    const safeValue = safeNum(value);
    const safeChange = safeNum(change);
    const safeChangePercent = safeNum(changePercent);
    const isPositive = safeChangePercent >= 0;
    const allocationPct = safeValue > 0 ? (safeValue / 50000) * 100 : 0;

    return (
        <GlassCard className="p-6 relative overflow-hidden group hover:border-emerald-500/20 transition-all">
            {/* Background Icon */}
            <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
                <TrendingUp className="w-20 h-20" />
            </div>

            <div className="relative z-10 space-y-4">
                {/* Header */}
                <div className="flex items-start justify-between">
                    <div>
                        <div className="flex items-center gap-2">
                            <h3 className="text-lg font-bold text-white">{symbol}</h3>
                            <span className="text-xs px-2 py-0.5 rounded-full bg-white/5 text-muted-foreground">
                                {name}
                            </span>
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">
                            {safeAmount.toFixed(4)} {symbol}
                        </p>
                    </div>

                    <div
                        className={`p-2 rounded-lg ${isPositive
                                ? "bg-emerald-500/10 text-emerald-400"
                                : "bg-red-500/10 text-red-400"
                            }`}
                    >
                        {isPositive ? (
                            <ArrowUpRight className="h-4 w-4" />
                        ) : (
                            <ArrowDownRight className="h-4 w-4" />
                        )}
                    </div>
                </div>

                {/* Value */}
                <div>
                    <div className="text-2xl font-mono font-bold text-white">
                        ${safeValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                        <span
                            className={`text-sm font-medium ${isPositive ? "text-emerald-400" : "text-red-400"
                                }`}
                        >
                            {isPositive ? "+" : ""}${safeFixed(safeChange, 2)}
                        </span>
                        <span
                            className={`text-xs ${isPositive ? "text-emerald-400" : "text-red-400"
                                }`}
                        >
                            ({isPositive ? "+" : ""}{safeFixed(safeChangePercent, 2)}%)
                        </span>
                    </div>
                </div>

                {/* Progress Bar */}
                <div className="space-y-1">
                    <div className="flex justify-between text-xs text-muted-foreground">
                        <span>Portfolio Allocation</span>
                        <span>{allocationPct.toFixed(1)}%</span>
                    </div>
                    <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                        <div
                            className="h-full bg-gradient-to-r from-emerald-400 to-cyan-400 rounded-full transition-all duration-500"
                            style={{ width: `${Math.min(allocationPct, 100)}%` }}
                        />
                    </div>
                </div>
            </div>
        </GlassCard>
    );
}
