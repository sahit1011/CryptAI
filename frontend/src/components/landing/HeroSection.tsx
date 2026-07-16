"use client";

import {
    motion,
    useMotionValue,
    useReducedMotion,
    useSpring,
    useTransform,
} from "framer-motion";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { useEffect, useState } from "react";
import { BackgroundGrid } from "./BackgroundGrid";

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

const LINE1 = "Five minds,";
const LINE2 = "one disciplined trader.";
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
    const reduced = useReducedMotion();

    // Hover tilt physics for the chart panel — springs give it weight, and the
    // angle stays modest (±6°) so it reads as depth, not a gimmick.
    const mx = useMotionValue(0);
    const my = useMotionValue(0);
    const sx = useSpring(mx, { stiffness: 140, damping: 18 });
    const sy = useSpring(my, { stiffness: 140, damping: 18 });
    const rotateX = useTransform(sy, [-0.5, 0.5], [6, -6]);
    const rotateY = useTransform(sx, [-0.5, 0.5], [-6, 6]);

    function handleTilt({ currentTarget, clientX, clientY }: React.MouseEvent) {
        if (reduced) return;
        const { left, top, width, height } = currentTarget.getBoundingClientRect();
        mx.set((clientX - left) / width - 0.5);
        my.set((clientY - top) / height - 0.5);
    }

    function resetTilt() {
        mx.set(0);
        my.set(0);
    }

    return (
        <section className="relative overflow-hidden pt-36 pb-24 md:pt-44 md:pb-32">
            <BackgroundGrid />

            <div className="container relative z-10 mx-auto grid max-w-6xl items-center gap-14 px-4 md:px-6 lg:grid-cols-[1.05fr_0.95fr] lg:gap-10">
                {/* ---- Claim ---------------------------------------------------- */}
                <motion.div variants={container} initial="hidden" animate="visible">
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

                </motion.div>

                {/* ---- Chart panel (hover tilt) --------------------------------- */}
                <motion.div
                    initial={{ opacity: 0, y: 14 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, delay: 0.25, ease: [0.16, 1, 0.3, 1] }}
                    className="relative"
                    style={{ perspective: 1000 }}
                    onMouseMove={handleTilt}
                    onMouseLeave={resetTilt}
                >
                    <motion.div
                        style={{ rotateX, rotateY }}
                        className="overflow-hidden rounded-xl border border-border bg-surface"
                    >
                        {/* Price header + timeframes */}
                        <div className="flex items-center justify-between px-4 pt-4">
                            <div>
                                <div className="text-[10px] font-medium uppercase tracking-wider text-subtle-foreground">
                                    BTC/USD
                                </div>
                                <div className="num flex items-center gap-2 text-lg font-semibold text-foreground">
                                    $43,284.50
                                    <span className="num text-xs font-medium text-profit">+2.4%</span>
                                </div>
                            </div>
                            <div className="flex gap-1">
                                {["1H", "24H", "7D", "1M"].map((tf, i) => (
                                    <span
                                        key={tf}
                                        className={`num rounded-sm px-2 py-1 text-[10px] font-medium ${
                                            i === 1
                                                ? "border border-accent/40 bg-accent/15 text-accent-300"
                                                : "border border-border text-subtle-foreground"
                                        }`}
                                    >
                                        {tf}
                                    </span>
                                ))}
                            </div>
                        </div>

                        {/* The chart — animated draw-in line + area, crosshair, OHLC readout. */}
                        <div className="relative mx-4 mb-4 mt-2 aspect-[16/9]">
                            <svg
                                className="absolute inset-0 h-full w-full"
                                viewBox="0 0 400 200"
                                preserveAspectRatio="none"
                            >
                                <defs>
                                    <linearGradient id="hero-area-gradient" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="var(--accent-400)" stopOpacity="0.28" />
                                        <stop offset="100%" stopColor="var(--accent-400)" stopOpacity="0.03" />
                                    </linearGradient>
                                </defs>

                                {/* Faint horizontal grid */}
                                {[40, 80, 120, 160].map((y) => (
                                    <line
                                        key={y}
                                        x1="0" y1={y} x2="400" y2={y}
                                        stroke="var(--border-strong)" strokeWidth="0.5" opacity="0.35"
                                    />
                                ))}

                                <motion.path
                                    d="M0,190 Q40,180 80,185 T160,180 T240,170 T320,175 T400,160 V200 H0 Z"
                                    fill="url(#hero-area-gradient)"
                                    initial={{ opacity: 0, scaleY: 0 }}
                                    animate={{ opacity: 1, scaleY: 1 }}
                                    transition={{ delay: 1.2, duration: 1 }}
                                    style={{ transformOrigin: "bottom" }}
                                />

                                <motion.path
                                    d="M0,140 Q50,120 100,130 T200,110 T300,100 T400,90"
                                    fill="none"
                                    stroke="var(--accent-500)"
                                    strokeWidth="2"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    initial={{ pathLength: 0, opacity: 0 }}
                                    animate={{ pathLength: 1, opacity: 1 }}
                                    transition={{ delay: 1, duration: 2.5, ease: "easeInOut" }}
                                />

                                {(() => {
                                    // Crosshair pinned to a point on the bezier line (x=280).
                                    const staticX = 280;
                                    const calculateY = (px: number) => {
                                        if (px <= 100) {
                                            const t = px / 100;
                                            return (1 - t) * (1 - t) * 140 + 2 * (1 - t) * t * 120 + t * t * 130;
                                        } else if (px <= 200) {
                                            const t = (px - 100) / 100;
                                            return (1 - t) * (1 - t) * 130 + 2 * (1 - t) * t * 140 + t * t * 110;
                                        } else if (px <= 300) {
                                            const t = (px - 200) / 100;
                                            return (1 - t) * (1 - t) * 110 + 2 * (1 - t) * t * 80 + t * t * 100;
                                        }
                                        const t = (px - 300) / 100;
                                        return (1 - t) * (1 - t) * 100 + 2 * (1 - t) * t * 120 + t * t * 90;
                                    };
                                    const staticY = calculateY(staticX);

                                    return (
                                        <>
                                            <line
                                                x1={staticX} y1="0" x2={staticX} y2="200"
                                                stroke="var(--accent-500)" strokeWidth="1"
                                                strokeDasharray="4,4" opacity="0.7"
                                            />
                                            <line
                                                x1="0" y1={staticY} x2="400" y2={staticY}
                                                stroke="var(--accent-500)" strokeWidth="1"
                                                strokeDasharray="4,4" opacity="0.7"
                                            />
                                            <circle
                                                cx={staticX} cy={staticY} r="5"
                                                fill="var(--accent-500)" stroke="var(--foreground)" strokeWidth="2"
                                            />
                                            <circle
                                                cx={staticX} cy={staticY} r="10"
                                                fill="var(--accent-500)" opacity="0.25"
                                            />
                                        </>
                                    );
                                })()}
                            </svg>

                            {/* OHLC readout at the crosshair */}
                            <motion.div
                                initial={{ opacity: 0, scale: 0.95 }}
                                animate={{ opacity: 1, scale: 1 }}
                                transition={{ delay: 1.6, duration: 0.3 }}
                                className="pointer-events-none absolute z-10"
                                style={{ left: "70%", top: "48%", transform: "translate(14px, -14px)" }}
                            >
                                <div className="rounded-md border border-border bg-background/90 p-2 backdrop-blur-sm">
                                    <div className="num mb-1 text-[9px] font-semibold text-accent-300">BTC/USD</div>
                                    <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[8px]">
                                        <div className="text-subtle-foreground">Open</div>
                                        <div className="num text-right text-foreground">43,120.00</div>
                                        <div className="text-subtle-foreground">High</div>
                                        <div className="num text-right text-profit">43,450.00</div>
                                        <div className="text-subtle-foreground">Low</div>
                                        <div className="num text-right text-loss">43,050.00</div>
                                        <div className="text-subtle-foreground">Close</div>
                                        <div className="num text-right text-foreground">43,284.50</div>
                                    </div>
                                </div>
                            </motion.div>
                        </div>
                    </motion.div>

                    {/* Single quiet accent: a hairline crimson rule under the panel. */}
                    <div className="mx-auto mt-px h-px w-2/3 bg-gradient-to-r from-transparent via-accent/40 to-transparent" />
                </motion.div>
            </div>
        </section>
    );
}
