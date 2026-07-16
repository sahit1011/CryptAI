"use client";

import { useCallback, useEffect, useState } from "react";
import {
    Radar,
    TrendingUp,
    TrendingDown,
    Loader2,
    Zap,
    Bot,
    Hand,
    Beaker,
    Power,
    Target,
    ShieldAlert,
    Sparkles,
} from "lucide-react";
import { SectionHeader } from "../ui/SectionHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/states";
import { useStore, type Signal } from "@/store/useStore";
import {
    getSettings,
    saveSettings,
    getSetups,
    executeSetup,
    type TradingMode,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { formatMoney } from "@/lib/currency";

const MODES: { id: TradingMode; label: string; icon: typeof Bot; hint: string }[] = [
    { id: "off", label: "Off", icon: Power, hint: "Ignore setups — no trading." },
    { id: "paper", label: "Paper", icon: Beaker, hint: "Auto-trade a paper portfolio. No exchange, no risk." },
    { id: "manual", label: "Manual", icon: Hand, hint: "You place each setup yourself with one click." },
    { id: "auto", label: "Auto", icon: Bot, hint: "The AI places orders on your connected exchange." },
];

/**
 * Signals feed + trading-mode control. Shows the live trade-setup suggestions the
 * agents generate (shared across users), and lets the user choose how they're acted on:
 * Off / Paper (default) / Manual (Execute button) / Auto (agents place orders).
 */
export function SignalsSection() {
    const signals = useStore((s) => s.signals);
    const setSignals = useStore((s) => s.setSignals);
    const addSignal = useStore((s) => s.addSignal);

    const [mode, setMode] = useState<TradingMode>("paper");
    const [savingMode, setSavingMode] = useState<TradingMode | null>(null);
    const [modeError, setModeError] = useState<string | null>(null);

    // Hydrate recent setups + current mode on mount.
    useEffect(() => {
        (async () => {
            try {
                const { setups } = await getSetups();
                const mapped = setups.map(toSignal).filter(Boolean) as Signal[];
                if (mapped.length) setSignals(mapped);
            } catch {
                /* WS will still deliver live setups */
            }
            try {
                setMode((await getSettings()).trading_mode);
            } catch {
                /* keep default */
            }
        })();
    }, [setSignals]);

    const changeMode = useCallback(async (next: TradingMode) => {
        setSavingMode(next);
        setModeError(null);
        try {
            const saved = await saveSettings({ trading_mode: next });
            setMode(saved.trading_mode);
        } catch (e) {
            setModeError(e instanceof Error ? e.message : "Could not update mode");
        } finally {
            setSavingMode(null);
        }
    }, []);

    return (
        <div>
            <SectionHeader
                title="Signals"
                description="Live trade-setup suggestions from the AI agents. Choose how they're acted on — watch only, paper-trade, place them yourself, or let the agents trade your connected exchange."
                icon={Radar}
            />

            {/* Trading-mode selector */}
            <Card className="mb-6 gap-4 p-5">
                <div className="flex items-center gap-2">
                    <Sparkles className="size-4 text-accent" />
                    <h2 className="text-sm font-semibold text-foreground">Trading mode</h2>
                </div>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {MODES.map((m) => {
                        const Icon = m.icon;
                        const active = mode === m.id;
                        const busy = savingMode === m.id;
                        return (
                            <button
                                key={m.id}
                                onClick={() => changeMode(m.id)}
                                disabled={savingMode !== null}
                                className={cn(
                                    "flex flex-col gap-1.5 rounded-lg border px-4 py-3 text-left transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:opacity-60",
                                    active
                                        ? "border-accent/40 bg-accent-muted/40 text-foreground"
                                        : "border-border bg-elevated/30 text-muted-foreground hover:border-border-strong hover:text-foreground",
                                )}
                            >
                                <span className="flex items-center gap-2 text-sm font-medium">
                                    {busy ? <Loader2 className="size-4 animate-spin" /> : <Icon className={cn("size-4", active && "text-accent")} />}
                                    {m.label}
                                </span>
                                <span className="text-[11px] leading-snug text-subtle-foreground">{m.hint}</span>
                            </button>
                        );
                    })}
                </div>
                {modeError && <p className="text-sm text-loss">{modeError}</p>}
                {(mode === "manual" || mode === "auto") && (
                    <p className="flex items-center gap-1.5 text-xs text-subtle-foreground">
                        <ShieldAlert className="size-3" />
                        Real orders require a connected exchange (Connect tab) and stay testnet-gated.
                    </p>
                )}
            </Card>

            {/* Live setups */}
            {signals.length === 0 ? (
                <Card className="py-12">
                    <EmptyState
                        icon={<Radar className="size-6" />}
                        title="Waiting for setups"
                        description="The agents publish setups here as they find them each cycle. (Needs an LLM key configured on the backend to generate live suggestions.)"
                    />
                </Card>
            ) : (
                <div className="grid gap-4 md:grid-cols-2">
                    {signals.map((s) => (
                        <SignalCard key={s.id} signal={s} mode={mode} onExecuted={addSignal} />
                    ))}
                </div>
            )}
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
            onExecuted({ ...signal }); // refresh card ordering
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

            {/* Action row depends on mode */}
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

/** Map a backend /api/setups payload to a Signal. */
function toSignal(raw: Record<string, unknown>): Signal | null {
    const p = ((raw as { payload?: Record<string, unknown> }).payload ?? raw) as Record<string, unknown>;
    if (!p.symbol) return null;
    const tps = (Array.isArray(p.take_profit_levels) ? p.take_profit_levels : [])
        .map((tp) => (typeof tp === "object" && tp !== null ? Number((tp as Record<string, unknown>).price) : Number(tp)))
        .filter((n) => Number.isFinite(n));
    const entry = Number(p.entry_price) || 0;
    const stopLoss = Number(p.stop_loss) || 0;
    return {
        id: `${p.symbol}-${p.direction}-${entry}-${stopLoss}`,
        symbol: String(p.symbol),
        direction: String(p.direction) === "SHORT" ? "SHORT" : "LONG",
        entry,
        stopLoss,
        takeProfits: tps,
        confidence: p.confidence_score != null ? Number(p.confidence_score) : undefined,
        riskReward: p.risk_reward != null ? Number(p.risk_reward) : undefined,
        regime: p.market_regime ? String(p.market_regime) : undefined,
        strategy: p.strategy_type ? String(p.strategy_type) : undefined,
        reasoning: typeof p.reasoning === "string" ? p.reasoning : undefined,
        positionSize: p.recommended_position_size != null ? Number(p.recommended_position_size) : undefined,
        ts: new Date().toISOString(),
    };
}
