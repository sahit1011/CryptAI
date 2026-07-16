"use client";

import { motion } from "framer-motion";

/*
 * FeaturesSection — "why CryptAI" as a numbered capability index (01–04) inside
 * one bordered grid with hairline dividers. No floating icon-chip cards (the
 * most recognizable template pattern); the numbering is real information — it
 * mirrors the order the pipeline works in.
 */

const features = [
    {
        n: "01",
        title: "Autonomous agents",
        body: "Specialist agents own data, analysis, memory and strategy — each argues its part of a trade, so setups survive scrutiny before they reach you.",
    },
    {
        n: "02",
        title: "A deterministic risk gate",
        body: "Every AI-drafted setup passes a rule-based gate — position sizing, portfolio heat, daily loss limits — that no model can talk its way around.",
    },
    {
        n: "03",
        title: "Real-time execution",
        body: "Live market data streams into the engine; approved setups become full bracket orders — entry, stop, targets — in milliseconds.",
    },
    {
        n: "04",
        title: "Testnet-first & non-custodial",
        body: "Start on paper trading, graduate to testnet keys you control. CryptAI never takes custody of funds — your keys stay encrypted and yours.",
    },
];

export function FeaturesSection() {
    return (
        <section id="features" className="relative pt-14 pb-24 md:pt-16 md:pb-32">
            <div className="container relative z-10 mx-auto max-w-6xl px-4 md:px-6">
                <div className="mb-12 max-w-2xl">
                    <span className="eyebrow text-accent-300">Why CryptAI</span>
                    <h2 className="display-3 mt-3 text-balance">A quant desk that runs itself</h2>
                    <p className="body-md mt-4 text-pretty text-muted-foreground">
                        Everything you need to research, validate, and deploy algorithmic
                        strategies — in one cohesive terminal.
                    </p>
                </div>

                <motion.div
                    initial={{ opacity: 0, y: 12 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-80px" }}
                    transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                    className="grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2"
                >
                    {features.map((feature) => (
                        <div
                            key={feature.n}
                            className="group bg-surface p-7 transition-colors duration-150 hover:bg-elevated/60 md:p-8"
                        >
                            <span className="num text-xs text-accent-300">{feature.n}</span>
                            <h3 className="heading-4 mt-4 mb-2 text-[17px]">{feature.title}</h3>
                            <p className="body-sm max-w-md">{feature.body}</p>
                        </div>
                    ))}
                </motion.div>
            </div>
        </section>
    );
}
