"use client";

import { motion, useInView } from "framer-motion";
import { useEffect, useRef, useState } from "react";

import { Value } from "@/components/ui/value";

/*
 * StatsSection — an illustrative marketing band. Numbers are clearly labelled
 * "Illustrative" so they never read as live/reported metrics, render in Geist
 * Mono via <Value>, and animate with a deterministic count-up (no Math.random
 * during render). Emerald accents only; sits on bg-background with a shared
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
            className="display-3 text-4xl md:text-5xl text-gradient-emerald"
        />
    );
}

export function StatsSection() {
    return (
        <section className="relative overflow-hidden border-y border-border py-20 md:py-24">
            {/* Shared emerald atmosphere — keeps the page one continuous feel. */}
            <div className="aurora z-0 opacity-70" aria-hidden />

            <div className="container relative z-10 mx-auto px-4 md:px-6">
                <div className="mx-auto mb-12 max-w-2xl text-center">
                    <span className="label-md text-accent-300">By the numbers</span>
                    <h2 className="display-3 mt-3 text-balance">Built to run at market speed</h2>
                    <p className="body-sm mt-3">
                        Illustrative figures shown to convey scale and design targets — not
                        reported production metrics.
                    </p>
                </div>

                <div className="grid grid-cols-2 gap-5 lg:grid-cols-4">
                    {stats.map((stat, i) => (
                        <motion.div
                            key={stat.label}
                            initial={{ opacity: 0, y: 24 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true, margin: "-80px" }}
                            transition={{ duration: 0.5, delay: i * 0.08, ease: [0.16, 1, 0.3, 1] }}
                            className="glass-panel glass-panel-hover flex flex-col items-center justify-center px-4 py-8 text-center"
                        >
                            <CountUp stat={stat} />
                            <div className="label-md mt-3 text-subtle-foreground">{stat.label}</div>
                        </motion.div>
                    ))}
                </div>
            </div>
        </section>
    );
}
