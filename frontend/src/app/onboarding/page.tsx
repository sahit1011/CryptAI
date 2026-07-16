"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Activity, ArrowRight, Check, Loader2 } from "lucide-react";
import { createClient } from "@/utils/supabase/client";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TradingModeSelector } from "@/components/dashboard/ui/TradingModeSelector";
import { ConnectExchangeSection } from "@/components/dashboard/sections/ConnectExchangeSection";
import { getSettings, saveSettings, type TradingMode } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * First-run onboarding: choose how the AI trades for you, optionally connect an
 * exchange, then enter the dashboard. Preferences are changeable later in Settings.
 */
export default function OnboardingPage() {
    const router = useRouter();
    const supabase = createClient();

    const [checking, setChecking] = useState(true);
    const [step, setStep] = useState<1 | 2>(1);
    const [mode, setMode] = useState<TradingMode>("paper");
    const [finishing, setFinishing] = useState(false);

    // Must be signed in; already-onboarded users go straight to the dashboard.
    useEffect(() => {
        (async () => {
            const { data: { session } } = await supabase.auth.getSession();
            if (!session) {
                router.replace("/auth/login");
                return;
            }
            try {
                const s = await getSettings();
                if (s.onboarded) {
                    router.replace("/dashboard");
                    return;
                }
                setMode(s.trading_mode);
            } catch { /* proceed with defaults */ }
            setChecking(false);
        })();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    async function finish() {
        setFinishing(true);
        try {
            await saveSettings({ onboarded: true });
        } catch { /* non-fatal — dashboard still works */ }
        router.replace("/dashboard");
    }

    if (checking) {
        return (
            <div className="flex min-h-screen items-center justify-center bg-background">
                <Loader2 className="size-6 animate-spin text-accent" />
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-background px-4 py-10 text-foreground">
            <div className="mx-auto max-w-3xl">
                {/* Brand + progress */}
                <div className="mb-8 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="flex size-8 items-center justify-center rounded-lg border border-border bg-accent-muted text-accent">
                            <Activity className="size-5" />
                        </div>
                        <span className="text-lg font-semibold tracking-tight">CryptAI</span>
                    </div>
                    <div className="flex items-center gap-2" aria-label={`Step ${step} of 2`}>
                        {[1, 2].map((s) => (
                            <span
                                key={s}
                                className={cn(
                                    "h-1.5 w-10 rounded-full transition-colors",
                                    s <= step ? "bg-accent" : "bg-elevated",
                                )}
                            />
                        ))}
                    </div>
                </div>

                {step === 1 ? (
                    <>
                        <h1 className="mb-2 text-2xl font-semibold">How should CryptAI trade for you?</h1>
                        <p className="mb-6 text-sm text-muted-foreground">
                            Our AI agents analyze BTC, ETH and Gold around the clock and publish trade
                            setups. Choose what happens with them — you can change this anytime in Settings.
                        </p>
                        <Card className="p-5">
                            <TradingModeSelector value={mode} onChange={setMode} columns={2} />
                        </Card>
                        <div className="mt-6 flex justify-end">
                            <Button onClick={() => setStep(2)} className="min-w-36">
                                Continue <ArrowRight className="size-4" />
                            </Button>
                        </div>
                    </>
                ) : (
                    <>
                        <h1 className="mb-2 text-2xl font-semibold">Connect your exchange</h1>
                        <p className="mb-6 text-sm text-muted-foreground">
                            {mode === "paper" || mode === "off"
                                ? "Optional for your current mode — paper trading uses a practice portfolio with virtual money. You can connect an exchange later in Settings."
                                : "Manual and Auto modes place real (testnet) orders, so an exchange connection is needed. You can also do this later in Settings."}
                        </p>
                        <ConnectExchangeSection embedded />
                        <div className="mt-6 flex items-center justify-between">
                            <Button variant="ghost" onClick={() => setStep(1)}>Back</Button>
                            <Button onClick={finish} disabled={finishing} className="min-w-44">
                                {finishing ? <Loader2 className="size-4 animate-spin" /> : <Check className="size-4" />}
                                {mode === "paper" || mode === "off" ? "Skip & enter dashboard" : "Enter dashboard"}
                            </Button>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
