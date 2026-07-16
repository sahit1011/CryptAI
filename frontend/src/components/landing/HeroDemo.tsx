"use client";

import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { Zap, Check } from "lucide-react";
import { useEffect, useState } from "react";

/*
 * HeroDemo — the hero panel as a 2×2 quad of independently-looping scenarios
 * (the TradingView multi-chart hero, in our product's voice):
 *
 *   ┌ chart · BTC/USD          ┬ trade execution        ┐
 *   │ smooth price curve with  │ setup card → execute → │
 *   │ priced y-axis + AI marks │ filled → open P&L      │
 *   ├ agent activity           ┼ portfolio              ┤
 *   │ pipeline rows streaming  │ equity curve + P&L     │
 *   └──────────────────────────┴────────────────────────┘
 *
 * Each quadrant runs its own timer loop (different periods, so the panel never
 * feels synchronized/mechanical). Deterministic mock data; reduced-motion gets
 * static frames.
 */

/** Tiny mono header used by every quadrant. */
function QuadLabel({ children, live }: { children: React.ReactNode; live?: boolean }) {
    return (
        <div className="flex items-center gap-1.5 px-3 pt-2.5 pb-1">
            {live && <span className="size-1 animate-pulse-subtle rounded-full bg-accent" />}
            <span className="num text-[9px] uppercase tracking-wider text-subtle-foreground">{children}</span>
        </div>
    );
}

/* ------------------------------- Q1: CHART ------------------------------- */
const PRICE_TICKS = [
    { y: 30, label: "43,400" },
    { y: 70, label: "43,300" },
    { y: 110, label: "43,200" },
    { y: 150, label: "43,100" },
];

function ChartQuad({ reduced }: { reduced: boolean }) {
    // Loop: draw (0) → markup (1) → hold, then repeat.
    const [cycle, setCycle] = useState(0);
    const [marked, setMarked] = useState(reduced);

    useEffect(() => {
        if (reduced) return;
        let alive = true;
        const run = () => {
            if (!alive) return;
            setMarked(false);
            const t1 = setTimeout(() => alive && setMarked(true), 2600);
            const t2 = setTimeout(() => {
                if (!alive) return;
                setCycle((c) => c + 1);
                run();
            }, 7800);
            return () => { clearTimeout(t1); clearTimeout(t2); };
        };
        const cleanup = run();
        return () => { alive = false; cleanup?.(); };
    }, [reduced]);

    return (
        <div className="relative h-full">
            <QuadLabel live>chart · BTC/USD</QuadLabel>
            <div className="relative mx-2 h-[calc(100%-30px)]">
                <svg className="absolute inset-0 h-full w-full" viewBox="0 0 300 180" preserveAspectRatio="none">
                    {PRICE_TICKS.map((t) => (
                        <line key={t.y} x1="0" y1={t.y} x2="262" y2={t.y} stroke="var(--border-strong)" strokeWidth="0.5" opacity="0.35" />
                    ))}
                    <motion.path
                        key={`area-${cycle}`}
                        d="M0,168 Q30,158 60,162 T120,150 T180,120 T240,96 T262,84 V180 H0 Z"
                        fill="var(--accent-400)"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 0.09 }}
                        transition={{ delay: 1.2, duration: 0.8 }}
                    />
                    <motion.path
                        key={`line-${cycle}`}
                        d="M0,150 Q30,138 60,142 T120,124 T180,100 T240,78 T262,70"
                        fill="none"
                        stroke="var(--accent-500)"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        initial={{ pathLength: reduced ? 1 : 0 }}
                        animate={{ pathLength: 1 }}
                        transition={{ duration: 2.2, ease: "easeInOut" }}
                    />
                    {/* live endpoint */}
                    <motion.circle
                        cx="262" cy="70" r="3"
                        fill="var(--accent-500)"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: [0, 1, 0.5, 1] }}
                        transition={{ delay: 2.2, duration: 1.6, repeat: Infinity }}
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
                </svg>

                {/* Priced y-axis (HTML so type stays crisp) */}
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
                    {marked && (
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
                            className="absolute right-[16%] top-[34%] rounded-sm border border-accent/30 bg-background/85 px-1.5 py-0.5 backdrop-blur-sm"
                        >
                            <span className="num text-[8px] text-accent-300">liquidity sweep</span>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
}

/* ------------------------------- Q2: TRADE ------------------------------- */
type TradeStep = "signal" | "execute" | "filled";

function TradeQuad({ reduced }: { reduced: boolean }) {
    const [step, setStep] = useState<TradeStep>(reduced ? "filled" : "signal");
    const [round, setRound] = useState(0);

    useEffect(() => {
        if (reduced) return;
        const timers = [
            setTimeout(() => setStep("execute"), 2800),
            setTimeout(() => setStep("filled"), 4200),
            setTimeout(() => { setStep("signal"); setRound((r) => r + 1); }, 8600),
        ];
        return () => timers.forEach(clearTimeout);
    }, [reduced, round]);

    const filled = step === "filled";

    return (
        <div className="relative h-full">
            <QuadLabel live>trade execution</QuadLabel>
            <motion.div
                key={round}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                className="mx-3 mt-1 rounded-lg border border-border bg-background/50 p-2.5"
            >
                <div className="mb-1.5 flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                        <span className="text-[11px] font-semibold text-foreground">BTCUSDT</span>
                        <span className="rounded-sm border border-profit/30 bg-profit/10 px-1 py-px text-[7px] font-medium uppercase tracking-wider text-profit">
                            Long
                        </span>
                    </div>
                    <span className="num text-[8px] text-muted-foreground">conf 74%</span>
                </div>
                <div className="mb-2 grid grid-cols-3 gap-px overflow-hidden rounded-sm border border-border bg-border text-center">
                    {[["Entry", "43,284"], ["Stop", "42,950"], ["Target", "44,090"]].map(([k, v]) => (
                        <div key={k} className="bg-surface px-1 py-[3px]">
                            <div className="text-[6px] uppercase tracking-wider text-subtle-foreground">{k}</div>
                            <div className="num text-[9px] text-foreground">{v}</div>
                        </div>
                    ))}
                </div>
                <motion.div
                    animate={step === "execute" ? { scale: [1, 0.95, 1] } : { scale: 1 }}
                    transition={{ duration: 0.3 }}
                    className={`flex h-5 items-center justify-center gap-1 rounded-md text-[9px] font-medium ${
                        filled
                            ? "border border-profit/30 bg-profit/10 text-profit"
                            : "bg-primary text-primary-foreground"
                    }`}
                >
                    {filled ? (
                        <><Check className="size-2.5" /> Filled · bracket live</>
                    ) : step === "execute" ? (
                        <><Zap className="size-2.5" /> Executing…</>
                    ) : (
                        <><Zap className="size-2.5" /> Execute</>
                    )}
                </motion.div>
            </motion.div>

            <AnimatePresence>
                {filled && (
                    <motion.div
                        initial={{ opacity: 0, y: 5 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.3 }}
                        className="mx-3 mt-2 flex items-center justify-between rounded-md border border-profit/25 bg-profit/10 px-2 py-1"
                    >
                        <span className="num text-[9px] text-profit">open P&L</span>
                        <span className="num text-[10px] font-medium text-profit">+$118.40</span>
                    </motion.div>
                )}
            </AnimatePresence>
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
];

function AgentsQuad({ reduced }: { reduced: boolean }) {
    const [round, setRound] = useState(0);

    useEffect(() => {
        if (reduced) return;
        const t = setTimeout(() => setRound((r) => r + 1), 9400);
        return () => clearTimeout(t);
    }, [reduced, round]);

    return (
        <div className="relative h-full">
            <QuadLabel live>agent activity</QuadLabel>
            <div className="mx-3 mt-0.5 divide-y divide-border/60">
                {AGENT_FEED.map((row, i) => (
                    <motion.div
                        key={`${round}-${row.agent}`}
                        initial={{ opacity: reduced ? 1 : 0, x: reduced ? 0 : -6 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: reduced ? 0 : 0.3 + i * 0.55, duration: 0.3 }}
                        className="flex items-baseline gap-2 py-[5.5px]"
                    >
                        <span className="num w-14 shrink-0 text-[9px] text-accent-300">{row.agent}</span>
                        <span className="min-w-0 flex-1 truncate text-[10px] text-muted-foreground">{row.msg}</span>
                        <motion.span
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: reduced ? 0 : 0.55 + i * 0.55 }}
                            className="num shrink-0 text-[8px] uppercase tracking-wider text-subtle-foreground"
                        >
                            ok
                        </motion.span>
                    </motion.div>
                ))}
            </div>
        </div>
    );
}

/* ----------------------------- Q4: PORTFOLIO ----------------------------- */
const POSITIONS = [
    { sym: "BTCUSDT", side: "LONG", pnl: "+$118.40", up: true },
    { sym: "XAUTUSDT", side: "SHORT", pnl: "-$23.10", up: false },
];

function PortfolioQuad({ reduced }: { reduced: boolean }) {
    const [round, setRound] = useState(0);

    useEffect(() => {
        if (reduced) return;
        const t = setTimeout(() => setRound((r) => r + 1), 8200);
        return () => clearTimeout(t);
    }, [reduced, round]);

    return (
        <div className="relative h-full">
            <QuadLabel live>portfolio · paper</QuadLabel>
            <div className="mx-3 mt-0.5 space-y-2">
                <div className="flex items-baseline justify-between">
                    <span className="num text-sm font-semibold text-foreground">$12,450.80</span>
                    <span className="num text-[10px] font-medium text-profit">+$159.50 · 68% win</span>
                </div>

                <div className="relative h-10 overflow-hidden rounded-md border border-border bg-background/40">
                    <svg className="absolute inset-0 h-full w-full" viewBox="0 0 280 40" preserveAspectRatio="none">
                        <motion.path
                            key={round}
                            d="M0,32 L28,29 L56,30 L84,25 L112,26 L140,20 L168,22 L196,15 L224,17 L252,10 L280,7"
                            fill="none"
                            stroke="var(--profit)"
                            strokeWidth="1.4"
                            initial={{ pathLength: reduced ? 1 : 0 }}
                            animate={{ pathLength: 1 }}
                            transition={{ duration: 2, ease: "easeInOut" }}
                        />
                    </svg>
                </div>

                <div className="divide-y divide-border/60">
                    {POSITIONS.map((pos, i) => (
                        <motion.div
                            key={`${round}-${pos.sym}`}
                            initial={{ opacity: reduced ? 1 : 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: reduced ? 0 : 1.2 + i * 0.4 }}
                            className="flex items-center justify-between py-1.5"
                        >
                            <div className="flex items-center gap-1.5">
                                <span className="text-[10px] font-semibold text-foreground">{pos.sym}</span>
                                <span
                                    className={`rounded-sm border px-1 py-px text-[7px] font-medium uppercase tracking-wider ${
                                        pos.side === "LONG"
                                            ? "border-profit/30 bg-profit/10 text-profit"
                                            : "border-loss/30 bg-loss/10 text-loss"
                                    }`}
                                >
                                    {pos.side}
                                </span>
                            </div>
                            <span className={`num text-[10px] font-medium ${pos.up ? "text-profit" : "text-loss"}`}>
                                {pos.pnl}
                            </span>
                        </motion.div>
                    ))}
                </div>
            </div>
        </div>
    );
}

/* --------------------------------- Panel --------------------------------- */
export function HeroDemo() {
    const reduced = useReducedMotion() ?? false;

    return (
        <div className="grid h-[420px] grid-cols-2 grid-rows-2 gap-px bg-border md:h-[440px]">
            <div className="bg-surface"><ChartQuad reduced={reduced} /></div>
            <div className="bg-surface"><TradeQuad reduced={reduced} /></div>
            <div className="bg-surface"><AgentsQuad reduced={reduced} /></div>
            <div className="bg-surface"><PortfolioQuad reduced={reduced} /></div>
        </div>
    );
}
