"use client";

import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { MousePointer2, Zap, Check } from "lucide-react";
import { useEffect, useState } from "react";

/*
 * HeroDemo — a looping, scripted "trader's routine" inside the hero panel
 * (TradingView-hero style, but our product): the chart streams, the AI marks
 * up structure, a setup card arrives, the cursor executes, the order fills.
 * Pure framer-motion — no video asset, stays crisp at any DPI and weighs 0 MB.
 * Reduced-motion users get the final composed frame, statically.
 */

type Phase = "chart" | "analyze" | "signal" | "execute" | "filled";

// Phase timeline (ms in each phase before advancing).
const SCRIPT: [Phase, number][] = [
    ["chart", 2200],
    ["analyze", 3000],
    ["signal", 2600],
    ["execute", 1600],
    ["filled", 2800],
];

// Simulated-cursor waypoints per phase (percent coordinates inside the panel).
const CURSOR: Record<Phase, { left: string; top: string }> = {
    chart: { left: "86%", top: "22%" },
    analyze: { left: "58%", top: "58%" },
    signal: { left: "40%", top: "78%" },
    execute: { left: "27%", top: "87%" },
    filled: { left: "34%", top: "72%" },
};

export function HeroDemo() {
    const reduced = useReducedMotion();
    const [phase, setPhase] = useState<Phase>("chart");

    useEffect(() => {
        if (reduced) {
            const t = setTimeout(() => setPhase("filled"), 0);
            return () => clearTimeout(t);
        }
        let idx = 0;
        let timer: ReturnType<typeof setTimeout>;
        const next = () => {
            idx = (idx + 1) % SCRIPT.length;
            setPhase(SCRIPT[idx][0]);
            timer = setTimeout(next, SCRIPT[idx][1]);
        };
        timer = setTimeout(next, SCRIPT[0][1]);
        return () => clearTimeout(timer);
    }, [reduced]);

    const analyzed = phase !== "chart";
    const signalUp = phase === "signal" || phase === "execute" || phase === "filled";
    const filled = phase === "filled";

    return (
        <div>
            {/* Price header + phase caption */}
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
                {/* The routine narrated in one quiet mono line. */}
                <AnimatePresence mode="wait">
                    <motion.span
                        key={phase}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        transition={{ duration: 0.25 }}
                        className="num text-[10px] uppercase tracking-wider text-subtle-foreground"
                    >
                        {phase === "chart" && "streaming live data"}
                        {phase === "analyze" && "agents analyzing structure"}
                        {phase === "signal" && "setup published"}
                        {phase === "execute" && "executing…"}
                        {phase === "filled" && "bracket order filled"}
                    </motion.span>
                </AnimatePresence>
            </div>

            {/* Chart + scripted overlays */}
            <div className="relative mx-4 mb-4 mt-2 aspect-[16/10]">
                <svg className="absolute inset-0 h-full w-full" viewBox="0 0 400 200" preserveAspectRatio="none">
                    <defs>
                        <linearGradient id="hero-area-gradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="var(--accent-400)" stopOpacity="0.28" />
                            <stop offset="100%" stopColor="var(--accent-400)" stopOpacity="0.03" />
                        </linearGradient>
                    </defs>

                    {[40, 80, 120, 160].map((y) => (
                        <line key={y} x1="0" y1={y} x2="400" y2={y} stroke="var(--border-strong)" strokeWidth="0.5" opacity="0.35" />
                    ))}

                    <motion.path
                        d="M0,190 Q40,180 80,185 T160,180 T240,170 T320,175 T400,160 V200 H0 Z"
                        fill="url(#hero-area-gradient)"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.6, duration: 1 }}
                    />
                    <motion.path
                        d="M0,140 Q50,120 100,130 T200,110 T300,100 T400,90"
                        fill="none"
                        stroke="var(--accent-500)"
                        strokeWidth="2"
                        strokeLinecap="round"
                        initial={{ pathLength: 0 }}
                        animate={{ pathLength: 1 }}
                        transition={{ duration: 2, ease: "easeInOut" }}
                    />

                    {/* AI markup — demand zone + swept level, drawn in the analyze phase */}
                    <AnimatePresence>
                        {analyzed && (
                            <motion.g
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                exit={{ opacity: 0 }}
                                transition={{ duration: 0.5 }}
                            >
                                <rect x="120" y="128" width="120" height="26" fill="var(--profit)" opacity="0.08" />
                                <line x1="120" y1="128" x2="240" y2="128" stroke="var(--profit)" strokeWidth="1" strokeDasharray="3,3" opacity="0.5" />
                                <line x1="0" y1="112" x2="400" y2="112" stroke="var(--accent-400)" strokeWidth="1" strokeDasharray="4,4" opacity="0.55" />
                                <circle cx="205" cy="109" r="4" fill="var(--accent-500)" stroke="var(--foreground)" strokeWidth="1.5" />
                            </motion.g>
                        )}
                    </AnimatePresence>
                </svg>

                {/* Structure labels (HTML so type stays crisp) */}
                <AnimatePresence>
                    {analyzed && (
                        <motion.div
                            initial={{ opacity: 0, y: 4 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0 }}
                            transition={{ delay: 0.3, duration: 0.35 }}
                            className="absolute left-[32%] top-[68%] rounded-sm border border-profit/30 bg-background/85 px-1.5 py-0.5 backdrop-blur-sm"
                        >
                            <span className="num text-[9px] text-profit">demand zone</span>
                        </motion.div>
                    )}
                </AnimatePresence>
                <AnimatePresence>
                    {analyzed && (
                        <motion.div
                            initial={{ opacity: 0, y: 4 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0 }}
                            transition={{ delay: 0.55, duration: 0.35 }}
                            className="absolute right-[8%] top-[48%] rounded-sm border border-accent/30 bg-background/85 px-1.5 py-0.5 backdrop-blur-sm"
                        >
                            <span className="num text-[9px] text-accent-300">liquidity sweep</span>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* Setup card — slides in when the strategy agent publishes */}
                <AnimatePresence>
                    {signalUp && (
                        <motion.div
                            initial={{ opacity: 0, y: 14 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: 10 }}
                            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                            className="absolute bottom-2 left-2 w-56 rounded-lg border border-border bg-background/95 p-3 backdrop-blur-sm"
                        >
                            <div className="mb-2 flex items-center justify-between">
                                <div className="flex items-center gap-1.5">
                                    <span className="text-xs font-semibold text-foreground">BTCUSDT</span>
                                    <span className="rounded-sm border border-profit/30 bg-profit/10 px-1 py-px text-[8px] font-medium uppercase tracking-wider text-profit">
                                        Long
                                    </span>
                                </div>
                                <span className="num text-[9px] text-muted-foreground">conf 74%</span>
                            </div>
                            <div className="mb-2.5 grid grid-cols-3 gap-px overflow-hidden rounded-sm border border-border bg-border text-center">
                                {[["Entry", "43,284"], ["Stop", "42,950"], ["Target", "44,090"]].map(([k, v]) => (
                                    <div key={k} className="bg-surface px-1 py-1">
                                        <div className="text-[7px] uppercase tracking-wider text-subtle-foreground">{k}</div>
                                        <div className="num text-[10px] text-foreground">{v}</div>
                                    </div>
                                ))}
                            </div>
                            {/* Execute — pressed by the scripted cursor */}
                            <motion.div
                                animate={
                                    phase === "execute"
                                        ? { scale: [1, 0.96, 1] }
                                        : { scale: 1 }
                                }
                                transition={{ duration: 0.35 }}
                                className={`flex h-6 items-center justify-center gap-1 rounded-md text-[10px] font-medium ${
                                    filled
                                        ? "border border-profit/30 bg-profit/10 text-profit"
                                        : "bg-primary text-primary-foreground"
                                }`}
                            >
                                {filled ? (
                                    <>
                                        <Check className="size-3" /> Filled · bracket live
                                    </>
                                ) : (
                                    <>
                                        <Zap className="size-3" /> Execute
                                    </>
                                )}
                            </motion.div>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* P&L chip after the fill */}
                <AnimatePresence>
                    {filled && (
                        <motion.div
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0 }}
                            transition={{ duration: 0.35 }}
                            className="absolute right-2 top-2 rounded-md border border-profit/30 bg-profit/10 px-2 py-1"
                        >
                            <span className="num text-[10px] font-medium text-profit">open P&L +$118.40</span>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* Scripted cursor */}
                {!reduced && (
                    <motion.div
                        animate={CURSOR[phase]}
                        transition={{ type: "spring", stiffness: 90, damping: 16 }}
                        className="pointer-events-none absolute z-20"
                        style={{ left: CURSOR.chart.left, top: CURSOR.chart.top }}
                    >
                        <MousePointer2 className="size-3.5 fill-foreground text-foreground drop-shadow" />
                    </motion.div>
                )}
            </div>
        </div>
    );
}
