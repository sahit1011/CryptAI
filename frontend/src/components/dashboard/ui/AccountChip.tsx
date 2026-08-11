"use client";

import { useEffect, useState } from "react";

import { Value } from "@/components/ui/value";
import { cn } from "@/lib/utils";
import { getSettings, type TradingMode } from "@/lib/api";
import { useStore } from "@/store/useStore";

/*
 * AccountChip — which account is this, always visible, never behind a menu.
 *
 * A user who cannot tell practice money from exchange money at a glance is one
 * misread away from believing a paper P&L is real, or from hesitating over a real
 * order because they assumed it was practice. That belongs in the chrome, not in a
 * dropdown you have to go looking for (docs/UX_SPEC.md §7.4).
 *
 * Amber for both live-capable states, because "test mode" is still a real exchange
 * accepting real orders. Crimson is reserved for genuine live trading, which is
 * gated off at the platform level and therefore cannot render here yet — that
 * absence is deliberate, so the day it appears it will not look like more of the same.
 */

const LABELS: Record<TradingMode, { text: string; hint: string } | null> = {
    paper: { text: "PRACTICE", hint: "Virtual money, real prices. Nothing here is real." },
    manual: { text: "PRACTICE", hint: "Virtual money, real prices. You place each trade yourself." },
    auto: {
        text: "DELTA TEST",
        hint: "Real exchange, fake money. Orders route through the exchange's test system.",
    },
    off: null, // nothing is trading; a balance chip would imply otherwise
};

export function AccountChip() {
    const [mode, setMode] = useState<TradingMode | null>(null);
    const { portfolio } = useStore();

    useEffect(() => {
        let cancelled = false;
        getSettings()
            .then((s) => !cancelled && setMode(s.trading_mode))
            .catch(() => { /* unknown account state — render nothing rather than guess */ });
        return () => {
            cancelled = true;
        };
    }, []);

    if (!mode) return null;
    const label = LABELS[mode];
    if (!label) return null;

    // Only show a number we actually have. A chip reading ₹0 next to "PRACTICE" reads as
    // a broke account rather than an unloaded one.
    const balance = portfolio.totalValue || portfolio.balance || 0;

    return (
        <span
            title={label.hint}
            className={cn(
                "hidden items-center gap-2 rounded-md border px-2.5 py-1 text-[11px] font-medium sm:inline-flex",
                mode === "auto"
                    ? "border-amber-500/50 bg-amber-500/10 text-amber-400"
                    : "border-dashed border-amber-500/40 bg-amber-500/5 text-amber-400/90",
            )}
        >
            {label.text}
            {balance > 0 ? (
                <>
                    <span className="text-amber-400/40">·</span>
                    <Value value={balance} money decimals={0} className="text-amber-400" />
                </>
            ) : null}
        </span>
    );
}
