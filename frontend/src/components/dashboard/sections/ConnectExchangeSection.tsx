"use client";

import { useCallback, useEffect, useState } from "react";
import {
    Plug,
    ShieldCheck,
    KeyRound,
    Loader2,
    CheckCircle2,
    AlertTriangle,
    Trash2,
    ExternalLink,
    Lock,
} from "lucide-react";
import { SectionHeader } from "../ui/SectionHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadingState } from "@/components/ui/states";
import {
    getExchangeKeys,
    saveExchangeKeys,
    deleteExchangeKeys,
    saveSettings,
    type ExchangeKeyStatus,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const EXCHANGES: { id: string; label: string; hint: string; keysUrl: string }[] = [
    { id: "bingx", label: "BingX", hint: "VST demo (testnet) — Futures/Perpetual keys", keysUrl: "https://bingx.com/en/account/api/" },
    { id: "delta_india", label: "Delta Exchange India", hint: "Demo (testnet) — F&O trading keys", keysUrl: "https://www.delta.exchange/app/account/manageapikeys" },
];

/**
 * Connect-exchange onboarding. A signed-in user pastes their own BingX VST *testnet*
 * API key + secret; the backend encrypts them into the per-user vault, which makes the
 * user an active tenant the trading daemon books setups for. Secrets are write-only:
 * once stored, the API only ever returns a masked hint (never the raw secret), so this
 * screen never displays or persists the plaintext.
 */
export function ConnectExchangeSection() {
    const [status, setStatus] = useState<ExchangeKeyStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState<string | null>(null);

    const [exchange, setExchange] = useState("bingx");
    const [apiKey, setApiKey] = useState("");
    const [apiSecret, setApiSecret] = useState("");
    const [label, setLabel] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [formError, setFormError] = useState<string | null>(null);
    const [justConnected, setJustConnected] = useState(false);
    const [disconnecting, setDisconnecting] = useState(false);

    const refresh = useCallback(async () => {
        setLoading(true);
        setLoadError(null);
        try {
            setStatus(await getExchangeKeys());
        } catch (e) {
            setLoadError(e instanceof Error ? e.message : "Could not load connection status");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        void refresh();
    }, [refresh]);

    const connected = !!status?.connected;

    async function handleConnect(e: React.FormEvent) {
        e.preventDefault();
        setFormError(null);
        if (!apiKey.trim() || !apiSecret.trim()) {
            setFormError("Both API key and secret are required.");
            return;
        }
        setSubmitting(true);
        try {
            const next = await saveExchangeKeys({
                api_key: apiKey.trim(),
                api_secret: apiSecret.trim(),
                label: label.trim() || null,
                exchange,
                is_testnet: true,
            });
            setStatus(next);
            // Point the daemon/manual-execute at the exchange the user just connected.
            try { await saveSettings({ active_exchange: exchange }); } catch { /* non-fatal */ }
            setApiKey("");
            setApiSecret("");
            setLabel("");
            setJustConnected(true);
        } catch (e) {
            setFormError(e instanceof Error ? e.message : "Could not store credentials");
        } finally {
            setSubmitting(false);
        }
    }

    async function handleDisconnect() {
        setDisconnecting(true);
        setFormError(null);
        try {
            const next = await deleteExchangeKeys(status?.exchange || "bingx");
            setStatus(next);
            setJustConnected(false);
        } catch (e) {
            setFormError(e instanceof Error ? e.message : "Could not disconnect");
        } finally {
            setDisconnecting(false);
        }
    }

    return (
        <div>
            <SectionHeader
                title="Connect Exchange"
                description="Link your BingX testnet account to let the AI agents trade your own portfolio. Analysis is shared; execution and balances stay entirely yours."
                icon={Plug}
            />

            {/* Testnet-only safety banner — this is a hard backend gate, surfaced up front. */}
            <div className="mb-6 flex items-start gap-3 rounded-lg border border-accent/25 bg-accent-muted/40 px-4 py-3">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-accent" />
                <div className="text-sm text-muted-foreground">
                    <span className="font-medium text-foreground">Testnet only.</span> While live
                    trading is being validated, only <span className="font-medium">BingX VST (testnet)</span>{" "}
                    keys are accepted — no real funds are ever at risk. Mainnet keys are rejected.
                </div>
            </div>

            {loading ? (
                <Card className="py-10">
                    <LoadingState title="Checking connection…" />
                </Card>
            ) : loadError ? (
                <Card className="border-loss/30 py-8">
                    <div className="flex flex-col items-center gap-3 text-center">
                        <AlertTriangle className="size-6 text-loss" />
                        <p className="text-sm text-muted-foreground">{loadError}</p>
                        <Button variant="outline" size="sm" onClick={() => void refresh()}>
                            Try again
                        </Button>
                    </div>
                </Card>
            ) : connected ? (
                <ConnectedCard
                    status={status!}
                    justConnected={justConnected}
                    disconnecting={disconnecting}
                    onDisconnect={handleDisconnect}
                    error={formError}
                />
            ) : (
                <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
                    <ConnectForm
                        exchange={exchange}
                        apiKey={apiKey}
                        apiSecret={apiSecret}
                        label={label}
                        submitting={submitting}
                        error={formError}
                        onExchange={setExchange}
                        onApiKey={setApiKey}
                        onApiSecret={setApiSecret}
                        onLabel={setLabel}
                        onSubmit={handleConnect}
                    />
                    <HelpCard exchange={exchange} />
                </div>
            )}
        </div>
    );
}

function ConnectedCard({
    status,
    justConnected,
    disconnecting,
    onDisconnect,
    error,
}: {
    status: ExchangeKeyStatus;
    justConnected: boolean;
    disconnecting: boolean;
    onDisconnect: () => void;
    error: string | null;
}) {
    return (
        <Card className="gap-0 overflow-hidden p-0">
            <div className="flex items-center gap-3 border-b border-border bg-profit/5 px-5 py-4">
                <div className="flex size-10 items-center justify-center rounded-lg border border-profit/25 bg-profit/10 text-profit">
                    <CheckCircle2 className="size-5" />
                </div>
                <div>
                    <p className="text-sm font-semibold text-foreground">
                        {justConnected ? "Exchange connected" : "Exchange linked"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                        The agents will trade this account on the next analysis cycle.
                    </p>
                </div>
            </div>

            <div className="grid grid-cols-2 gap-px bg-border sm:grid-cols-3">
                <Detail label="Exchange" value={(status.exchange || "bingx").toUpperCase()} />
                <Detail
                    label="Environment"
                    value={status.is_testnet !== false ? "Testnet (VST)" : "Live"}
                    accent={status.is_testnet !== false ? "text-accent" : "text-loss"}
                />
                <Detail label="API key" value={status.api_key_masked || "••••••"} mono />
                {status.label ? <Detail label="Label" value={status.label} /> : null}
            </div>

            <div className="flex flex-col gap-3 px-5 py-4">
                {error && <InlineError message={error} />}
                <div className="flex items-center justify-between gap-4">
                    <p className="text-xs text-subtle-foreground">
                        Disconnecting removes your stored keys and pauses trading for your account.
                        Open positions are unaffected.
                    </p>
                    <Button
                        variant="destructive"
                        size="sm"
                        onClick={onDisconnect}
                        disabled={disconnecting}
                    >
                        {disconnecting ? (
                            <Loader2 className="size-4 animate-spin" />
                        ) : (
                            <Trash2 className="size-4" />
                        )}
                        {disconnecting ? "Disconnecting…" : "Disconnect"}
                    </Button>
                </div>
            </div>
        </Card>
    );
}

function ConnectForm({
    exchange,
    apiKey,
    apiSecret,
    label,
    submitting,
    error,
    onExchange,
    onApiKey,
    onApiSecret,
    onLabel,
    onSubmit,
}: {
    exchange: string;
    apiKey: string;
    apiSecret: string;
    label: string;
    submitting: boolean;
    error: string | null;
    onExchange: (v: string) => void;
    onApiKey: (v: string) => void;
    onApiSecret: (v: string) => void;
    onLabel: (v: string) => void;
    onSubmit: (e: React.FormEvent) => void;
}) {
    const selected = EXCHANGES.find((x) => x.id === exchange) ?? EXCHANGES[0];
    return (
        <Card className="p-5">
            <form onSubmit={onSubmit} className="flex flex-col gap-5">
                <div className="flex items-center gap-2">
                    <KeyRound className="size-4 text-accent" />
                    <h2 className="text-sm font-semibold text-foreground">Exchange API keys</h2>
                </div>

                <Field label="Exchange" htmlFor="exchange">
                    <div className="grid grid-cols-2 gap-2">
                        {EXCHANGES.map((x) => (
                            <button
                                key={x.id}
                                type="button"
                                onClick={() => onExchange(x.id)}
                                className={cn(
                                    "rounded-md border px-3 py-2 text-left text-sm transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
                                    exchange === x.id
                                        ? "border-accent/40 bg-accent-muted/40 text-foreground"
                                        : "border-border bg-elevated/30 text-muted-foreground hover:text-foreground",
                                )}
                            >
                                <span className="block font-medium">{x.label}</span>
                                <span className="block text-[11px] text-subtle-foreground">{x.hint}</span>
                            </button>
                        ))}
                    </div>
                </Field>

                <Field label="API key" htmlFor="api-key">
                    <Input
                        id="api-key"
                        value={apiKey}
                        onChange={(e) => onApiKey(e.target.value)}
                        placeholder={`Paste your ${selected.label} API key`}
                        autoComplete="off"
                        spellCheck={false}
                        className="font-mono"
                    />
                </Field>

                <Field label="API secret" htmlFor="api-secret">
                    <Input
                        id="api-secret"
                        type="password"
                        value={apiSecret}
                        onChange={(e) => onApiSecret(e.target.value)}
                        placeholder={`Paste your ${selected.label} API secret`}
                        autoComplete="off"
                        spellCheck={false}
                        className="font-mono"
                    />
                </Field>

                <Field label="Label" htmlFor="label" hint="optional">
                    <Input
                        id="label"
                        value={label}
                        onChange={(e) => onLabel(e.target.value)}
                        placeholder="e.g. My testnet account"
                        maxLength={40}
                    />
                </Field>

                {error && <InlineError message={error} />}

                <div className="flex items-center gap-3 pt-1">
                    <Button type="submit" disabled={submitting} className="min-w-36">
                        {submitting ? (
                            <>
                                <Loader2 className="size-4 animate-spin" /> Connecting…
                            </>
                        ) : (
                            <>
                                <Plug className="size-4" /> Connect exchange
                            </>
                        )}
                    </Button>
                    <span className="flex items-center gap-1.5 text-xs text-subtle-foreground">
                        <Lock className="size-3" /> Encrypted at rest — never shown again
                    </span>
                </div>
            </form>
        </Card>
    );
}

function HelpCard({ exchange }: { exchange: string }) {
    const ex = EXCHANGES.find((x) => x.id === exchange) ?? EXCHANGES[0];
    return (
        <Card className="gap-4 p-5">
            <div className="flex items-center gap-2">
                <ExternalLink className="size-4 text-accent" />
                <h2 className="text-sm font-semibold text-foreground">How to get {ex.label} testnet keys</h2>
            </div>
            <ol className="flex flex-col gap-3 text-sm text-muted-foreground">
                {[
                    <>
                        Open{" "}
                        <a
                            href={ex.keysUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-accent underline-offset-4 hover:underline"
                        >
                            {ex.label} API management
                        </a>{" "}
                        and switch to the <span className="font-medium text-foreground">demo / testnet</span> environment.
                    </>,
                    <>Create an API key with <span className="font-medium text-foreground">Futures / Perpetual</span> read + trade permissions.</>,
                    <>Leave IP restrictions off (or allowlist the server) so the agents can place orders.</>,
                    <>Paste the key and secret here. That&apos;s it — you&apos;re a live tenant on the next cycle.</>,
                ].map((step, i) => (
                    <li key={i} className="flex gap-3">
                        <span className="flex size-5 shrink-0 items-center justify-center rounded-full border border-border bg-elevated text-[11px] font-semibold text-accent">
                            {i + 1}
                        </span>
                        <span>{step}</span>
                    </li>
                ))}
            </ol>
        </Card>
    );
}

function Field({
    label,
    htmlFor,
    hint,
    children,
}: {
    label: string;
    htmlFor: string;
    hint?: string;
    children: React.ReactNode;
}) {
    return (
        <div className="flex flex-col gap-2">
            <Label htmlFor={htmlFor} className="justify-between">
                <span>{label}</span>
                {hint && <span className="text-xs font-normal text-subtle-foreground">{hint}</span>}
            </Label>
            {children}
        </div>
    );
}

function Detail({
    label,
    value,
    mono,
    accent,
}: {
    label: string;
    value: string;
    mono?: boolean;
    accent?: string;
}) {
    return (
        <div className="bg-card px-5 py-4">
            <p className="mb-1 text-[11px] font-medium uppercase tracking-wider text-subtle-foreground">
                {label}
            </p>
            <p className={cn("text-sm font-medium text-foreground", mono && "font-mono", accent)}>
                {value}
            </p>
        </div>
    );
}

function InlineError({ message }: { message: string }) {
    return (
        <div className="flex items-start gap-2 rounded-md border border-loss/25 bg-loss/10 px-3 py-2 text-sm text-loss">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>{message}</span>
        </div>
    );
}
