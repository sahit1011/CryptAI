"use client";

import { motion } from "framer-motion";

/*
 * The discipline band — the contrarian claim no bot shop makes: most cycles,
 * the desk does nothing. A day of analysis cycles rendered as dots; the rare
 * crimson ones are published setups, everything else is a deliberate pass.
 * Restraint, made visible.
 */

// One day = 144 ten-minute cycles. Deterministic pattern (no randomness):
// a handful of setups, spaced like a real quiet trading day.
const CYCLES = 144;
const SETUP_AT = new Set([11, 38, 71, 102, 131]);

export function StatsSection() {
    return (
        <section className="relative border-y border-border bg-elevated/20 py-20 md:py-24">
            <div className="container relative z-10 mx-auto max-w-6xl px-4 md:px-6">
                <motion.h2
                    initial={{ opacity: 0, y: 14 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-80px" }}
                    transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
                    className="display-2 max-w-3xl text-balance"
                >
                    Most cycles, nothing{" "}
                    <em className="font-serif text-accent-300">clears the gate.</em>
                </motion.h2>

                <motion.p
                    initial={{ opacity: 0, y: 10 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-80px" }}
                    transition={{ duration: 0.5, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
                    className="body-md mt-4 max-w-xl text-muted-foreground"
                >
                    That&apos;s the point. A bot that trades every signal has no opinion —
                    CryptAI passes on anything the risk rules don&apos;t clear.
                </motion.p>

                {/* A day of cycles. Each dot is one 10-minute analysis pass. */}
                <motion.div
                    initial={{ opacity: 0 }}
                    whileInView={{ opacity: 1 }}
                    viewport={{ once: true, margin: "-80px" }}
                    transition={{ duration: 0.6, delay: 0.2 }}
                    className="mt-10"
                >
                    <div className="flex flex-wrap gap-[7px]" aria-hidden>
                        {Array.from({ length: CYCLES }, (_, i) => (
                            <motion.span
                                key={i}
                                initial={{ opacity: 0 }}
                                whileInView={{ opacity: 1 }}
                                viewport={{ once: true, margin: "-60px" }}
                                transition={{ delay: 0.3 + i * 0.008, duration: 0.2 }}
                                className={
                                    SETUP_AT.has(i)
                                        ? "size-2 rounded-full bg-accent shadow-[0_0_8px_var(--accent-muted)]"
                                        : "size-2 rounded-full bg-border"
                                }
                            />
                        ))}
                    </div>
                    <div className="num mt-5 flex flex-wrap items-center gap-x-6 gap-y-1.5 text-xs text-subtle-foreground">
                        <span className="flex items-center gap-2">
                            <span className="size-2 rounded-full bg-border" /> analyzed, passed
                        </span>
                        <span className="flex items-center gap-2">
                            <span className="size-2 rounded-full bg-accent" /> setup published
                        </span>
                        <span>one day · 144 cycles · discipline is the feature</span>
                    </div>
                </motion.div>
            </div>
        </section>
    );
}
