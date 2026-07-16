"use client";

import { useState } from "react";
import { Beaker, Bot, Hand, Loader2, Power } from "lucide-react";
import { saveSettings, type TradingMode } from "@/lib/api";
import { cn } from "@/lib/utils";

const MODES: { id: TradingMode; label: string; icon: typeof Bot; hint: string }[] = [
    { id: "paper", label: "Paper", icon: Beaker, hint: "AI auto-trades a practice portfolio with virtual money. No exchange needed, zero risk." },
    { id: "manual", label: "Manual", icon: Hand, hint: "AI suggests setups; you place each trade yourself with one click." },
    { id: "auto", label: "Auto", icon: Bot, hint: "AI places orders on your connected exchange automatically (testnet-gated)." },
    { id: "off", label: "Off", icon: Power, hint: "Watch only — no suggestions are acted on." },
];

/** Trading-mode picker — saves to /api/settings on selection. Used by onboarding + Settings. */
export function TradingModeSelector({
    value,
    onChange,
    columns = 4,
}: {
    value: TradingMode;
    onChange: (mode: TradingMode) => void;
    columns?: 2 | 4;
}) {
    const [saving, setSaving] = useState<TradingMode | null>(null);
    const [error, setError] = useState<string | null>(null);

    async function pick(mode: TradingMode) {
        setSaving(mode);
        setError(null);
        try {
            const saved = await saveSettings({ trading_mode: mode });
            onChange(saved.trading_mode);
        } catch (e) {
            setError(e instanceof Error ? e.message : "Could not save your choice");
        } finally {
            setSaving(null);
        }
    }

    return (
        <div>
            <div className={cn("grid gap-3", columns === 4 ? "grid-cols-2 sm:grid-cols-4" : "grid-cols-1 sm:grid-cols-2")}>
                {MODES.map((m) => {
                    const Icon = m.icon;
                    const active = value === m.id;
                    const busy = saving === m.id;
                    return (
                        <button
                            key={m.id}
                            onClick={() => pick(m.id)}
                            disabled={saving !== null}
                            aria-pressed={active}
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
            {error && <p className="mt-2 text-sm text-loss">{error}</p>}
        </div>
    );
}
