"use client";

import { useEffect, useState } from "react";
import { Plug, Settings2, Sparkles } from "lucide-react";
import { SectionHeader } from "../ui/SectionHeader";
import { Card } from "@/components/ui/card";
import { TradingModeSelector } from "../ui/TradingModeSelector";
import { TradingPersona } from "../ui/TradingPersona";
import { EngineControl } from "../ui/EngineControl";
import { ConnectExchangeSection } from "./ConnectExchangeSection";
import { getSettings, type TradingMode } from "@/lib/api";

/**
 * Settings — where preferences chosen during onboarding are managed afterwards:
 * trading mode (how AI signals are acted on) and the exchange connection.
 */
export function SettingsSection() {
    const [mode, setMode] = useState<TradingMode>("paper");

    useEffect(() => {
        getSettings()
            .then((s) => setMode(s.trading_mode))
            .catch(() => { /* keep default */ });
    }, []);

    return (
        <div>
            <SectionHeader
                title="Settings"
                description="Your trading preferences — how the AI acts on its signals, and which exchange account it trades."
                icon={Settings2}
            />

            {/* AI engine control (owner only; renders null for other users) */}
            <EngineControl />

            {/* Trading persona — the preferences the session pipeline synthesises against */}
            <TradingPersona />

            {/* Trading mode */}
            <Card className="mb-8 gap-4 p-5">
                <div className="flex items-center gap-2">
                    <Sparkles className="size-4 text-accent" />
                    <h2 className="text-sm font-semibold text-foreground">Trading mode</h2>
                </div>
                <TradingModeSelector value={mode} onChange={setMode} />
            </Card>

            {/* Exchange connection */}
            <div className="mb-3 flex items-center gap-2">
                <Plug className="size-4 text-accent" />
                <h2 className="text-sm font-semibold text-foreground">Exchange connection</h2>
            </div>
            <ConnectExchangeSection embedded />
        </div>
    );
}
