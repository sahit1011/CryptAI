"use client";

import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight } from "lucide-react";

/*
 * ArchitectureSection — the real product architecture as a single horizontal
 * pipeline strip: five stages separated by hairline dividers, in the same
 * terminal voice as the hero panel (mono agent names, quiet status words).
 * One bordered container, not five floating cards — the pipeline IS the visual.
 */

const stages = [
    {
        id: "data",
        title: "Data",
        body: "Streams live candles across five timeframes from exchange WebSockets.",
        out: "market state",
    },
    {
        id: "analysis",
        title: "Analysis",
        body: "Indicators, market structure and LLM reasoning argue a directional bias.",
        out: "bias + levels",
    },
    {
        id: "memory",
        title: "Memory",
        body: "Recalls similar regimes from vector memory so the desk learns from its history.",
        out: "regime context",
    },
    {
        id: "strategy",
        title: "Strategy",
        body: "Drafts a full trade plan — entry, stop, targets — with an explicit R:R.",
        out: "trade setup",
    },
    {
        id: "risk",
        title: "Risk gate",
        body: "Deterministic rules — sizing, portfolio heat, loss limits. Not a model; models can't talk past it.",
        out: "approved order",
    },
];

export function ArchitectureSection() {
    const reduced = useReducedMotion();
    return (
        <section id="architecture" className="relative overflow-hidden py-24 md:py-32">
            <div className="container relative z-10 mx-auto max-w-6xl px-4 md:px-6">
                <div className="mb-12 max-w-2xl">
                    <h2 className="display-3 text-balance">
                        Modeled on an{" "}
                        <em className="font-serif text-accent-300">institutional trading desk</em>
                    </h2>
                    <p className="body-md mt-4 text-pretty text-muted-foreground">
                        Five specialists pass work down a pipeline — every trade idea is
                        produced by one agent, challenged by the next, and finally cleared by
                        a rule-based risk gate before execution.
                    </p>
                </div>

                <motion.div
                    initial={{ opacity: 0, y: 12 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-80px" }}
                    transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                    className="overflow-hidden rounded-xl border border-border bg-surface"
                >
                    <div className="grid divide-y divide-border md:grid-cols-5 md:divide-x md:divide-y-0">
                        {stages.map((stage, i) => (
                            <div key={stage.id} className="relative flex flex-col p-6">
                                {/* Work traveling down the pipeline — a quiet pulse visits
                                    each stage in order, forever. */}
                                <motion.div
                                    aria-hidden
                                    className="pointer-events-none absolute inset-0 bg-accent/[0.06]"
                                    initial={{ opacity: 0 }}
                                    animate={reduced ? { opacity: 0 } : { opacity: [0, 1, 0] }}
                                    transition={{
                                        duration: 1.4,
                                        delay: i * 1.4,
                                        repeat: reduced ? 0 : Infinity,
                                        repeatDelay: (stages.length - 1) * 1.4,
                                        ease: "easeInOut",
                                    }}
                                />
                                <div className="mb-3 flex items-center justify-between">
                                    <span className="num text-xs text-accent-300">{stage.id}</span>
                                    {i < stages.length - 1 && (
                                        <ArrowRight className="size-3.5 text-subtle-foreground max-md:rotate-90" />
                                    )}
                                </div>
                                <h3 className="mb-1.5 text-[15px] font-semibold tracking-tight text-foreground">
                                    {stage.title}
                                </h3>
                                <p className="text-[13px] leading-relaxed text-muted-foreground">
                                    {stage.body}
                                </p>
                                <span className="num mt-4 text-[10px] uppercase tracking-wider text-subtle-foreground md:mt-auto md:pt-4">
                                    → {stage.out}
                                </span>
                            </div>
                        ))}
                    </div>
                </motion.div>
            </div>
        </section>
    );
}
