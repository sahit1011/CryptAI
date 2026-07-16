"use client";

import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { useEffect, useState } from "react";
import { BackgroundGrid } from "./BackgroundGrid";
import { HeroDemo } from "./HeroDemo";

/*
 * Hero — asymmetric two-column: a typed, left-aligned claim on the left and a
 * flat live-chart panel on the right (the animated BTC line chart, kept from an
 * earlier iteration by request — now framed in the hairline terminal card
 * instead of a tilted fake-browser). One crimson moment per column.
 */

const container = {
    hidden: {},
    visible: { transition: { staggerChildren: 0.07, delayChildren: 0.05 } },
};
const item = {
    hidden: { opacity: 0, y: 10 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.45, ease: [0.16, 1, 0.3, 1] as const } },
};

const LINE1 = "Multiple minds.";
const LINE2 = "One disciplined trader.";
const HEADLINE = `${LINE1}\n${LINE2}`;

/*
 * TypedHeadline — the claim types itself once per page load, terminal-style:
 * line one (serif italic), a 3s hold on the blinking cursor, then line two.
 *  - runs ONCE (no loop); an invisible copy of the full text reserves the
 *    exact space → zero layout shift while typing
 *  - the block cursor blinks during typing/hold and quietly disappears after
 *  - reduced-motion users (and crawlers, via aria-label) get the text instantly
 */
const TYPE_SPEED_MS = 75;
const LINE_HOLD_MS = 3000;

function TypedHeadline() {
    const reduced = useReducedMotion();
    const [count, setCount] = useState(0);
    const [cursorGone, setCursorGone] = useState(false);
    const done = count >= HEADLINE.length;

    useEffect(() => {
        if (reduced) {
            // Deferred (not sync-in-effect): show the full headline immediately.
            const t = setTimeout(() => {
                setCount(HEADLINE.length);
                setCursorGone(true);
            }, 0);
            return () => clearTimeout(t);
        }
        let i = 0;
        let interval: ReturnType<typeof setInterval> | null = null;
        let hold: ReturnType<typeof setTimeout> | null = null;

        const typeLine2 = () => {
            i += 1; // consume the newline
            setCount(i);
            interval = setInterval(() => {
                i += 1;
                setCount(i);
                if (i >= HEADLINE.length && interval) clearInterval(interval);
            }, TYPE_SPEED_MS);
        };

        interval = setInterval(() => {
            i += 1;
            setCount(i);
            if (i === LINE1.length && interval) {
                // Line one finished — hold on the blinking cursor, then continue.
                clearInterval(interval);
                hold = setTimeout(typeLine2, LINE_HOLD_MS);
            }
        }, TYPE_SPEED_MS);

        return () => {
            if (interval) clearInterval(interval);
            if (hold) clearTimeout(hold);
        };
    }, [reduced]);

    // Let the cursor blink twice after finishing, then remove it.
    useEffect(() => {
        if (!done || reduced) return;
        const t = setTimeout(() => setCursorGone(true), 1800);
        return () => clearTimeout(t);
    }, [done, reduced]);

    const typed = HEADLINE.slice(0, count);
    const [t1, t2 = ""] = typed.split("\n");
    const cursorOnLine2 = typed.includes("\n");
    // Line one is the editorial accent: Instrument Serif italic in crimson —
    // accent-400 sits a step below full saturation so it complements rather
    // than shouts; optically matched with a slight size bump + relaxed tracking.
    const line1Class = "font-serif italic tracking-[-0.01em] text-[1.06em] text-accent-300";

    return (
        <h1 className="display-1 mb-6 text-foreground" aria-label={`${LINE1} ${LINE2}`}>
            <span aria-hidden="true" className="relative block">
                {/* Invisible full headline reserves the final box. */}
                <span className="invisible block">
                    <span className={line1Class}>{LINE1}</span>
                    <br />
                    {LINE2}
                </span>
                <span className="absolute inset-0">
                    <span className={line1Class}>{t1}</span>
                    {!cursorOnLine2 && !cursorGone && <Cursor />}
                    <br />
                    {t2}
                    {cursorOnLine2 && !cursorGone && <Cursor />}
                </span>
            </span>
        </h1>
    );
}

function Cursor() {
    return (
        <span className="type-cursor ml-1 inline-block h-[0.82em] w-[0.45ch] translate-y-[0.1em] bg-accent" />
    );
}

export function HeroSection() {
    return (
        <section className="relative overflow-hidden pt-36 pb-24 md:pt-44 md:pb-32">
            <BackgroundGrid />

            {/* ---- Ambient product demo — a 3D-tilted background layer ----------
                The live quad demo lies diagonally in perspective behind the hero
                (rotated ~30° about its horizontal axis + a diagonal twist) and
                dissolves right→left so the claim stays perfectly readable.
                Desktop-only ambience; decorative, so aria-hidden. */}
            <motion.div
                aria-hidden
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 1.4, delay: 0.5 }}
                className="pointer-events-none absolute inset-y-0 right-[-14%] z-0 hidden w-[74%] select-none lg:block"
                style={{
                    perspective: "1800px",
                    maskImage: "linear-gradient(to left, black 42%, transparent 96%)",
                    WebkitMaskImage: "linear-gradient(to left, black 42%, transparent 96%)",
                }}
            >
                <div
                    className="absolute right-0 top-1/2 w-[880px] max-w-none opacity-80"
                    style={{
                        transform:
                            "translateY(-50%) rotateX(30deg) rotateY(-18deg) rotateZ(10deg) scale(1.08)",
                        transformStyle: "preserve-3d",
                    }}
                >
                    <div className="overflow-hidden rounded-xl border border-border bg-surface/90 shadow-[var(--shadow-elevation-high)]">
                        <HeroDemo />
                    </div>
                </div>
            </motion.div>

            <div className="container relative z-10 mx-auto max-w-6xl px-4 md:px-6">
                {/* ---- Claim ---------------------------------------------------- */}
                <motion.div variants={container} initial="hidden" animate="visible" className="max-w-2xl">
                    <motion.p variants={item} className="eyebrow mb-5 text-foreground">
                        Multi-agent trading system
                    </motion.p>

                    <motion.div variants={item}>
                        <TypedHeadline />
                    </motion.div>

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

                    {/* Mobile/tablet: the demo as a regular panel below the claim */}
                    <motion.div
                        variants={item}
                        className="mt-12 overflow-hidden rounded-xl border border-border bg-surface lg:hidden"
                    >
                        <HeroDemo />
                    </motion.div>
                </motion.div>
            </div>
        </section>
    );
}
