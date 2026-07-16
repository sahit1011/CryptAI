"use client";

import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { BackgroundGrid } from "./BackgroundGrid";

/*
 * Hero — asymmetric two-column: a specific, left-aligned claim on the left and a
 * flat "agent pipeline" terminal panel on the right. No rotating headlines, no
 * gradient/shine text, no 3D tilt, no fake browser chrome — the product's real
 * architecture IS the visual. One crimson moment per column.
 */

// Illustrative pipeline feed — mirrors the real agents' log output, clearly a mockup.
const pipelineRows = [
    { agent: "data", msg: "BTCUSDT 500 candles · 5 timeframes synced", state: "done" },
    { agent: "analysis", msg: "HTF bias bullish · sweep of 43,050 lows", state: "done" },
    { agent: "memory", msg: "regime: trending · 3 similar episodes recalled", state: "done" },
    { agent: "strategy", msg: "long setup drafted · R:R 2.4", state: "done" },
    { agent: "risk", msg: "sizing 1.8% · bracket approved", state: "live" },
] as const;

const container = {
    hidden: {},
    visible: { transition: { staggerChildren: 0.07, delayChildren: 0.05 } },
};
const item = {
    hidden: { opacity: 0, y: 10 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.45, ease: [0.16, 1, 0.3, 1] as const } },
};

export function HeroSection() {
    return (
        <section className="relative overflow-hidden pt-36 pb-24 md:pt-44 md:pb-32">
            <BackgroundGrid />

            <div className="container relative z-10 mx-auto grid max-w-6xl items-center gap-14 px-4 md:px-6 lg:grid-cols-[1.05fr_0.95fr] lg:gap-10">
                {/* ---- Claim ---------------------------------------------------- */}
                <motion.div variants={container} initial="hidden" animate="visible">
                    <motion.p variants={item} className="eyebrow mb-5 text-accent-300">
                        Multi-agent trading system
                    </motion.p>

                    <motion.h1 variants={item} className="display-1 mb-6 text-foreground">
                        Five AI agents.
                        <br />
                        One disciplined trader.
                    </motion.h1>

                    <motion.p
                        variants={item}
                        className="mb-9 max-w-xl text-base leading-relaxed text-muted-foreground md:text-lg"
                    >
                        CryptAI runs a pipeline of specialist agents — data, analysis, memory,
                        strategy, risk — over BTC, ETH and Gold around the clock. Every setup is
                        argued by the models, then approved by a deterministic risk gate before a
                        single order is placed.
                    </motion.p>

                    <motion.div variants={item} className="flex flex-wrap items-center gap-3">
                        <Link href="/auth/signup">
                            <Button size="lg" className="h-11 px-6 text-[15px]">
                                Start paper trading
                                <ArrowRight className="size-4" />
                            </Button>
                        </Link>
                        <Link href="#architecture">
                            <Button variant="ghost" size="lg" className="h-11 px-4 text-[15px]">
                                See the pipeline
                            </Button>
                        </Link>
                    </motion.div>

                    {/* Facts, not badge clichés — set in mono like an order ticket. */}
                    <motion.p variants={item} className="num mt-10 text-xs text-subtle-foreground">
                        BTC · ETH · XAUT&ensp;/&ensp;analysis every cycle&ensp;/&ensp;testnet-gated
                        execution&ensp;/&ensp;non-custodial keys
                    </motion.p>
                </motion.div>

                {/* ---- Pipeline panel ------------------------------------------- */}
                <motion.div
                    initial={{ opacity: 0, y: 14 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, delay: 0.25, ease: [0.16, 1, 0.3, 1] }}
                    className="relative"
                >
                    <div className="overflow-hidden rounded-xl border border-border bg-surface">
                        {/* Panel header */}
                        <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
                            <div className="flex items-center gap-2">
                                <span className="size-1.5 rounded-full bg-accent animate-pulse-subtle" />
                                <span className="num text-xs text-muted-foreground">
                                    cryptai · agent pipeline
                                </span>
                            </div>
                            <span className="num text-[10px] uppercase tracking-wider text-subtle-foreground">
                                Illustrative
                            </span>
                        </div>

                        {/* Agent feed */}
                        <div className="divide-y divide-border">
                            {pipelineRows.map((row, i) => (
                                <motion.div
                                    key={row.agent}
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    transition={{ delay: 0.5 + i * 0.12, duration: 0.35 }}
                                    className="flex items-baseline gap-3 px-4 py-2.5"
                                >
                                    <span className="num w-16 shrink-0 text-xs text-accent-300">
                                        {row.agent}
                                    </span>
                                    <span className="min-w-0 flex-1 truncate text-[13px] text-muted-foreground">
                                        {row.msg}
                                    </span>
                                    <span
                                        className={
                                            row.state === "live"
                                                ? "num shrink-0 text-[10px] uppercase tracking-wider text-profit"
                                                : "num shrink-0 text-[10px] uppercase tracking-wider text-subtle-foreground"
                                        }
                                    >
                                        {row.state === "live" ? "executing" : "ok"}
                                    </span>
                                </motion.div>
                            ))}
                        </div>

                        {/* Resulting setup — the pipeline's output, tabular numbers. */}
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: 1.25, duration: 0.4 }}
                            className="border-t border-border bg-elevated/40 px-4 py-3.5"
                        >
                            <div className="mb-2.5 flex items-center justify-between">
                                <div className="flex items-center gap-2.5">
                                    <span className="text-sm font-semibold text-foreground">BTCUSDT</span>
                                    <span className="rounded-sm border border-profit/30 bg-profit/10 px-1.5 py-px text-[10px] font-medium uppercase tracking-wider text-profit">
                                        Long
                                    </span>
                                </div>
                                <span className="num text-xs text-muted-foreground">conf 74%</span>
                            </div>
                            <div className="grid grid-cols-3 gap-px overflow-hidden rounded-md border border-border bg-border text-center">
                                {[
                                    { k: "Entry", v: "43,284.5" },
                                    { k: "Stop", v: "42,950.0" },
                                    { k: "Target", v: "44,090.0" },
                                ].map((cell) => (
                                    <div key={cell.k} className="bg-surface px-2 py-2">
                                        <div className="text-[10px] uppercase tracking-wider text-subtle-foreground">
                                            {cell.k}
                                        </div>
                                        <div className="num mt-0.5 text-sm text-foreground">{cell.v}</div>
                                    </div>
                                ))}
                            </div>
                        </motion.div>
                    </div>

                    {/* Single quiet accent: a hairline crimson rule under the panel. */}
                    <div className="mx-auto mt-px h-px w-2/3 bg-gradient-to-r from-transparent via-accent/40 to-transparent" />
                </motion.div>
            </div>
        </section>
    );
}
