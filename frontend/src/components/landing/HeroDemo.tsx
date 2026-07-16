"use client";

import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { Zap, Check, MousePointer2, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

/*
 * HeroDemo — the hero panel as a 2×2 quad of independently-looping scenarios
 * (TradingView multi-chart hero, in our product's voice). Each quadrant runs
 * its own multi-step story on its own period so the panel never syncs up:
 *
 *   chart · BTC/USD    curve+priced y-axis → AI markup → setup card →
 *                      CURSOR CLICKS EXECUTE → filled + entry line
 *   trade execution    risk-gate checks → execute → filled → P&L ticks →
 *                      TP1 hit banner
 *   agent activity     pipeline rows → execution row → "cycle complete" chip
 *   portfolio · paper  equity draw → positions → P&L uptick flash →
 *                      closed-trade toast
 *
 * Deterministic mock data; reduced-motion gets static frames.
 */

function QuadLabel({ children, live }: { children: React.ReactNode; live?: boolean }) {
    return (
        <div className="flex items-center gap-1.5 px-3 pt-2.5 pb-1">
            {live && <span className="size-1 animate-pulse-subtle rounded-full bg-accent" />}
            <span className="num text-[9px] uppercase tracking-wider text-subtle-foreground">{children}</span>
        </div>
    );
}

/** Chained phase runner: [phase, ms-until-next]. Returns current phase. */
function usePhases<T extends string>(steps: [T, number][], reduced: boolean, fallback: T): T {
    const [phase, setPhase] = useState<T>(reduced ? fallback : steps[0][0]);
    useEffect(() => {
        if (reduced) return;
        let idx = 0;
        let timer: ReturnType<typeof setTimeout>;
        const next = () => {
            idx = (idx + 1) % steps.length;
            setPhase(steps[idx][0]);
            timer = setTimeout(next, steps[idx][1]);
        };
        timer = setTimeout(next, steps[0][1]);
        return () => clearTimeout(timer);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [reduced]);
    return phase;
}

/* ------------------------------- Q1: CHART ------------------------------- */
const PRICE_TICKS = [
    { y: 30, label: "43,400" },
    { y: 70, label: "43,300" },
    { y: 110, label: "43,200" },
    { y: 150, label: "43,100" },
];

type ChartPhase = "draw" | "markup" | "signal" | "click" | "filled";
const CHART_CURSOR: Record<ChartPhase, { left: string; top: string }> = {
    draw: { left: "78%", top: "26%" },
    markup: { left: "52%", top: "62%" },
    signal: { left: "30%", top: "68%" },
    click: { left: "24%", top: "82%" },   // on the Execute button
    filled: { left: "60%", top: "40%" },
};

function ChartQuad({ reduced }: { reduced: boolean }) {
    const phase = usePhases<ChartPhase>(
        [["draw", 2400], ["markup", 2400], ["signal", 2200], ["click", 1000], ["filled", 3000]],
        reduced,
        "filled",
    );
    const marked = phase !== "draw";
    const cardUp = phase === "signal" || phase === "click" || phase === "filled";
    const filled = phase === "filled";
    // Key the curve on loop restarts so it redraws each round.
    const [round, setRound] = useState(0);
    useEffect(() => {
        if (phase !== "draw") return;
        // Deferred (not sync-in-effect): re-key the curve so it redraws.
        const t = setTimeout(() => setRound((r) => r + 1), 0);
        return () => clearTimeout(t);
    }, [phase]);

    return (
        <div className="relative h-full">
            <QuadLabel live>chart · BTC/USD</QuadLabel>
            <div className="relative mx-2 h-[calc(100%-30px)]">
                <svg className="absolute inset-0 h-full w-full" viewBox="0 0 300 180" preserveAspectRatio="none">
                    {PRICE_TICKS.map((t) => (
                        <line key={t.y} x1="0" y1={t.y} x2="262" y2={t.y} stroke="var(--border-strong)" strokeWidth="0.5" opacity="0.35" />
                    ))}
                    <motion.path
                        key={`area-${round}`}
                        d="M0,168 Q30,158 60,162 T120,150 T180,120 T240,96 T262,84 V180 H0 Z"
                        fill="var(--accent-400)"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 0.09 }}
                        transition={{ delay: 1.1, duration: 0.8 }}
                    />
                    <motion.path
                        key={`line-${round}`}
                        d="M0,150 Q30,138 60,142 T120,124 T180,100 T240,78 T262,70"
                        fill="none"
                        stroke="var(--accent-500)"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        initial={{ pathLength: reduced ? 1 : 0 }}
                        animate={{ pathLength: 1 }}
                        transition={{ duration: 2.1, ease: "easeInOut" }}
                    />
                    <motion.circle
                        cx="262" cy="70" r="3"
                        fill="var(--accent-500)"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: [0, 1, 0.5, 1] }}
                        transition={{ delay: 2.1, duration: 1.6, repeat: Infinity }}
                    />
                    <AnimatePresence>
                        {marked && (
                            <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.4 }}>
                                <rect x="96" y="118" width="84" height="20" fill="var(--profit)" opacity="0.08" />
                                <line x1="96" y1="118" x2="180" y2="118" stroke="var(--profit)" strokeWidth="1" strokeDasharray="3,3" opacity="0.5" />
                                <line x1="0" y1="84" x2="262" y2="84" stroke="var(--accent-400)" strokeWidth="1" strokeDasharray="4,4" opacity="0.5" />
                            </motion.g>
                        )}
                    </AnimatePresence>
                    {/* Entry marker once filled */}
                    <AnimatePresence>
                        {filled && (
                            <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.35 }}>
                                <line x1="0" y1="70" x2="262" y2="70" stroke="var(--profit)" strokeWidth="1" strokeDasharray="2,3" opacity="0.7" />
                                <circle cx="262" cy="70" r="4.5" fill="var(--profit)" opacity="0.25" />
                            </motion.g>
                        )}
                    </AnimatePresence>
                </svg>

                {/* Priced y-axis */}
                <div className="pointer-events-none absolute inset-y-0 right-0 w-9">
                    {PRICE_TICKS.map((t) => (
                        <span
                            key={t.label}
                            className="num absolute right-0 text-[8px] text-subtle-foreground"
                            style={{ top: `${(t.y / 180) * 100}%`, transform: "translateY(-50%)" }}
                        >
                            {t.label}
                        </span>
                    ))}
                </div>

                <AnimatePresence>
                    {marked && !cardUp && (
                        <motion.div
                            initial={{ opacity: 0, y: 4 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0 }}
                            transition={{ duration: 0.3 }}
                            className="absolute left-[30%] top-[72%] rounded-sm border border-profit/30 bg-background/85 px-1.5 py-0.5 backdrop-blur-sm"
                        >
                            <span className="num text-[8px] text-profit">demand zone</span>
                        </motion.div>
                    )}
                </AnimatePresence>
                <AnimatePresence>
                    {marked && (
                        <motion.div
                            initial={{ opacity: 0, y: 4 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0 }}
                            transition={{ delay: 0.2, duration: 0.3 }}
                            className="absolute right-[16%] top-[30%] rounded-sm border border-accent/30 bg-background/85 px-1.5 py-0.5 backdrop-blur-sm"
                        >
                            <span className="num text-[8px] text-accent-300">liquidity sweep</span>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* Mini setup card with the clickable Execute */}
                <AnimatePresence>
                    {cardUp && (
                        <motion.div
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: 8 }}
                            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                            className="absolute bottom-1 left-1 w-36 rounded-md border border-border bg-background/95 p-1.5 backdrop-blur-sm"
                        >
                            <div className="mb-1 flex items-center justify-between">
                                <span className="text-[9px] font-semibold text-foreground">
                                    LONG <span className="num text-subtle-foreground">@ 43,284</span>
                                </span>
                                <span className="num text-[8px] text-muted-foreground">R:R 2.4</span>
                            </div>
                            <motion.div
                                animate={phase === "click" ? { scale: [1, 0.93, 1] } : { scale: 1 }}
                                transition={{ duration: 0.3 }}
                                className={`relative flex h-[18px] items-center justify-center gap-1 rounded text-[8px] font-medium ${
                                    filled
                                        ? "border border-profit/30 bg-profit/10 text-profit"
                                        : "bg-primary text-primary-foreground"
                                }`}
                            >
                                {filled ? <><Check className="size-2.5" /> Filled</> : <><Zap className="size-2.5" /> Execute</>}
                                {/* click ripple */}
                                {phase === "click" && (
                                    <motion.span
                                        initial={{ opacity: 0.5, scale: 0.4 }}
                                        animate={{ opacity: 0, scale: 1.6 }}
                                        transition={{ duration: 0.5 }}
                                        className="absolute inset-0 rounded bg-accent/30"
                                    />
                                )}
                            </motion.div>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* Scripted cursor */}
                {!reduced && (
                    <motion.div
                        animate={CHART_CURSOR[phase]}
                        transition={{ type: "spring", stiffness: 110, damping: 16 }}
                        className="pointer-events-none absolute z-20"
                        style={CHART_CURSOR.draw}
                    >
                        <MousePointer2 className="size-3 fill-foreground text-foreground drop-shadow" />
                    </motion.div>
                )}
            </div>
        </div>
    );
}

/* ------------------------------- Q2: TRADE ------------------------------- */
type TradePhase = "checks" | "ready" | "executing" | "filled" | "pnl" | "tp";

const GATE_CHECKS = [
    "position size 1.8% ≤ 2% max",
    "portfolio heat 3.1% ≤ 6%",
    "daily loss 0.4% ≤ 5% limit",
];

function TradeQuad({ reduced }: { reduced: boolean }) {
    const phase = usePhases<TradePhase>(
        [["checks", 2600], ["ready", 1400], ["executing", 1200], ["filled", 2200], ["pnl", 2600], ["tp", 3000]],
        reduced,
        "pnl",
    );
    const gateDone = phase !== "checks";
    const filledOn = phase === "filled" || phase === "pnl" || phase === "tp";

    return (
        <div className="relative h-full">
            <QuadLabel live>trade execution</QuadLabel>
            <div className="mx-3 mt-0.5 space-y-1.5">
                {/* Risk-gate checklist */}
                <div className="rounded-md border border-border bg-background/40 px-2 py-1.5">
                    <div className="mb-1 flex items-center gap-1">
                        <ShieldCheck className="size-2.5 text-accent-300" />
                        <span className="num text-[8px] uppercase tracking-wider text-subtle-foreground">risk gate</span>
                    </div>
                    {GATE_CHECKS.map((c, i) => (
                        <motion.div
                            key={`${phase === "checks" ? "run" : "done"}-${i}`}
                            initial={{ opacity: reduced ? 1 : 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: reduced || gateDone ? 0 : 0.3 + i * 0.6 }}
                            className="flex items-center justify-between py-px"
                        >
                            <span className="num text-[8.5px] text-muted-foreground">{c}</span>
                            <Check className="size-2.5 text-profit" />
                        </motion.div>
                    ))}
                </div>

                {/* Order state */}
                <motion.div
                    animate={phase === "executing" ? { scale: [1, 0.97, 1] } : { scale: 1 }}
                    transition={{ duration: 0.3 }}
                    className={`flex h-[22px] items-center justify-center gap-1 rounded-md text-[9px] font-medium ${
                        filledOn
                            ? "border border-profit/30 bg-profit/10 text-profit"
                            : phase === "executing"
                                ? "bg-primary/80 text-primary-foreground"
                                : "bg-primary text-primary-foreground"
                    }`}
                >
                    {filledOn ? (
                        <><Check className="size-2.5" /> Filled · bracket live</>
                    ) : phase === "executing" ? (
                        <><Zap className="size-2.5" /> Executing…</>
                    ) : (
                        <><Zap className="size-2.5" /> {gateDone ? "Execute" : "Awaiting gate…"}</>
                    )}
                </motion.div>

                {/* P&L ticking, then TP1 hit */}
                <AnimatePresence mode="wait">
                    {(phase === "pnl" || phase === "tp") && (
                        <motion.div
                            key="pnlrow"
                            initial={{ opacity: 0, y: 5 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0 }}
                            className="flex items-center justify-between rounded-md border border-profit/25 bg-profit/10 px-2 py-1"
                        >
                            <span className="num text-[9px] text-profit">open P&L</span>
                            <AnimatePresence mode="wait">
                                <motion.span
                                    key={phase === "tp" ? "b" : "a"}
                                    initial={{ opacity: 0, y: 3 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, y: -3 }}
                                    transition={{ duration: 0.25 }}
                                    className="num text-[10px] font-medium text-profit"
                                >
                                    {phase === "tp" ? "+$205.00" : "+$118.40"}
                                </motion.span>
                            </AnimatePresence>
                        </motion.div>
                    )}
                </AnimatePresence>
                <AnimatePresence>
                    {phase === "tp" && (
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0 }}
                            transition={{ duration: 0.3 }}
                            className="flex items-center justify-center gap-1 rounded-md border border-profit/40 bg-profit/15 px-2 py-1"
                        >
                            <Check className="size-2.5 text-profit" />
                            <span className="num text-[9px] font-medium text-profit">TP1 hit · partial profits locked</span>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
}

/* ------------------------------ Q3: AGENTS ------------------------------- */
const AGENT_FEED = [
    { agent: "data", msg: "500 candles synced · 5 TFs" },
    { agent: "analysis", msg: "HTF bias bullish · sweep 43,050" },
    { agent: "memory", msg: "regime trending · 3 episodes" },
    { agent: "strategy", msg: "long drafted · R:R 2.4" },
    { agent: "risk", msg: "sizing 1.8% · approved" },
    { agent: "execution", msg: "bracket placed · entry 43,284" },
];

function AgentsQuad({ reduced }: { reduced: boolean }) {
    const [round, setRound] = useState(0);
    const [done, setDone] = useState(reduced);

    useEffect(() => {
        if (reduced) return;
        const t0 = setTimeout(() => setDone(false), 0); // deferred reset per round
        const t1 = setTimeout(() => setDone(true), 4600);
        const t2 = setTimeout(() => setRound((r) => r + 1), 11200);
        return () => { clearTimeout(t0); clearTimeout(t1); clearTimeout(t2); };
    }, [reduced, round]);

    return (
        <div className="relative h-full">
            <QuadLabel live>agent activity</QuadLabel>
            <div className="mx-3 divide-y divide-border/60">
                {AGENT_FEED.map((row, i) => (
                    <motion.div
                        key={`${round}-${row.agent}`}
                        initial={{ opacity: reduced ? 1 : 0, x: reduced ? 0 : -6 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: reduced ? 0 : 0.3 + i * 0.6, duration: 0.3 }}
                        className="flex items-baseline gap-2 py-[4px]"
                    >
                        <span className="num w-14 shrink-0 text-[9px] text-accent-300">{row.agent}</span>
                        <span className="min-w-0 flex-1 truncate text-[10px] text-muted-foreground">{row.msg}</span>
                        <motion.span
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: reduced ? 0 : 0.55 + i * 0.6 }}
                            className={`num shrink-0 text-[8px] uppercase tracking-wider ${
                                row.agent === "execution" ? "text-profit" : "text-subtle-foreground"
                            }`}
                        >
                            {row.agent === "execution" ? "live" : "ok"}
                        </motion.span>
                    </motion.div>
                ))}
            </div>
            <AnimatePresence>
                {done && (
                    <motion.div
                        initial={{ opacity: 0, y: 5 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.35 }}
                        className="mx-3 mt-1.5 flex items-center justify-center rounded-md border border-accent/25 bg-accent-muted/40 px-2 py-[3px]"
                    >
                        <span className="num text-[8.5px] text-accent-300">cycle complete · 1 setup published · next in 10m</span>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}

/* ----------------------------- Q4: PORTFOLIO ----------------------------- */
type PortPhase = "draw" | "positions" | "uptick" | "closed";

function PortfolioQuad({ reduced }: { reduced: boolean }) {
    const phase = usePhases<PortPhase>(
        [["draw", 2400], ["positions", 2400], ["uptick", 3000], ["closed", 3400]],
        reduced,
        "uptick",
    );
    const [round, setRound] = useState(0);
    useEffect(() => {
        if (phase !== "draw") return;
        // Deferred (not sync-in-effect): re-key the curve so it redraws.
        const t = setTimeout(() => setRound((r) => r + 1), 0);
        return () => clearTimeout(t);
    }, [phase]);
    const upticked = phase === "uptick" || phase === "closed";

    return (
        <div className="relative h-full">
            <QuadLabel live>portfolio · paper</QuadLabel>
            <div className="mx-3 mt-0.5 space-y-1.5">
                <div className="flex items-baseline justify-between">
                    <AnimatePresence mode="wait">
                        <motion.span
                            key={upticked ? "v2" : "v1"}
                            initial={{ opacity: 0, y: 3 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -3 }}
                            transition={{ duration: 0.25 }}
                            className="num text-sm font-semibold text-foreground"
                        >
                            {upticked ? "$12,479.30" : "$12,450.80"}
                        </motion.span>
                    </AnimatePresence>
                    <span className="num text-[10px] font-medium text-profit">
                        {upticked ? "+$188.00 · 69% win" : "+$159.50 · 68% win"}
                    </span>
                </div>

                <div className="relative h-9 overflow-hidden rounded-md border border-border bg-background/40">
                    <svg className="absolute inset-0 h-full w-full" viewBox="0 0 280 36" preserveAspectRatio="none">
                        <motion.path
                            key={round}
                            d="M0,29 L28,26 L56,27 L84,22 L112,23 L140,18 L168,20 L196,13 L224,15 L252,9 L280,6"
                            fill="none"
                            stroke="var(--profit)"
                            strokeWidth="1.4"
                            initial={{ pathLength: reduced ? 1 : 0 }}
                            animate={{ pathLength: 1 }}
                            transition={{ duration: 1.9, ease: "easeInOut" }}
                        />
                    </svg>
                </div>

                <div className="divide-y divide-border/60">
                    <motion.div
                        animate={phase === "uptick" ? { backgroundColor: ["rgba(16,185,129,0.14)", "rgba(16,185,129,0)"] } : {}}
                        transition={{ duration: 1.2 }}
                        className="flex items-center justify-between rounded-sm px-0.5 py-[4.5px]"
                    >
                        <div className="flex items-center gap-1.5">
                            <span className="text-[10px] font-semibold text-foreground">BTCUSDT</span>
                            <span className="rounded-sm border border-profit/30 bg-profit/10 px-1 py-px text-[7px] font-medium uppercase tracking-wider text-profit">LONG</span>
                        </div>
                        <span className="num text-[10px] font-medium text-profit">{upticked ? "+$146.90" : "+$118.40"}</span>
                    </motion.div>
                    <div className="flex items-center justify-between px-0.5 py-[4.5px]">
                        <div className="flex items-center gap-1.5">
                            <span className="text-[10px] font-semibold text-foreground">XAUTUSDT</span>
                            <span className="rounded-sm border border-loss/30 bg-loss/10 px-1 py-px text-[7px] font-medium uppercase tracking-wider text-loss">SHORT</span>
                        </div>
                        <span className="num text-[10px] font-medium text-loss">-$23.10</span>
                    </div>
                </div>

                <AnimatePresence>
                    {phase === "closed" && (
                        <motion.div
                            initial={{ opacity: 0, y: 5 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0 }}
                            transition={{ duration: 0.3 }}
                            className="flex items-center justify-between rounded-md border border-profit/25 bg-profit/10 px-2 py-[3px]"
                        >
                            <span className="num text-[8.5px] text-profit">ETHUSDT closed · take_profit</span>
                            <span className="num text-[9px] font-medium text-profit">+$129.60</span>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
}

/* --------------------------------- Panel --------------------------------- */
/**
 * ghost=true renders the background/ambient variant: translucent cells and
 * softened hairlines so the demo reads as UI living IN the page atmosphere,
 * not a standalone card floating on it.
 */
export function HeroDemo({ ghost = false }: { ghost?: boolean }) {
    const reduced = useReducedMotion() ?? false;

    // Ghost hairlines are nearly invisible — quads separate by spacing, not lines.
    const cell = ghost ? "overflow-hidden bg-surface/25" : "overflow-hidden bg-surface";
    // Ghost order flips the columns: the mask dissolves toward the LEFT, so the
    // richest quads (chart, agents) sit on the fully-visible RIGHT side.
    const quads = ghost
        ? [TradeQuad, ChartQuad, PortfolioQuad, AgentsQuad]
        : [ChartQuad, TradeQuad, AgentsQuad, PortfolioQuad];
    return (
        <div
            className={`grid h-[440px] grid-cols-2 grid-rows-2 md:h-[460px] ${
                ghost ? "gap-3 bg-transparent" : "gap-px bg-border"
            }`}
        >
            {quads.map((Quad, i) => (
                <div key={i} className={cell}><Quad reduced={reduced} /></div>
            ))}
        </div>
    );
}
