"use client";

import { useEffect, useState } from "react";
import { Loader2, Target } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/ui/states";
import { cn } from "@/lib/utils";
import {
    getPreferences,
    savePreferences,
    type RiskAppetite,
    type TradingPreferences,
} from "@/lib/api";
import {
    RISK_APPETITES,
    TRADING_STYLES,
    changedFields,
    parseSymbolUniverse,
    symbolUniverseText,
} from "@/lib/preferences";

/*
 * TradingPersona — the per-user preferences the session pipeline reads: default
 * trading style (channel), the 30-day PnL goal, the symbol universe, and risk appetite.
 * Saves only the fields that changed; the backend clamps risk to the plan (this form
 * never widens risk, only sends what the user touched).
 */

type Draft = {
    goal_horizon: TradingPreferences["goal_horizon"];
    risk_appetite: RiskAppetite;
    monthly_pnl_target_pct: string; // free text; parsed on save
    symbols: string;                // free text; parsed on save
    goal_notes: string;
};

function toDraft(p: TradingPreferences): Draft {
    return {
        goal_horizon: p.goal_horizon,
        risk_appetite: p.risk_appetite,
        monthly_pnl_target_pct: p.monthly_pnl_target_pct != null ? String(p.monthly_pnl_target_pct) : "",
        symbols: symbolUniverseText(p.symbol_universe),
        goal_notes: p.goal_notes ?? "",
    };
}

export function TradingPersona() {
    const [prefs, setPrefs] = useState<TradingPreferences | null>(null);
    const [draft, setDraft] = useState<Draft | null>(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [saved, setSaved] = useState(false);

    useEffect(() => {
        let cancelled = false;
        getPreferences()
            .then((p) => {
                if (cancelled) return;
                setPrefs(p);
                setDraft(toDraft(p));
            })
            .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)))
            .finally(() => !cancelled && setLoading(false));
        return () => {
            cancelled = true;
        };
    }, []);

    if (loading) {
        return (
            <Card className="mb-8 p-5">
                <LoadingState title="Loading your preferences…" />
            </Card>
        );
    }
    if (!prefs || !draft) {
        return (
            <Card className="mb-8 p-5">
                <p className="text-sm text-loss">{error ?? "Preferences unavailable."}</p>
            </Card>
        );
    }

    const set = <K extends keyof Draft>(key: K, value: Draft[K]) => {
        setDraft((d) => (d ? { ...d, [key]: value } : d));
        setSaved(false);
    };

    async function onSave() {
        if (!prefs || !draft) return;
        setSaving(true);
        setError(null);
        setSaved(false);

        const target = draft.monthly_pnl_target_pct.trim();
        const edited: Partial<TradingPreferences> = {
            goal_horizon: draft.goal_horizon,
            risk_appetite: draft.risk_appetite,
            symbol_universe: parseSymbolUniverse(draft.symbols),
            goal_notes: draft.goal_notes.trim() || null,
        };
        // Only send a numeric target when it parses; an emptied field is left unchanged
        // rather than sent as null (the backend field is gt=0, not nullable via POST).
        const parsedTarget = target === "" ? prefs.monthly_pnl_target_pct : Number(target);
        if (target !== "" && Number.isFinite(parsedTarget)) {
            edited.monthly_pnl_target_pct = parsedTarget as number;
        }

        const diff = changedFields(prefs, edited);
        if (Object.keys(diff).length === 0) {
            setSaving(false);
            setSaved(true);
            return;
        }
        try {
            const updated = await savePreferences(diff);
            setPrefs(updated);
            setDraft(toDraft(updated)); // reflect any server-side clamping
            setSaved(true);
        } catch (e) {
            setError(e instanceof Error ? e.message : "Could not save your preferences");
        } finally {
            setSaving(false);
        }
    }

    return (
        <Card className="mb-8 gap-5 p-5">
            <div className="flex items-center gap-2">
                <Target className="size-4 text-accent" />
                <h2 className="text-sm font-semibold text-foreground">Trading preferences</h2>
                <span className="ml-auto text-[11px] text-muted-foreground">
                    the agents synthesise setups against these
                </span>
            </div>

            {/* Default trading style (the channel) */}
            <div>
                <Label className="mb-2 block text-xs text-muted-foreground">Default trading style</Label>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {TRADING_STYLES.map((s) => {
                        const active = draft.goal_horizon === s.value;
                        return (
                            <button
                                key={s.value}
                                type="button"
                                onClick={() => set("goal_horizon", s.value)}
                                aria-pressed={active}
                                className={cn(
                                    "flex flex-col gap-1 rounded-lg border px-3 py-2.5 text-left transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
                                    active
                                        ? "border-accent/40 bg-accent-muted/40 text-foreground"
                                        : "border-border bg-elevated/30 text-muted-foreground hover:border-border-strong hover:text-foreground",
                                )}
                            >
                                <span className="text-sm font-medium">{s.label}</span>
                                <span className="text-[11px] leading-tight text-muted-foreground">{s.blurb}</span>
                            </button>
                        );
                    })}
                </div>
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
                {/* Risk appetite */}
                <div>
                    <Label className="mb-2 block text-xs text-muted-foreground">Risk appetite</Label>
                    <div className="grid grid-cols-3 gap-2">
                        {RISK_APPETITES.map((r) => {
                            const active = draft.risk_appetite === r.value;
                            return (
                                <button
                                    key={r.value}
                                    type="button"
                                    onClick={() => set("risk_appetite", r.value)}
                                    aria-pressed={active}
                                    className={cn(
                                        "rounded-md border px-2 py-2 text-xs font-medium transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
                                        active
                                            ? "border-accent/40 bg-accent-muted/40 text-foreground"
                                            : "border-border bg-elevated/30 text-muted-foreground hover:text-foreground",
                                    )}
                                >
                                    {r.label}
                                </button>
                            );
                        })}
                    </div>
                </div>

                {/* 30-day PnL goal */}
                <div>
                    <Label htmlFor="pnl-goal" className="mb-2 block text-xs text-muted-foreground">
                        30-day PnL goal (%)
                    </Label>
                    <Input
                        id="pnl-goal"
                        inputMode="decimal"
                        placeholder="e.g. 15"
                        value={draft.monthly_pnl_target_pct}
                        onChange={(e) => set("monthly_pnl_target_pct", e.target.value)}
                    />
                </div>
            </div>

            {/* Symbol universe */}
            <div>
                <Label htmlFor="symbols" className="mb-2 block text-xs text-muted-foreground">
                    Your coins <span className="text-muted-foreground/70">(comma-separated; blank = platform default)</span>
                </Label>
                <Input
                    id="symbols"
                    placeholder="BTC, ETH, SOL"
                    value={draft.symbols}
                    onChange={(e) => set("symbols", e.target.value)}
                />
            </div>

            {/* Goal notes */}
            <div>
                <Label htmlFor="goal-notes" className="mb-2 block text-xs text-muted-foreground">
                    Notes for the agents <span className="text-muted-foreground/70">(optional)</span>
                </Label>
                <Input
                    id="goal-notes"
                    placeholder="e.g. avoid trading around funding; prefer trend continuation"
                    value={draft.goal_notes}
                    onChange={(e) => set("goal_notes", e.target.value)}
                />
            </div>

            {error ? <p className="text-xs text-loss">{error}</p> : null}

            <div className="flex items-center gap-3">
                <Button onClick={onSave} disabled={saving}>
                    {saving ? <Loader2 className="size-4 animate-spin" /> : null}
                    {saving ? "Saving…" : "Save preferences"}
                </Button>
                {saved ? <span className="text-xs text-profit">Saved.</span> : null}
                <span className="ml-auto text-[11px] text-muted-foreground">
                    Risk limits are capped to your plan.
                </span>
            </div>
        </Card>
    );
}
