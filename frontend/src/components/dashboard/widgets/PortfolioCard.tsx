"use client";

import { Card } from "@/components/ui/card";
import { Value, PnL } from "@/components/ui/value";
import { EmptyState } from "@/components/ui/states";
import { ArrowUpRight, ArrowDownRight, Wallet } from "lucide-react";
import { cn, safeNum } from "@/lib/utils";

/*
 * A single holding tile. All numeric props come from the caller (real backend
 * data). When no position value is supplied we render an honest empty state
 * rather than fabricated placeholder holdings.
 */
interface PortfolioCardProps {
    symbol?: string;
    name?: string;
    /** Position size in the base asset. */
    amount?: number;
    /** Current position value in quote (USD). */
    value?: number;
    /** Absolute PnL in quote (USD). */
    change?: number;
    /** PnL as a percentage. */
    changePercent?: number;
    /** Fraction of the whole portfolio this holding represents (0–1). */
    allocation?: number;
}

export function PortfolioCard({
    symbol = "—",
    name,
    amount,
    value,
    change,
    changePercent,
    allocation,
}: PortfolioCardProps) {
    const hasValue = value != null && Number.isFinite(value);

    if (!hasValue) {
        return (
            <Card className="h-full justify-center">
                <EmptyState
                    icon={<Wallet />}
                    title="No position"
                    description={`No open ${symbol !== "—" ? symbol : "asset"} holding to display.`}
                />
            </Card>
        );
    }

    const safeChangePercent = safeNum(changePercent);
    const isPositive = safeChangePercent >= 0;
    const allocationPct = allocation != null ? safeNum(allocation) * 100 : null;

    return (
        <Card className="relative overflow-hidden py-0">
            <div className="p-5">
                <div className="flex items-start justify-between">
                    <div>
                        <div className="flex items-center gap-2">
                            <h3 className="text-base font-semibold text-foreground">{symbol}</h3>
                            {name ? (
                                <span className="rounded-md bg-elevated px-2 py-0.5 text-xs text-muted-foreground">
                                    {name}
                                </span>
                            ) : null}
                        </div>
                        {amount != null ? (
                            <Value
                                value={amount}
                                decimals={4}
                                suffix={` ${symbol}`}
                                className="mt-1 block text-xs text-muted-foreground"
                            />
                        ) : null}
                    </div>

                    <div
                        className={cn(
                            "rounded-md p-2",
                            isPositive ? "bg-profit-muted text-profit" : "bg-loss-muted text-loss",
                        )}
                    >
                        {isPositive ? (
                            <ArrowUpRight className="h-4 w-4" />
                        ) : (
                            <ArrowDownRight className="h-4 w-4" />
                        )}
                    </div>
                </div>

                <div className="mt-4">
                    <Value
                        value={value}
                        decimals={2}
                        money
                        className="text-2xl font-semibold text-foreground"
                    />
                    <div className="mt-1 flex items-center gap-2">
                        <PnL value={change} decimals={2} money className="text-sm" />
                        <PnL
                            value={safeChangePercent}
                            decimals={2}
                            percent
                            chip
                            className="text-xs"
                        />
                    </div>
                </div>

                {allocationPct != null ? (
                    <div className="mt-4 space-y-1.5">
                        <div className="flex justify-between text-xs text-muted-foreground">
                            <span>Portfolio Allocation</span>
                            <Value value={allocationPct} decimals={1} suffix="%" />
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-elevated">
                            <div
                                className="h-full rounded-full bg-accent transition-all duration-500"
                                style={{ width: `${Math.min(Math.max(allocationPct, 0), 100)}%` }}
                            />
                        </div>
                    </div>
                ) : null}
            </div>
        </Card>
    );
}
