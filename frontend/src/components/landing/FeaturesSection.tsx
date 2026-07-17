"use client";

import { motion, useReducedMotion, useScroll, useTransform, type MotionValue } from "framer-motion";
import { Check } from "lucide-react";
import { useRef } from "react";

/*
 * "Why CryptAI" — the manifesto is scroll-scrubbed: each word illuminates as
 * the reader scrolls through the section (responds to input, not a timer;
 * scrolling back dims them again). Below, the asymmetric split: the risk gate
 * as a spec sheet, supporting capabilities as a quiet hairline list.
 */

// Manifesto tokens; `serif` marks the crimson italic voice. `br` breaks the line.
const TOKENS: { text: string; serif?: boolean; br?: boolean }[] = [
    { text: "Most" }, { text: "bots:" }, { text: "one" }, { text: "model," },
    { text: "one" }, { text: "API" }, { text: "key.", br: true },
    { text: "CryptAI:" },
    { text: "specialists", serif: true }, { text: "that", serif: true },
    { text: "argue,", serif: true }, { text: "a", serif: true },
    { text: "gate", serif: true }, { text: "that", serif: true },
    { text: "decides.", serif: true },
];

const GATE_RULES = [
    { rule: "max risk per trade", value: "2%" },
    { rule: "max portfolio heat", value: "6%" },
    { rule: "max daily loss", value: "5%" },
    { rule: "max concurrent positions", value: "3" },
];

const CAPABILITIES = [
    {
        title: "Autonomous agents",
        body: "Data, analysis, memory and strategy each argue their part of a trade — setups survive scrutiny before they reach you.",
    },
    {
        title: "Real-time execution",
        body: "Approved setups become full bracket orders — entry, stop, targets — in milliseconds.",
    },
    {
        title: "Non-custodial, testnet-first",
        body: "Start on paper trading; your exchange keys stay encrypted and yours. CryptAI never takes custody.",
    },
];

const reveal = {
    initial: { opacity: 0, y: 14 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, margin: "-80px" },
};

function Word({
    token,
    index,
    progress,
    reduced,
}: {
    token: (typeof TOKENS)[number];
    index: number;
    progress: MotionValue<number>;
    reduced: boolean;
}) {
    // Each word owns a slice of the scrub range and fades up within it.
    const start = index / TOKENS.length;
    const end = (index + 1) / TOKENS.length;
    const opacity = useTransform(progress, [start, end], [0.12, 1]);

    return (
        <>
            <motion.span
                style={reduced ? undefined : { opacity }}
                className={token.serif ? "font-serif italic text-accent-300" : undefined}
            >
                {token.text}
            </motion.span>{" "}
            {token.br && <br />}
        </>
    );
}

export function FeaturesSection() {
    const reduced = useReducedMotion() ?? false;
    const headlineRef = useRef<HTMLHeadingElement | null>(null);
    // Scrub window: starts when the headline enters the lower viewport, done
    // by the time it reaches the upper third.
    const { scrollYProgress } = useScroll({
        target: headlineRef,
        offset: ["start 0.92", "start 0.38"],
    });

    return (
        <section id="features" className="relative pt-14 pb-24 md:pt-16 md:pb-32">
            <div className="container relative z-10 mx-auto max-w-6xl px-4 md:px-6">
                {/* Manifesto — illuminated by the reader's own scroll. */}
                <h2 ref={headlineRef} className="display-2 max-w-3xl text-balance text-foreground">
                    {TOKENS.map((token, i) => (
                        <Word key={i} token={token} index={i} progress={scrollYProgress} reduced={reduced} />
                    ))}
                </h2>

                <div className="mt-14 grid gap-12 lg:grid-cols-[1.1fr_1fr] lg:gap-16">
                    {/* The risk gate — spec sheet, not marketing card. */}
                    <motion.div
                        {...reveal}
                        transition={{ duration: 0.55, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
                    >
                        <h3 className="heading-2 text-foreground">The risk gate</h3>
                        <p className="body-md mt-3 max-w-lg text-muted-foreground">
                            Every AI-drafted setup passes a deterministic rule set before an
                            order exists. The models can argue all they want — none of them
                            can talk past it.
                        </p>

                        <div className="mt-6 overflow-hidden rounded-lg border border-border">
                            {GATE_RULES.map((r, i) => (
                                <div
                                    key={r.rule}
                                    className={`flex items-center justify-between px-4 py-3 ${
                                        i > 0 ? "border-t border-border" : ""
                                    }`}
                                >
                                    <span className="num text-sm text-muted-foreground">{r.rule}</span>
                                    <span className="flex items-center gap-2.5">
                                        <span className="num text-sm font-semibold text-foreground">{r.value}</span>
                                        <Check className="size-3.5 text-profit" />
                                    </span>
                                </div>
                            ))}
                            <div className="border-t border-border bg-elevated/40 px-4 py-2.5">
                                <span className="num text-xs text-subtle-foreground">
                                    enforced in code · not a model output
                                </span>
                            </div>
                        </div>
                    </motion.div>

                    {/* Supporting capabilities — a quiet list, not cards. */}
                    <motion.div
                        {...reveal}
                        transition={{ duration: 0.55, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
                        className="lg:pt-2"
                    >
                        {CAPABILITIES.map((c, i) => (
                            <div
                                key={c.title}
                                className={`py-6 ${i > 0 ? "border-t border-border" : "lg:pt-0"}`}
                            >
                                <h3 className="text-[17px] font-semibold tracking-tight text-foreground">
                                    {c.title}
                                </h3>
                                <p className="body-sm mt-2 max-w-md">{c.body}</p>
                            </div>
                        ))}
                    </motion.div>
                </div>
            </div>
        </section>
    );
}
