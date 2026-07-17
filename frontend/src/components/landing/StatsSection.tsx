"use client";

import { motion, useMotionValueEvent, useReducedMotion, useScroll } from "framer-motion";
import { useRef, useState } from "react";

/*
 * The discipline band — a day of analysis cycles as dots, filled by the
 * reader's own scroll (scrub, not a timer: scroll back and the day rewinds).
 * The rare crimson dots are published setups; everything else is a deliberate
 * pass. Restraint, made visible — and interactive.
 */

// One day = 144 ten-minute cycles. Deterministic pattern (no randomness):
// a handful of setups, spaced like a real quiet trading day.
const CYCLES = 144;
const SETUP_AT = new Set([11, 38, 71, 102, 131]);

export function StatsSection() {
    const reduced = useReducedMotion() ?? false;
    const bandRef = useRef<HTMLDivElement | null>(null);
    const { scrollYProgress } = useScroll({
        target: bandRef,
        offset: ["start 0.9", "start 0.3"],
    });
    const [lit, setLit] = useState(reduced ? CYCLES : 0);

    useMotionValueEvent(scrollYProgress, "change", (v) => {
        if (!reduced) setLit(Math.round(v * CYCLES));
    });

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

                {/* A day of cycles, driven by scroll. */}
                <div ref={bandRef} className="mt-10">
                    <div className="flex flex-wrap gap-[7px]" aria-hidden>
                        {Array.from({ length: CYCLES }, (_, i) => {
                            const on = i < lit;
                            const isSetup = SETUP_AT.has(i);
                            return (
                                <span
                                    key={i}
                                    className={
                                        isSetup && on
                                            ? "size-2 rounded-full bg-accent shadow-[0_0_8px_var(--accent-muted)] transition-all duration-200"
                                            : on
                                                ? "size-2 rounded-full bg-border-strong transition-colors duration-200"
                                                : "size-2 rounded-full bg-border/40 transition-colors duration-200"
                                    }
                                />
                            );
                        })}
                    </div>
                    <div className="num mt-5 flex flex-wrap items-center gap-x-6 gap-y-1.5 text-xs text-subtle-foreground">
                        <span className="flex items-center gap-2">
                            <span className="size-2 rounded-full bg-border-strong" /> analyzed, passed
                        </span>
                        <span className="flex items-center gap-2">
                            <span className="size-2 rounded-full bg-accent" /> setup published
                        </span>
                        <span>one day · 144 cycles · discipline is the feature</span>
                    </div>
                </div>
            </div>
        </section>
    );
}
