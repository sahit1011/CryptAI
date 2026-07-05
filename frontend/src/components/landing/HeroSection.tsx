"use client";

import { motion, AnimatePresence, useMotionValue, useSpring, useTransform } from "framer-motion";
import { ArrowRight, Play, CheckCircle2, LayoutDashboard, Bot, LineChart, ScrollText, Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { BackgroundGrid } from "./BackgroundGrid";
import { useState, useEffect } from "react";

const words = ["Crypto Quant System", "Autonomous Agent Swarm", "Algorithmic Trading Engine"];

// Illustrative marketing ticker — clearly a static mockup, not a live feed.
const tickerRows = [
    { symbol: "BTC", price: "43,284.50", change: "+2.41%", up: true },
    { symbol: "ETH", price: "2,318.90", change: "+1.08%", up: true },
    { symbol: "SOL", price: "98.42", change: "-0.74%", up: false },
];

export function HeroSection() {
    const [index, setIndex] = useState(0);

    // Mouse tracking for the 3D tilt on the preview panel.
    const x = useMotionValue(0);
    const y = useMotionValue(0);

    const mouseX = useSpring(x, { stiffness: 150, damping: 15 });
    const mouseY = useSpring(y, { stiffness: 150, damping: 15 });

    function handleMouseMove({ currentTarget, clientX, clientY }: React.MouseEvent) {
        const { left, top, width, height } = currentTarget.getBoundingClientRect();
        const xPct = (clientX - left) / width - 0.5;
        const yPct = (clientY - top) / height - 0.5;
        x.set(xPct);
        y.set(yPct);
    }

    function handleMouseLeave() {
        x.set(0);
        y.set(0);
    }

    const rotateX = useTransform(mouseY, [-0.5, 0.5], [12, -12]);
    const rotateY = useTransform(mouseX, [-0.5, 0.5], [-12, 12]);

    useEffect(() => {
        const interval = setInterval(() => {
            setIndex((prev) => (prev + 1) % words.length);
        }, 5000);
        return () => clearInterval(interval);
    }, []);

    return (
        <section className="relative min-h-screen flex flex-col items-center justify-center pt-24 pb-28 overflow-hidden">
            <BackgroundGrid />

            <div className="container relative z-10 px-4 md:px-6 text-center mt-8">
                {/* Version badge — emerald */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5 }}
                    className="inline-flex items-center gap-2 px-3 py-1 rounded-full glass-panel text-xs font-medium text-accent-300 mb-8"
                >
                    <span className="flex h-2 w-2 rounded-full bg-accent animate-pulse" />
                    v2.0 Now Available
                </motion.div>

                {/* Headline — emerald wordmark + neutral sheen rotating line */}
                <motion.h1
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5, delay: 0.1 }}
                    className="text-4xl md:text-6xl font-bold tracking-tight mb-7 leading-[1.08]"
                >
                    <span className="font-mono tracking-tighter text-gradient-emerald animate-shine bg-[length:200%_auto]">
                        &lt;CryptAI /&gt;
                    </span>
                    <br />
                    <span className="mt-2 inline-flex h-[1.1em] overflow-hidden justify-center items-center">
                        <AnimatePresence mode="wait">
                            <motion.span
                                key={words[index]}
                                initial="hidden"
                                animate="visible"
                                exit="hidden"
                                variants={{
                                    hidden: { opacity: 0 },
                                    visible: {
                                        opacity: 1,
                                        transition: { staggerChildren: 0.05 },
                                    },
                                }}
                                className="text-sheen animate-shine bg-[length:200%_auto] inline-block"
                            >
                                {words[index].split("").map((char, i) => (
                                    <motion.span
                                        key={i}
                                        variants={{
                                            hidden: { opacity: 0 },
                                            visible: { opacity: 1 },
                                        }}
                                    >
                                        {char === " " ? " " : char}
                                    </motion.span>
                                ))}
                            </motion.span>
                        </AnimatePresence>
                    </span>
                </motion.h1>

                <motion.p
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5, delay: 0.2 }}
                    className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto mb-9 leading-relaxed text-pretty"
                >
                    Deploy autonomous trading agents powered by advanced AI models.
                    Backtest strategies, analyze market sentiment, and execute trades with precision.
                </motion.p>

                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5, delay: 0.3 }}
                    className="flex flex-col sm:flex-row items-center justify-center gap-4"
                >
                    <Link href="/dashboard">
                        <Button
                            size="lg"
                            className="h-12 px-8 rounded-full bg-primary text-primary-foreground hover:bg-accent-400 font-medium text-base emerald-glow transition-transform hover:scale-[1.03]"
                        >
                            Start Trading <ArrowRight className="ml-2 w-4 h-4" />
                        </Button>
                    </Link>
                    <Link href="#demo">
                        <Button
                            variant="outline"
                            size="lg"
                            className="h-12 px-8 rounded-full border-border bg-surface/40 backdrop-blur-sm hover:border-border-strong hover:bg-elevated transition-all"
                        >
                            <Play className="mr-2 w-4 h-4 fill-current" /> Watch Demo
                        </Button>
                    </Link>
                </motion.div>

                {/* Illustrative marketing ticker strip */}
                <motion.div
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, delay: 0.45 }}
                    className="mt-10 mx-auto max-w-xl glass-panel px-4 py-2.5 flex items-center justify-center gap-6 flex-wrap"
                >
                    {tickerRows.map((row) => (
                        <div key={row.symbol} className="flex items-center gap-2 text-sm">
                            <span className="font-semibold text-foreground">{row.symbol}</span>
                            <span className="num text-muted-foreground">${row.price}</span>
                            <span className={`num text-xs ${row.up ? "text-profit" : "text-loss"}`}>
                                {row.change}
                            </span>
                        </div>
                    ))}
                    <span className="text-[9px] uppercase tracking-wider text-subtle-foreground border-l border-border pl-3">
                        Illustrative
                    </span>
                </motion.div>

                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 1, delay: 0.6 }}
                    className="mt-8 flex items-center justify-center gap-8 text-sm text-muted-foreground flex-wrap"
                >
                    {["Non-custodial", "Testnet-first", "Real-time execution"].map((label) => (
                        <div key={label} className="flex items-center gap-2">
                            <CheckCircle2 className="w-4 h-4 text-accent" />
                            <span>{label}</span>
                        </div>
                    ))}
                </motion.div>
            </div>

            {/* 3D Dashboard Preview Panel — Linear-inspired, fully emerald */}
            <motion.div
                initial={{ opacity: 0, y: 90 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 1.2, delay: 0.4, type: "spring", stiffness: 50 }}
                className="mt-20 relative z-10 w-[min(56rem,92vw)] mx-auto"
                style={{ perspective: "1200px" }}
                onMouseMove={handleMouseMove}
                onMouseLeave={handleMouseLeave}
            >
                <motion.div
                    className="relative rounded-xl border border-border-strong bg-background overflow-hidden shadow-[var(--shadow-elevation-high)]"
                    style={{ rotateX, rotateY }}
                    whileHover={{ scale: 1.02 }}
                    transition={{ duration: 0.1 }}
                >
                    {/* Fake browser header */}
                    <div className="h-10 border-b border-border flex items-center px-4 gap-2 bg-surface/60">
                        <div className="flex gap-2">
                            <div className="w-3 h-3 rounded-full bg-loss/30 border border-loss/60" />
                            <div className="w-3 h-3 rounded-full bg-warning/30 border border-warning/60" />
                            <div className="w-3 h-3 rounded-full bg-profit/30 border border-profit/60" />
                        </div>
                        <div className="ml-4 px-3 py-1 rounded-md bg-background/60 border border-border text-[10px] text-muted-foreground font-mono flex items-center gap-2">
                            <span className="text-accent">▲</span>
                            app.cryptai.com/dashboard
                        </div>
                        {/* Illustrative-preview tag so numbers read as a mockup, not live data. */}
                        <div className="ml-auto px-2 py-0.5 rounded bg-accent/10 border border-accent/25 text-[9px] uppercase tracking-wider text-accent-300">
                            Preview
                        </div>
                    </div>

                    {/* Dashboard mock */}
                    <div className="aspect-[16/9] bg-background p-4 relative">
                        <div className="grid grid-cols-12 gap-3 h-full">
                            {/* Sidebar nav */}
                            <div className="col-span-3 h-full rounded-lg border border-border bg-surface/60 backdrop-blur-sm p-2 flex flex-col gap-1">
                                {[
                                    { icon: LayoutDashboard, label: "Dashboard", active: true },
                                    { icon: Bot, label: "Agents", active: false },
                                    { icon: LineChart, label: "Markets", active: false },
                                    { icon: ScrollText, label: "Logs", active: false },
                                    { icon: Settings, label: "Settings", active: false },
                                ].map((item) => (
                                    <div
                                        key={item.label}
                                        className={`flex items-center gap-2 p-1.5 rounded-md transition-colors ${
                                            item.active
                                                ? "bg-accent/15 text-accent-300 border border-accent/25"
                                                : "text-muted-foreground hover:bg-elevated"
                                        }`}
                                    >
                                        <item.icon className="w-3 h-3" />
                                        <span className="text-[8px] font-medium">{item.label}</span>
                                    </div>
                                ))}

                                <div className="mt-auto pt-2 border-t border-border">
                                    <div className="text-[7px] text-subtle-foreground uppercase tracking-wider mb-1.5 px-1">
                                        Active Agents
                                    </div>
                                    <div className="space-y-1">
                                        {["Data Agent", "Analysis", "Execution"].map((agent) => (
                                            <div key={agent} className="flex items-center gap-1.5 px-1">
                                                <div className="w-1 h-1 rounded-full bg-accent animate-pulse" />
                                                <span className="text-[7px] text-muted-foreground">{agent}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>

                            {/* Content */}
                            <div className="col-span-9 h-full grid grid-rows-3 gap-3">
                                {/* Stat tiles */}
                                <div className="row-span-1 grid grid-cols-3 gap-3">
                                    {[
                                        { label: "Portfolio Value", value: "$124,582", change: "+12.4%" },
                                        { label: "24h P&L", value: "+$4,231", change: "+3.52%" },
                                        { label: "Win Rate", value: "68.4%", change: "14 trades" },
                                    ].map((stat, i) => (
                                        <motion.div
                                            key={stat.label}
                                            initial={{ opacity: 0, y: -16 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            transition={{ delay: 0.7 + i * 0.1 }}
                                            className="rounded-lg border border-border bg-surface/60 backdrop-blur-sm p-3 relative overflow-hidden"
                                        >
                                            <div className="text-[8px] text-muted-foreground uppercase tracking-wider mb-1 font-medium">
                                                {stat.label}
                                            </div>
                                            <div className="num text-sm font-bold text-foreground mb-0.5">
                                                {stat.value}
                                            </div>
                                            <div className="num text-[8px] font-semibold text-profit">
                                                {stat.change}
                                            </div>
                                        </motion.div>
                                    ))}
                                </div>

                                {/* Chart */}
                                <motion.div
                                    initial={{ opacity: 0, scale: 0.95 }}
                                    animate={{ opacity: 1, scale: 1 }}
                                    transition={{ delay: 0.8, duration: 0.5 }}
                                    className="row-span-2 rounded-lg border border-border bg-surface/60 backdrop-blur-sm relative overflow-hidden"
                                >
                                    <div className="absolute top-0 left-0 right-0 p-3 flex items-center justify-between z-10">
                                        <div>
                                            <div className="text-[9px] text-muted-foreground uppercase tracking-wider font-medium">
                                                BTC/USD
                                            </div>
                                            <div className="num text-sm font-bold text-foreground flex items-center gap-2">
                                                $43,284.50
                                                <span className="text-[8px] text-profit font-semibold">+2.4%</span>
                                            </div>
                                        </div>
                                        <div className="flex gap-1">
                                            {["1H", "24H", "7D", "1M"].map((tf, i) => (
                                                <div
                                                    key={tf}
                                                    className={`num text-[7px] px-2 py-1 rounded font-medium transition-all ${
                                                        i === 1
                                                            ? "bg-accent/15 text-accent-300 border border-accent/40 emerald-glow"
                                                            : "text-subtle-foreground border border-border"
                                                    }`}
                                                >
                                                    {tf}
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    <svg
                                        className="absolute inset-0 w-full h-full"
                                        viewBox="0 0 400 200"
                                        preserveAspectRatio="none"
                                    >
                                        <defs>
                                            <linearGradient id="hero-area-gradient" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="0%" stopColor="var(--accent-400)" stopOpacity="0.28" />
                                                <stop offset="100%" stopColor="var(--accent-400)" stopOpacity="0.03" />
                                            </linearGradient>
                                        </defs>

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

                                    {/* OHLC tooltip */}
                                    <motion.div
                                        initial={{ opacity: 0, scale: 0.9 }}
                                        animate={{ opacity: 1, scale: 1 }}
                                        transition={{ delay: 1.5, duration: 0.3 }}
                                        className="absolute pointer-events-none z-20"
                                        style={{ left: "70%", top: "51%", transform: "translate(15px, -15px)" }}
                                    >
                                        <div className="bg-background/90 backdrop-blur-md border border-accent/30 rounded-lg p-2 shadow-[var(--shadow-elevation-mid)]">
                                            <div className="text-[8px] text-accent-300 font-bold mb-1">BTC/USD</div>
                                            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[7px]">
                                                <div className="text-subtle-foreground">Open:</div>
                                                <div className="num text-foreground font-semibold">$43,120.00</div>
                                                <div className="text-subtle-foreground">High:</div>
                                                <div className="num text-profit font-semibold">$43,450.00</div>
                                                <div className="text-subtle-foreground">Low:</div>
                                                <div className="num text-loss font-semibold">$43,050.00</div>
                                                <div className="text-subtle-foreground">Close:</div>
                                                <div className="num text-foreground font-semibold">$43,284.50</div>
                                            </div>
                                        </div>
                                    </motion.div>

                                    {/* Faint horizontal grid lines */}
                                    <div className="absolute inset-0 opacity-10 pointer-events-none">
                                        {[...Array(5)].map((_, i) => (
                                            <div
                                                key={i}
                                                className="absolute left-0 right-0 border-t border-border-strong"
                                                style={{ top: `${(i + 1) * 20}%` }}
                                            />
                                        ))}
                                    </div>
                                </motion.div>
                            </div>
                        </div>
                    </div>
                </motion.div>

                {/* Emerald glow beneath the panel */}
                <div className="absolute -inset-8 bg-accent/15 blur-[120px] -z-10 rounded-full opacity-60" />
            </motion.div>
        </section>
    );
}
