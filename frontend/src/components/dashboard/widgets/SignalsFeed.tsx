"use client";

import { useEffect, useState } from "react";
import {
    Beaker,
    Bot,
    Loader2,
    Radar,
    Target,
    TrendingDown,
    TrendingUp,
    Zap,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/states";
import { useStore, type Signal } from "@/store/useStore";
import { executeSetup, getEngine, getSettings, getSetups, type TradingMode } from "@/lib/api";
import { payloadToSignal } from "@/lib/signals";
import { formatMoney } from "@/lib/currency";
import { cn } from "@/lib/utils";

/**
 * Live AI trade-setup feed. Hydrates from GET /api/setups, then updates over the
 * WebSocket (`trade_setup` messages via useMarketData -> store.signals). Behavior of
 * each card follows the user's trading mode (Manual -> Execute button).
 */
export function SignalsFeed({ limit }: { limit?: number }) {
    const signals = useStore((s) => s.signals);
    const setSignals = useStore((s) => s.setSignals);
    const addSignal = useStore((s) => s.addSignal);
    const [mode, setMode] = useState<TradingMode>("paper");
    const [engineOn, setEngineOn] = useState<boolean | null>(null);

    useEffect(() => {
        (async () => {
            try {
                const { setups } = await getSetups();
                const mapped = setups.map(payloadToSignal).filter(Boolean) as Signal[];
                if (mapped.length) setSignals(mapped);
            } catch { /* WS still delivers live setups */ }
            try {
                setMode((await getSettings()).trading_mode);
            } catch { /* keep default */ }
            try {
                setEngineOn((await getEngine()).enabled);
            } catch { /* status is best-effort */ }
        })();
    }, [setSignals]);

    const shown = limit ? signals.slice(0, limit) : signals;

    if (shown.length === 0) {
        // Distinguish "engine paused" (no analysis running) from "engine on, no setup yet"
        // so an empty feed is never mysterious.
        const paused = engineOn === false;
        return (
            <Card className="py-4">
                <EmptyState
                    icon={<Radar className="size-6" />}
                    title={paused ? "AI engine is paused" : "Waiting for AI setups"}
                    description={
                        paused
                            ? "The trading agents aren't analyzing the markets right now. An admin can start the engine in Settings to generate fresh setups."
                            : "The agents publish trade setups here as they find them each analysis cycle."
                    }
                />
            </Card>
        );
    }

    return (
        <div className="grid gap-4 md:grid-cols-2">
            {shown.map((s) => (
                <SignalCard key={s.id} signal={s} mode={mode} onExecuted={addSignal} />
            ))}
        </div>
    );
}

function SignalCard({
    signal,
    mode,
    onExecuted,
}: {
    signal: Signal;
    mode: TradingMode;
    onExecuted: (s: Signal) => void;
}) {
    const [executing, setExecuting] = useState(false);
    const [result, setResult] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const long = signal.direction === "LONG";

    async function handleExecute() {
        setExecuting(true);
        setError(null);
        try {
            const r = await executeSetup({
                symbol: signal.symbol,
                direction: signal.direction,
                entry_price: signal.entry,
                stop_loss: signal.stopLoss,
                take_profit_levels: signal.takeProfits,
                confidence_score: signal.confidence,
                market_regime: signal.regime,
                recommended_position_size: signal.positionSize,
            });
            setResult(String(r.status ?? "submitted"));
            onExecuted({ ...signal });
        } catch (e) {
            setError(e instanceof Error ? e.message : "Execution failed");
        } finally {
            setExecuting(false);
        }
    }

    return (
        <Card className="gap-4 p-5">
            <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2.5">
                    <div
                        className={cn(
                            "flex size-9 items-center justify-center rounded-lg border",
                            long ? "border-profit/25 bg-profit/10 text-profit" : "border-loss/25 bg-loss/10 text-loss",
                        )}
                    >
                        {long ? <TrendingUp className="size-5" /> : <TrendingDown className="size-5" />}
                    </div>
                    <div>
                        <p className="text-sm font-semibold text-foreground">{signal.symbol}</p>
                        <p className={cn("text-xs font-medium", long ? "text-profit" : "text-loss")}>
                            {signal.direction}
                            {signal.strategy ? <span className="text-subtle-foreground"> · {signal.strategy}</span> : null}
                        </p>
                    </div>
                </div>
                <div className="flex flex-col items-end gap-1 text-right">
                    {signal.confidence != null && (
                        <span className="rounded-md border border-border bg-elevated px-2 py-0.5 text-[11px] font-medium text-foreground">
                            {Math.round(signal.confidence * (signal.confidence <= 1 ? 100 : 1))}% conf
                        </span>
                    )}
                    {signal.riskReward != null && (
                        <span className="text-[11px] text-subtle-foreground">R:R {signal.riskReward.toFixed(2)}</span>
                    )}
                </div>
            </div>

            <div className="grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-border bg-border text-center">
                <Level label="Entry" value={signal.entry} />
                <Level label="Stop" value={signal.stopLoss} accent="text-loss" />
                <Level label="Target" value={signal.takeProfits[0]} accent="text-profit" icon={Target} />
            </div>

            {signal.reasoning && (
                <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">{signal.reasoning}</p>
            )}

            <div className="flex items-center justify-between gap-3 border-t border-border pt-3">
                <span className="text-[11px] text-subtle-foreground">
                    {signal.regime ? signal.regime.replace(/_/g, " ").toLowerCase() : "suggestion"}
                </span>
                {mode === "manual" ? (
                    <Button size="sm" onClick={handleExecute} disabled={executing || result != null}>
                        {executing ? <Loader2 className="size-4 animate-spin" /> : <Zap className="size-4" />}
                        {result ? "Submitted" : executing ? "Placing…" : "Execute"}
                    </Button>
                ) : mode === "auto" ? (
                    <span className="flex items-center gap-1.5 text-xs text-accent"><Bot className="size-3.5" /> auto-trading</span>
                ) : mode === "paper" ? (
                    <span className="flex items-center gap-1.5 text-xs text-subtle-foreground"><Beaker className="size-3.5" /> paper</span>
                ) : (
                    <span className="text-xs text-subtle-foreground">watching</span>
                )}
            </div>
            {error && <p className="text-xs text-loss">{error}</p>}
        </Card>
    );
}

function Level({
    label,
    value,
    accent,
    icon: Icon,
}: {
    label: string;
    value?: number;
    accent?: string;
    icon?: typeof Target;
}) {
    const rate = useStore((s) => s.inrRate);
    const currency = useStore((s) => s.currency);
    return (
        <div className="bg-card px-3 py-2.5">
            <p className="mb-0.5 flex items-center justify-center gap-1 text-[10px] font-medium uppercase tracking-wider text-subtle-foreground">
                {Icon && <Icon className="size-3" />}
                {label}
            </p>
            <p className={cn("font-mono text-sm font-medium tabular-nums text-foreground", accent)}>
                {value != null && Number.isFinite(value) ? formatMoney(value, currency, rate, 2) : "—"}
            </p>
        </div>
    );
}
