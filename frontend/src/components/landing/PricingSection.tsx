"use client";

import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { CountUp } from "./CountUp";
import { cn } from "@/lib/utils";

/*
 * PricingSection — "The Risk Envelope Ledger". Not three cards: one ruled
 * ledger where the three tiers are COLUMNS you read across, and buying up means
 * widening the same risk envelope one detent at a time. Every number is a real
 * backend limit (src/billing/plans.py). Paid tiers aren't purchasable yet
 * (Stripe unwired, live trading testnet-gated) — handled honestly, not faked.
 *
 * Design direction from the marketing-bands design workflow (winner: Risk
 * Envelope Ledger), built against CryptAI's real crimson tokens.
 */

type Fmt = "usd" | "pct" | "int";

const ROWS: { label: string; fmt: Fmt; values: [number, number, number] }[] = [
    { label: "Paper balance", fmt: "usd", values: [10000, 25000, 100000] },
    { label: "Max risk / trade", fmt: "pct", values: [1, 2, 3] },
    { label: "Concurrent positions", fmt: "int", values: [1, 3, 8] },
    { label: "Trades / day", fmt: "int", values: [3, 5, 20] },
    { label: "Max position size", fmt: "usd", values: [2000, 10000, 100000] },
];

const TIERS = [
    { name: "Free", price: 0, desc: "Paper", live: false },
    { name: "Starter", price: 19, desc: "Live · retail", live: true },
    { name: "Pro", price: 79, desc: "Live · desk", live: true },
] as const;

const fmtProps = (fmt: Fmt) =>
    fmt === "usd" ? { prefix: "$" } : fmt === "pct" ? { suffix: "%" } : {};

// Perceptual (sqrt) fill width so $10k reads as a real segment beside $100k.
const fillPct = (v: number, max: number) => `${Math.sqrt(v / max) * 100}%`;

const ease = [0.16, 1, 0.3, 1] as const;

/** A single numeric ledger cell — count-up from the Free baseline + fill bar. */
function ValueCell({ row, col, delayMs }: { row: (typeof ROWS)[number]; col: number; delayMs: number }) {
    const value = row.values[col];
    const max = row.values[2];
    return (
        <div className="relative flex items-end justify-center px-3 pb-3 pt-2.5">
            <span className="num text-sm font-medium tabular-nums text-foreground md:text-[15px]">
                <CountUp to={value} from={row.values[0]} decimals={0} delayMs={delayMs} {...fmtProps(row.fmt)} />
            </span>
            {/* Muted baseline bar — decorative reinforcement; the number is truth. */}
            <span aria-hidden className="absolute inset-x-3 bottom-0 h-0.5 overflow-hidden rounded-sm bg-white/[0.04]">
                <motion.span
                    className="block h-full rounded-sm bg-white/15"
                    initial={{ width: 0 }}
                    whileInView={{ width: fillPct(value, max) }}
                    viewport={{ once: true, margin: "-60px" }}
                    transition={{ duration: 0.7, delay: delayMs / 1000 + 0.2, ease }}
                />
            </span>
        </div>
    );
}

function GateCell({ live }: { live: boolean }) {
    if (!live) {
        return (
            <div className="flex items-center justify-center gap-2 px-3 py-3">
                <span className="size-1.5 rounded-full bg-subtle-foreground" />
                <span className="num text-xs text-muted-foreground">Paper only</span>
            </div>
        );
    }
    return (
        <div className="flex items-center justify-center gap-2 px-3 py-3">
            {/* Sealed-shutter seam — the one crimson mark in the ledger body. */}
            <span aria-hidden className="h-3 w-0.5 rounded-full bg-accent" />
            <span className="num text-xs text-foreground">Live · sealed</span>
            <span className="num rounded border border-border px-1 py-0.5 text-[9px] uppercase tracking-wider text-subtle-foreground">
                testnet-gated
            </span>
        </div>
    );
}

function TierCTA({ tier }: { tier: (typeof TIERS)[number] }) {
    if (!tier.live) {
        return (
            <div className="flex flex-col items-center gap-1.5 px-3 py-4">
                <Button asChild size="sm" className="w-full max-w-[180px]">
                    <Link href="/auth/signup">
                        Start free <ArrowRight className="size-3.5" />
                    </Link>
                </Button>
                <span className="num text-[11px] text-subtle-foreground">$0 · no card</span>
            </div>
        );
    }
    return (
        <div className="flex flex-col items-center gap-1.5 px-3 py-4">
            <Link
                href="/contact"
                className="w-full max-w-[180px] rounded-md border border-border px-3 py-1.5 text-center text-sm font-medium text-accent-300 transition-colors duration-150 hover:border-border-strong hover:bg-elevated/60"
            >
                Notify me
            </Link>
            <span className="num text-[11px] text-subtle-foreground">when live opens</span>
        </div>
    );
}

export function PricingSection() {
    return (
        <section id="pricing" className="relative py-24 md:py-32">
            <div className="container relative z-10 mx-auto max-w-6xl px-4 md:px-6">
                <div className="grid gap-10 lg:grid-cols-[220px_1fr] lg:gap-14">
                    {/* Left rail — framing (replaces the banned eyebrow) */}
                    <motion.div
                        initial={{ opacity: 0, y: 12 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: "-80px" }}
                        transition={{ duration: 0.5, ease }}
                        className="lg:sticky lg:top-24 lg:self-start"
                    >
                        <div className="num text-[11px] uppercase tracking-[0.14em] text-subtle-foreground">
                            Same engine
                            <br />
                            Different envelope
                        </div>
                        <p className="mt-4 text-xl leading-snug text-foreground">
                            You&apos;re not buying features. You&apos;re widening the{" "}
                            <em className="font-serif italic text-accent-300">envelope.</em>
                        </p>
                        <p className="num mt-5 max-w-[16rem] text-xs leading-relaxed text-subtle-foreground">
                            Higher tiers don&apos;t relax the rules — they raise the ceiling. Every
                            limit is enforced server-side, not suggested.
                        </p>
                    </motion.div>

                    {/* The ledger — desktop */}
                    <motion.div
                        initial={{ opacity: 0, y: 14 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: "-80px" }}
                        transition={{ duration: 0.55, ease }}
                        className="hidden lg:block"
                    >
                        <div className="grid grid-cols-[minmax(150px,1.1fr)_1fr_1fr_1fr]">
                            {/* Header row */}
                            <div className="border-b border-border" />
                            {TIERS.map((t, c) => (
                                <div
                                    key={t.name}
                                    className={cn(
                                        "relative border-b border-l border-border px-3 pb-3 pt-4 text-center",
                                        c === 1 && "bg-elevated/30",
                                        c === 2 && "border-x border-border-strong bg-elevated/40",
                                    )}
                                >
                                    {c === 2 && (
                                        <span aria-hidden className="absolute inset-x-0 top-0 mx-auto h-0.5 w-full bg-accent" />
                                    )}
                                    <div className="num text-[11px] uppercase tracking-wider text-muted-foreground">
                                        {t.name}
                                    </div>
                                    <div className="num mt-1 text-2xl font-semibold text-foreground">
                                        ${t.price}
                                        <span className="text-sm font-normal text-subtle-foreground">/mo</span>
                                    </div>
                                    <div className="num mt-0.5 text-[11px] text-subtle-foreground">{t.desc}</div>
                                </div>
                            ))}

                            {/* Constraint rows */}
                            {ROWS.map((row, r) => (
                                <div key={row.label} className="contents">
                                    <div className="flex items-center border-b border-border py-2.5 pr-3 text-sm text-muted-foreground">
                                        {row.label}
                                    </div>
                                    {TIERS.map((t, c) => (
                                        <div
                                            key={t.name}
                                            className={cn(
                                                "border-b border-l border-border",
                                                c === 1 && "bg-elevated/30",
                                                c === 2 && "border-x border-border-strong bg-elevated/40",
                                            )}
                                        >
                                            <ValueCell row={row} col={c} delayMs={r * 70} />
                                        </div>
                                    ))}
                                </div>
                            ))}

                            {/* Gate row */}
                            <div className="flex items-center border-b border-border py-2.5 pr-3 text-sm text-muted-foreground">
                                Execution
                            </div>
                            {TIERS.map((t, c) => (
                                <div
                                    key={t.name}
                                    className={cn(
                                        "border-b border-l border-border",
                                        c === 1 && "bg-elevated/30",
                                        c === 2 && "border-x border-border-strong bg-elevated/40",
                                    )}
                                >
                                    <GateCell live={t.live} />
                                </div>
                            ))}

                            {/* CTA row */}
                            <div />
                            {TIERS.map((t, c) => (
                                <div
                                    key={t.name}
                                    className={cn(
                                        "border-l border-border",
                                        c === 1 && "bg-elevated/30",
                                        c === 2 && "border-x border-b border-border-strong bg-elevated/40",
                                    )}
                                >
                                    <TierCTA tier={t} />
                                </div>
                            ))}
                        </div>

                        <p className="num mt-5 text-center text-[11px] uppercase tracking-wider text-subtle-foreground">
                            Live execution is hard-gated to testnet today · paid tiers open when it&apos;s real
                        </p>
                    </motion.div>

                    {/* The ledger — mobile/tablet: stacked mini-ledgers per tier */}
                    <div className="space-y-6 lg:hidden">
                        {TIERS.map((t, c) => (
                            <div
                                key={t.name}
                                className={cn(
                                    "overflow-hidden rounded-lg border",
                                    c === 2 ? "border-border-strong" : "border-border",
                                )}
                            >
                                <div className={cn("flex items-baseline justify-between px-4 py-3", c === 2 ? "bg-elevated/40" : "bg-surface")}>
                                    <div>
                                        <span className="num text-[11px] uppercase tracking-wider text-muted-foreground">{t.name}</span>
                                        <div className="num text-xl font-semibold text-foreground">
                                            ${t.price}<span className="text-sm font-normal text-subtle-foreground">/mo</span>
                                        </div>
                                    </div>
                                    <span className="num text-[11px] text-subtle-foreground">{t.desc}</span>
                                </div>
                                {ROWS.map((row) => (
                                    <div key={row.label} className="flex items-center justify-between border-t border-border px-4 py-2.5">
                                        <span className="text-sm text-muted-foreground">{row.label}</span>
                                        <span className="num text-sm font-medium text-foreground">
                                            {row.fmt === "usd" && "$"}
                                            {row.values[c].toLocaleString("en-US")}
                                            {row.fmt === "pct" && "%"}
                                        </span>
                                    </div>
                                ))}
                                <div className="flex items-center justify-between border-t border-border px-4 py-2.5">
                                    <span className="text-sm text-muted-foreground">Execution</span>
                                    <span className="num text-xs text-foreground">{t.live ? "Live · sealed" : "Paper only"}</span>
                                </div>
                                <div className="border-t border-border px-4 py-3">
                                    <TierCTA tier={t} />
                                </div>
                            </div>
                        ))}
                        <p className="num text-center text-[11px] uppercase tracking-wider text-subtle-foreground">
                            Live execution is testnet-gated today · paid tiers open when it&apos;s real
                        </p>
                    </div>
                </div>
            </div>
        </section>
    );
}
