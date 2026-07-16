"use client";

import { useEffect, useState } from "react";
import { Cpu, Loader2, Pause, Play } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { getEngine, setEngine, type EngineStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

const DURATIONS: { label: string; seconds: number | null }[] = [
    { label: "1 hour", seconds: 3600 },
    { label: "4 hours", seconds: 4 * 3600 },
    { label: "24 hours", seconds: 24 * 3600 },
    { label: "Until I turn it off", seconds: null },
];

function humanizeRemaining(s: number | null): string | null {
    if (s == null) return null;
    if (s < 60) return `${s}s left`;
    if (s < 3600) return `${Math.round(s / 60)}m left`;
    return `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m left`;
}

/**
 * Owner-only AI-engine switch. The trading agents burn LLM calls every cycle, so the
 * engine is OFF by default and the owner turns it on for a bounded window. Hidden for
 * non-admins (they still see engine status elsewhere, just not the control).
 */
export function EngineControl() {
    const [status, setStatus] = useState<EngineStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [duration, setDuration] = useState<number | null>(3600);
    const [error, setError] = useState<string | null>(null);

    async function refresh() {
        try {
            setStatus(await getEngine());
        } catch (e) {
            setError(e instanceof Error ? e.message : "Could not load engine status");
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        refresh();
        // Live countdown / auto-off reflection.
        const t = setInterval(refresh, 30_000);
        return () => clearInterval(t);
    }, []);

    async function toggle(on: boolean) {
        setBusy(true);
        setError(null);
        try {
            setStatus(await setEngine(on, on ? duration : null));
        } catch (e) {
            setError(e instanceof Error ? e.message : "Could not update the engine");
        } finally {
            setBusy(false);
        }
    }

    // Non-admins don't get the control at all.
    if (!loading && status && status.is_admin === false) return null;

    const enabled = status?.enabled ?? false;
    const remaining = humanizeRemaining(status?.expires_in_seconds ?? null);

    return (
        <Card className="mb-8 gap-4 p-5">
            <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                    <Cpu className="size-4 text-accent" />
                    <h2 className="text-sm font-semibold text-foreground">AI Engine</h2>
                </div>
                <span
                    className={cn(
                        "flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium",
                        enabled
                            ? "border-profit/30 bg-profit/10 text-profit"
                            : "border-border bg-elevated text-subtle-foreground",
                    )}
                >
                    <span className={cn("size-1.5 rounded-full", enabled ? "bg-profit animate-pulse" : "bg-subtle-foreground")} />
                    {loading ? "…" : enabled ? "Running" : "Paused"}
                    {enabled && remaining ? <span className="text-subtle-foreground">· {remaining}</span> : null}
                </span>
            </div>

            <p className="text-xs leading-relaxed text-muted-foreground">
                The agents analyze the markets and publish trade setups only while the engine is
                running — each cycle uses AI credits, so start it when you want fresh signals and
                it will stop itself after the window you pick.
            </p>

            {!enabled && (
                <div className="flex flex-wrap gap-2">
                    {DURATIONS.map((d) => (
                        <button
                            key={d.label}
                            onClick={() => setDuration(d.seconds)}
                            aria-pressed={duration === d.seconds}
                            className={cn(
                                "rounded-md border px-3 py-1.5 text-xs font-medium transition-colors",
                                duration === d.seconds
                                    ? "border-accent/40 bg-accent-muted/40 text-foreground"
                                    : "border-border bg-elevated/30 text-muted-foreground hover:text-foreground",
                            )}
                        >
                            {d.label}
                        </button>
                    ))}
                </div>
            )}

            <div className="flex items-center gap-3">
                {enabled ? (
                    <Button size="sm" variant="outline" onClick={() => toggle(false)} disabled={busy}>
                        {busy ? <Loader2 className="size-4 animate-spin" /> : <Pause className="size-4" />}
                        Stop engine
                    </Button>
                ) : (
                    <Button size="sm" onClick={() => toggle(true)} disabled={busy}>
                        {busy ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
                        Start engine
                    </Button>
                )}
            </div>
            {error && <p className="text-sm text-loss">{error}</p>}
        </Card>
    );
}
