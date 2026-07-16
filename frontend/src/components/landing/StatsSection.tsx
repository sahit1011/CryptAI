"use client";

import { motion, useInView } from "framer-motion";
import { useEffect, useRef, useState } from "react";

import { Value } from "@/components/ui/value";

/*
 * StatsSection — an illustrative marketing band. Numbers are clearly labelled
 * "Illustrative" so they never read as live/reported metrics, render in Geist
 * Mono via <Value>, and animate with a deterministic count-up (no Math.random
 * during render). Crimson accents only; sits on bg-background with a shared
 * aurora atmosphere layer for a continuous feel.
 */

interface Stat {
    /** Numeric target the count-up animates toward. */
    target: number;
    /** Decimal places for the animated value. */
    decimals: number;
    prefix?: string;
    suffix?: string;
    label: string;
}

const stats: Stat[] = [
    { target: 2.4, decimals: 1, prefix: "$", suffix: "B", label: "Simulated volume routed" },
    { target: 12, decimals: 0, suffix: "+", label: "Specialized agent types" },
    { target: 99.99, decimals: 2, suffix: "%", label: "Target uptime" },
    { target: 50, decimals: 0, prefix: "<", suffix: "ms", label: "Signal-to-order latency" },
];

/*
 * CountUp — animates a value from 0 → target when it scrolls into view, using
 * requestAnimationFrame (client-only, deterministic — no randomness). Renders
 * through <Value> so the number stays in Geist Mono + tabular figures.
 */
function CountUp({ stat }: { stat: Stat }) {
    const ref = useRef<HTMLSpanElement>(null);
    const inView = useInView(ref, { once: true, margin: "-60px" });
    const [display, setDisplay] = useState(0);

    useEffect(() => {
        if (!inView) return;

        let raf = 0;
        const duration = 1100;
        let start: number | null = null;

        const tick = (now: number) => {
            if (start === null) start = now;
            const t = Math.min((now - start) / duration, 1);
            // easeOutCubic for a smooth, premium settle.
            const eased = 1 - Math.pow(1 - t, 3);
            setDisplay(stat.target * eased);
            if (t < 1) raf = requestAnimationFrame(tick);
        };

        raf = requestAnimationFrame(tick);
        return () => cancelAnimationFrame(raf);
    }, [inView, stat.target]);

    return (
        <Value
            ref={ref}
            value={display}
            decimals={stat.decimals}
            prefix={stat.prefix}
            suffix={stat.suffix}
            className="display-3 text-4xl text-foreground md:text-[2.75rem]"
        />
    );
}

/*
 * A single bordered stat band with hairline dividers — numbers in plain
 * foreground mono, labels in small caps. One quiet strip, not four floating
 * glass cards: the restraint is the design.
 */
export function StatsSection() {
    return (
        <section className="relative overflow-hidden py-20 md:py-24">
            <div className="container relative z-10 mx-auto max-w-6xl px-4 md:px-6">
                <div className="mb-10 max-w-2xl">
                    <span className="eyebrow text-accent-300">By the numbers</span>
                    <h2 className="display-3 mt-3 text-balance">Built to run at market speed</h2>
                    <p className="body-sm mt-3">
                        Illustrative figures shown to convey scale and design targets — not
                        reported production metrics.
                    </p>
                </div>

                <motion.div
                    initial={{ opacity: 0, y: 12 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-80px" }}
                    transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                    className="grid grid-cols-2 divide-border overflow-hidden rounded-xl border border-border bg-surface max-lg:gap-px max-lg:bg-border lg:grid-cols-4 lg:divide-x"
                >
                    {stats.map((stat) => (
                        <div key={stat.label} className="bg-surface px-6 py-8">
                            <CountUp stat={stat} />
                            <div className="label-md mt-3 text-subtle-foreground">{stat.label}</div>
                        </div>
                    ))}
                </motion.div>
            </div>
        </section>
    );
}
