"use client";

import { motion } from "framer-motion";

/*
 * The numbers band — one honest sentence instead of the four-tile metric
 * template. Every figure here is real and enforced in the codebase (candle
 * window, timeframes, markets, risk cap), not marketing inflation. The mono
 * crimson numbers inside running prose are the signature move.
 */

function Num({ children }: { children: React.ReactNode }) {
    return <span className="num font-semibold text-accent-300">{children}</span>;
}

export function StatsSection() {
    return (
        <section className="relative border-y border-border bg-elevated/20 py-20 md:py-24">
            <div className="container relative z-10 mx-auto max-w-6xl px-4 md:px-6">
                <motion.p
                    initial={{ opacity: 0, y: 14 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-80px" }}
                    transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
                    className="max-w-4xl text-2xl font-medium leading-relaxed tracking-tight text-foreground md:text-[2rem] md:leading-snug"
                >
                    Every cycle, the desk reads <Num>500</Num> candles across{" "}
                    <Num>5</Num> timeframes on <Num>3</Num> markets, argues{" "}
                    <Num>one</Num> setup, and sizes it to at most <Num>2%</Num> risk.
                </motion.p>
                <motion.p
                    initial={{ opacity: 0 }}
                    whileInView={{ opacity: 1 }}
                    viewport={{ once: true, margin: "-80px" }}
                    transition={{ duration: 0.5, delay: 0.25 }}
                    className="num mt-6 text-sm text-subtle-foreground"
                >
                    the only numbers that matter are enforced, not advertised
                </motion.p>
            </div>
        </section>
    );
}
