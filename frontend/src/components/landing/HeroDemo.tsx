"use client";

import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { MousePointer2, Zap, Check, LineChart, Bot, Wallet } from "lucide-react";
import { useEffect, useState } from "react";

/*
 * HeroDemo — a looping, scripted product tour inside the hero panel (the
 * TradingView-hero idea, but our product): a mini app window with a tab rail
 * the cursor navigates.
 *
 *   Chart      candlesticks stream → agents mark up structure → setup card →
 *              cursor executes → bracket fills
 *   Agents     the multi-agent activity feed, lines arriving live
 *   Portfolio  equity curve + open positions with green/red P&L
 *
 * Pure framer-motion (no video asset). All data is a hand-written mock —
 * deterministic, no randomness at render. Reduced-motion gets a static frame.
 */

type Phase = "chart" | "analyze" | "signal" | "execute" | "filled" | "agents" | "portfolio";

const SCRIPT: [Phase, number][] = [
    ["chart", 2200],
    ["analyze", 2800],
    ["signal", 2400],
    ["execute", 1400],
    ["filled", 2400],
    ["agents", 3800],
    ["portfolio", 4000],
];

// Simulated-cursor waypoints (percent coordinates inside the demo body).
const CURSOR: Record<Phase, { left: string; top: string }> = {
    chart: { left: "80%", top: "30%" },
    analyze: { left: "52%", top: "56%" },
    signal: { left: "30%", top: "72%" },
    execute: { left: "22%", top: "88%" },
    filled: { left: "38%", top: "70%" },
    agents: { left: "47%", top: "6%" },     // on the Agents tab
    portfolio: { left: "63%", top: "6%" },  // on the Portfolio tab
};

// ---- Mock data (deterministic) ------------------------------------------------
// 22 candles, an uptrend with pullbacks. Viewbox 0..400 x 0..180 (y down).
const CANDLES = [
    { o: 132, c: 138, h: 128, l: 142 }, { o: 138, c: 130, h: 126, l: 141 },
    { o: 130, c: 124, h: 120, l: 133 }, { o: 124, c: 129, h: 121, l: 132 },
    { o: 129, c: 118, h: 114, l: 130 }, { o: 118, c: 112, h: 108, l: 121 },
    { o: 112, c: 119, h: 109, l: 122 }, { o: 119, c: 108, h: 104, l: 120 },
    { o: 108, c: 102, h: 97, l: 111 },  { o: 102, c: 109, h: 99, l: 112 },
    { o: 109, c: 98, h: 94, l: 110 },   { o: 98, c: 92, h: 87, l: 101 },
    { o: 92, c: 99, h: 89, l: 103 },    { o: 99, c: 88, h: 84, l: 100 },
    { o: 88, c: 82, h: 77, l: 90 },     { o: 82, c: 88, h: 79, l: 91 },
    { o: 88, c: 78, h: 74, l: 89 },     { o: 78, c: 72, h: 67, l: 80 },
    { o: 72, c: 79, h: 69, l: 82 },     { o: 79, c: 68, h: 64, l: 81 },
    { o: 68, c: 62, h: 57, l: 70 },     { o: 62, c: 56, h: 52, l: 65 },
];

const AGENT_FEED = [
    { t: "12:04:01", agent: "data", msg: "BTCUSDT 500 candles synced · 5 TFs" },
    { t: "12:04:03", agent: "analysis", msg: "HTF bias bullish · sweep of 43,050 lows" },
    { t: "12:04:07", agent: "memory", msg: "regime: trending · 3 similar episodes" },
    { t: "12:04:11", agent: "strategy", msg: "long setup drafted · R:R 2.4" },
    { t: "12:04:12", agent: "risk", msg: "sizing 1.8% · portfolio heat 3.1% · approved" },
    { t: "12:04:13", agent: "execution", msg: "bracket placed · entry 43,284.5" },
];

const POSITIONS = [
    { sym: "BTCUSDT", side: "LONG", pnl: "+$118.40", pct: "+1.9%", up: true },
    { sym: "ETHUSDT", side: "LONG", pnl: "+$64.20", pct: "+4.1%", up: true },
    { sym: "XAUTUSDT", side: "SHORT", pnl: "-$23.10", pct: "-0.8%", up: false },
];

const TABS = [
    { id: "chart", label: "Chart", icon: LineChart },
    { id: "agents", label: "Agents", icon: Bot },
    { id: "portfolio", label: "Portfolio", icon: Wallet },
] as const;

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

    const view: "chart" | "agents" | "portfolio" =
        phase === "agents" ? "agents" : phase === "portfolio" ? "portfolio" : "chart";
    const analyzed = view === "chart" && phase !== "chart";
    const signalUp = phase === "signal" || phase === "execute" || phase === "filled";
    const filled = phase === "filled";

    return (
        <div className="relative">
            {/* Tab rail — the cursor "navigates" between app views */}
            <div className="flex items-center justify-between border-b border-border px-3 py-2">
                <div className="flex gap-1">
                    {TABS.map((t) => {
                        const Icon = t.icon;
                        const active = view === t.id;
                        return (
                            <span
                                key={t.id}
                                className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors duration-150 ${
                                    active ? "bg-elevated text-foreground" : "text-subtle-foreground"
                                }`}
                            >
                                <Icon className={`size-3 ${active ? "text-accent-300" : ""}`} />
                                {t.label}
                            </span>
                        );
                    })}
                </div>
                <AnimatePresence mode="wait">
                    <motion.span
                        key={phase}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="num text-[9px] uppercase tracking-wider text-subtle-foreground"
                    >
                        {phase === "chart" && "streaming live"}
                        {phase === "analyze" && "agents analyzing"}
                        {phase === "signal" && "setup published"}
                        {phase === "execute" && "executing…"}
                        {phase === "filled" && "bracket filled"}
                        {phase === "agents" && "pipeline activity"}
                        {phase === "portfolio" && "paper portfolio"}
                    </motion.span>
                </AnimatePresence>
            </div>

            {/* Demo body */}
            <div className="relative h-[340px] md:h-[380px]">
                <AnimatePresence mode="wait">
                    {/* ---------------- CHART VIEW ---------------- */}
                    {view === "chart" && (
                        <motion.div
                            key="chart"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            transition={{ duration: 0.3 }}
                            className="absolute inset-0"
                        >
                            <div className="flex items-center justify-between px-4 pt-3">
                                <div className="num flex items-center gap-2 text-base font-semibold text-foreground">
                                    $43,284.50
                                    <span className="num text-[11px] font-medium text-profit">+2.4%</span>
                                </div>
                                <div className="flex gap-1">
                                    {["5m", "15m", "1H", "4H"].map((tf, i) => (
                                        <span
                                            key={tf}
                                            className={`num rounded-sm px-1.5 py-0.5 text-[9px] font-medium ${
                                                i === 2
                                                    ? "border border-accent/40 bg-accent/15 text-accent-300"
                                                    : "border border-border text-subtle-foreground"
                                            }`}
                                        >
                                            {tf}
                                        </span>
                                    ))}
                                </div>
                            </div>

                            <div className="relative mx-4 mt-2 h-[calc(100%-64px)]">
                                <svg className="absolute inset-0 h-full w-full" viewBox="0 0 400 180" preserveAspectRatio="none">
                                    {[36, 72, 108, 144].map((y) => (
                                        <line key={y} x1="0" y1={y} x2="400" y2={y} stroke="var(--border-strong)" strokeWidth="0.5" opacity="0.3" />
                                    ))}
                                    {/* Candles stream in left→right */}
                                    {CANDLES.map((k, i) => {
                                        const x = 10 + i * 17.5;
                                        const up = k.c < k.o; // y is inverted
                                        const color = up ? "var(--profit)" : "var(--loss)";
                                        return (
                                            <motion.g
                                                key={i}
                                                initial={{ opacity: 0 }}
                                                animate={{ opacity: 1 }}
                                                transition={{ delay: 0.15 + i * 0.07, duration: 0.25 }}
                                            >
                                                <line x1={x} y1={k.h} x2={x} y2={k.l} stroke={color} strokeWidth="1" opacity="0.7" />
                                                <rect
                                                    x={x - 3.2}
                                                    y={Math.min(k.o, k.c)}
                                                    width={6.4}
                                                    height={Math.max(2, Math.abs(k.c - k.o))}
                                                    fill={color}
                                                    rx={0.8}
                                                />
                                            </motion.g>
                                        );
                                    })}
                                    {/* AI markup */}
                                    <AnimatePresence>
                                        {analyzed && (
                                            <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.45 }}>
                                                <rect x="150" y="96" width="110" height="22" fill="var(--profit)" opacity="0.08" />
                                                <line x1="150" y1="96" x2="260" y2="96" stroke="var(--profit)" strokeWidth="1" strokeDasharray="3,3" opacity="0.5" />
                                                <line x1="0" y1="62" x2="400" y2="62" stroke="var(--accent-400)" strokeWidth="1" strokeDasharray="4,4" opacity="0.55" />
                                            </motion.g>
                                        )}
                                    </AnimatePresence>
                                </svg>

                                {analyzed && (
                                    <>
                                        <motion.div
                                            initial={{ opacity: 0, y: 4 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            transition={{ delay: 0.3, duration: 0.3 }}
                                            className="absolute left-[40%] top-[60%] rounded-sm border border-profit/30 bg-background/85 px-1.5 py-0.5 backdrop-blur-sm"
                                        >
                                            <span className="num text-[9px] text-profit">demand zone</span>
                                        </motion.div>
                                        <motion.div
                                            initial={{ opacity: 0, y: 4 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            transition={{ delay: 0.5, duration: 0.3 }}
                                            className="absolute right-[6%] top-[28%] rounded-sm border border-accent/30 bg-background/85 px-1.5 py-0.5 backdrop-blur-sm"
                                        >
                                            <span className="num text-[9px] text-accent-300">liquidity sweep</span>
                                        </motion.div>
                                    </>
                                )}

                                {/* Setup card → execute → filled */}
                                <AnimatePresence>
                                    {signalUp && (
                                        <motion.div
                                            initial={{ opacity: 0, y: 14 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            exit={{ opacity: 0, y: 10 }}
                                            transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                                            className="absolute bottom-3 left-1 w-56 rounded-lg border border-border bg-background/95 p-3 backdrop-blur-sm"
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
                                            <motion.div
                                                animate={phase === "execute" ? { scale: [1, 0.95, 1] } : { scale: 1 }}
                                                transition={{ duration: 0.3 }}
                                                className={`flex h-6 items-center justify-center gap-1 rounded-md text-[10px] font-medium ${
                                                    filled
                                                        ? "border border-profit/30 bg-profit/10 text-profit"
                                                        : "bg-primary text-primary-foreground"
                                                }`}
                                            >
                                                {filled ? (
                                                    <><Check className="size-3" /> Filled · bracket live</>
                                                ) : (
                                                    <><Zap className="size-3" /> Execute</>
                                                )}
                                            </motion.div>
                                        </motion.div>
                                    )}
                                </AnimatePresence>

                                <AnimatePresence>
                                    {filled && (
                                        <motion.div
                                            initial={{ opacity: 0, y: 6 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            exit={{ opacity: 0 }}
                                            className="absolute right-1 top-1 rounded-md border border-profit/30 bg-profit/10 px-2 py-1"
                                        >
                                            <span className="num text-[10px] font-medium text-profit">open P&L +$118.40</span>
                                        </motion.div>
                                    )}
                                </AnimatePresence>
                            </div>
                        </motion.div>
                    )}

                    {/* ---------------- AGENTS VIEW ---------------- */}
                    {view === "agents" && (
                        <motion.div
                            key="agents"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            transition={{ duration: 0.3 }}
                            className="absolute inset-0 px-4 py-3"
                        >
                            <div className="mb-2 flex items-center gap-2">
                                <span className="size-1.5 animate-pulse-subtle rounded-full bg-accent" />
                                <span className="num text-[10px] uppercase tracking-wider text-subtle-foreground">
                                    live agent activity
                                </span>
                            </div>
                            <div className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-background/40">
                                {AGENT_FEED.map((row, i) => (
                                    <motion.div
                                        key={row.t + row.agent}
                                        initial={{ opacity: 0, x: -8 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        transition={{ delay: 0.15 + i * 0.35, duration: 0.3 }}
                                        className="flex items-baseline gap-2.5 px-3 py-[9px]"
                                    >
                                        <span className="num shrink-0 text-[9px] text-subtle-foreground">{row.t}</span>
                                        <span className="num w-16 shrink-0 text-[11px] text-accent-300">{row.agent}</span>
                                        <span className="min-w-0 flex-1 truncate text-[12px] text-muted-foreground">{row.msg}</span>
                                    </motion.div>
                                ))}
                            </div>
                        </motion.div>
                    )}

                    {/* ---------------- PORTFOLIO VIEW ---------------- */}
                    {view === "portfolio" && (
                        <motion.div
                            key="portfolio"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            transition={{ duration: 0.3 }}
                            className="absolute inset-0 px-4 py-3"
                        >
                            <div className="mb-3 grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-border bg-border">
                                {[
                                    ["Portfolio value", "$12,450.80", "text-foreground"],
                                    ["Total P&L", "+$159.50", "text-profit"],
                                    ["Win rate", "68%", "text-foreground"],
                                ].map(([k, v, cls]) => (
                                    <div key={k} className="bg-surface px-3 py-2.5">
                                        <div className="text-[8px] uppercase tracking-wider text-subtle-foreground">{k}</div>
                                        <motion.div
                                            initial={{ opacity: 0 }}
                                            animate={{ opacity: 1 }}
                                            transition={{ delay: 0.25, duration: 0.4 }}
                                            className={`num mt-0.5 text-sm font-semibold ${cls}`}
                                        >
                                            {v}
                                        </motion.div>
                                    </div>
                                ))}
                            </div>

                            {/* Equity sparkline */}
                            <div className="relative mb-3 h-16 overflow-hidden rounded-lg border border-border bg-background/40">
                                <svg className="absolute inset-0 h-full w-full" viewBox="0 0 400 64" preserveAspectRatio="none">
                                    <motion.path
                                        d="M0,50 L40,46 L80,48 L120,40 L160,42 L200,34 L240,37 L280,26 L320,29 L360,18 L400,14"
                                        fill="none"
                                        stroke="var(--profit)"
                                        strokeWidth="1.5"
                                        initial={{ pathLength: 0 }}
                                        animate={{ pathLength: 1 }}
                                        transition={{ duration: 1.6, ease: "easeInOut" }}
                                    />
                                </svg>
                                <span className="num absolute left-2 top-1.5 text-[8px] uppercase tracking-wider text-subtle-foreground">
                                    equity curve
                                </span>
                            </div>

                            <div className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-background/40">
                                {POSITIONS.map((pos, i) => (
                                    <motion.div
                                        key={pos.sym}
                                        initial={{ opacity: 0, y: 6 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        transition={{ delay: 0.4 + i * 0.18, duration: 0.3 }}
                                        className="flex items-center justify-between px-3 py-2"
                                    >
                                        <div className="flex items-center gap-2">
                                            <span className="text-[12px] font-semibold text-foreground">{pos.sym}</span>
                                            <span
                                                className={`rounded-sm border px-1 py-px text-[8px] font-medium uppercase tracking-wider ${
                                                    pos.side === "LONG"
                                                        ? "border-profit/30 bg-profit/10 text-profit"
                                                        : "border-loss/30 bg-loss/10 text-loss"
                                                }`}
                                            >
                                                {pos.side}
                                            </span>
                                        </div>
                                        <div className="flex items-baseline gap-2">
                                            <span className={`num text-[12px] font-medium ${pos.up ? "text-profit" : "text-loss"}`}>{pos.pnl}</span>
                                            <span className={`num text-[10px] ${pos.up ? "text-profit" : "text-loss"}`}>{pos.pct}</span>
                                        </div>
                                    </motion.div>
                                ))}
                            </div>
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
