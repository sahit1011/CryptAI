"use client";

import { motion, AnimatePresence, useMotionValue, useSpring, useTransform } from "framer-motion";
import { ArrowRight, Play, CheckCircle2, LayoutDashboard, Bot, LineChart, ScrollText, Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { BackgroundGrid } from "./BackgroundGrid";
import { useState, useEffect } from "react";

const words = ["Crypto Quant System", "Autonomous Agent Swarm", "Algorithmic Trading Engine"];

export function HeroSection() {
    const [index, setIndex] = useState(0);

    // Mouse tracking for 3D tilt effect
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

    const rotateX = useTransform(mouseY, [-0.5, 0.5], [15, -15]);
    const rotateY = useTransform(mouseX, [-0.5, 0.5], [-15, 15]);

    useEffect(() => {
        const interval = setInterval(() => {
            setIndex((prev) => (prev + 1) % words.length);
        }, 5000);
        return () => clearInterval(interval);
    }, []);

    return (
        <section className="relative min-h-screen flex flex-col items-center justify-center pt-20 pb-32 overflow-hidden">
            <BackgroundGrid />

            <div className="container relative z-10 px-4 md:px-6 text-center mt-12">
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5 }}
                    className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 border border-white/10 text-xs font-medium text-indigo-300 mb-8 backdrop-blur-sm"
                >
                    <span className="flex h-2 w-2 rounded-full bg-indigo-500 animate-pulse" />
                    v2.0 Now Available
                </motion.div>

                <motion.h1
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5, delay: 0.1 }}
                    className="text-4xl md:text-6xl font-bold tracking-tight mb-8 leading-[1.1]"
                >
                    <span className="font-mono tracking-tighter text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 via-cyan-400 to-emerald-400 animate-shine bg-[length:200%_auto]">
                        &lt;CryptAI /&gt;
                    </span> <br />
                    <div className="h-[1.1em] overflow-hidden flex justify-center items-center">
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
                                        transition: { staggerChildren: 0.05 }
                                    }
                                }}
                                className="bg-clip-text text-transparent bg-[linear-gradient(to_right,white,white,rgba(255,255,255,0.5),white,white)] bg-[length:200%_auto] animate-shine inline-block"
                            >
                                {words[index].split("").map((char, i) => (
                                    <motion.span
                                        key={i}
                                        variants={{
                                            hidden: { opacity: 0 },
                                            visible: { opacity: 1 }
                                        }}
                                    >
                                        {char}
                                    </motion.span>
                                ))}
                            </motion.span>
                        </AnimatePresence>
                    </div>
                </motion.h1>

                <motion.p
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5, delay: 0.2 }}
                    className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto mb-10 leading-relaxed"
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
                        <Button size="lg" className="h-12 px-8 rounded-full bg-white text-black hover:bg-white/90 font-medium text-base shadow-[0_0_20px_rgba(255,255,255,0.3)] transition-all hover:scale-105">
                            Start Trading <ArrowRight className="ml-2 w-4 h-4" />
                        </Button>
                    </Link>
                    <Link href="#demo">
                        <Button variant="outline" size="lg" className="h-12 px-8 rounded-full border-white/10 bg-white/5 hover:bg-white/10 hover:text-white backdrop-blur-sm transition-all">
                            <Play className="mr-2 w-4 h-4 fill-current" /> Watch Demo
                        </Button>
                    </Link>
                </motion.div>

                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 1, delay: 0.5 }}
                    className="mt-12 flex items-center justify-center gap-8 text-sm text-muted-foreground"
                >
                    <div className="flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                        <span>Non-custodial</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                        <span>99.9% Uptime</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                        <span>Real-time Execution</span>
                    </div>
                </motion.div>
            </div>

            {/* 3D Dashboard Preview Effect - Linear.app Inspired */}
            <motion.div
                initial={{ opacity: 0, y: 100 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 1.2, delay: 0.4, type: "spring", stiffness: 50 }}
                className="mt-20 relative z-10 w-[50vw] max-w-none mx-auto"
                style={{ perspective: "1200px" }}
                onMouseMove={handleMouseMove}
                onMouseLeave={handleMouseLeave}
            >
                <motion.div
                    className="relative rounded-xl border border-white/20 bg-[#0A0A0A] overflow-hidden shadow-[0_20px_50px_rgba(0,0,0,0.5)]"
                    style={{ rotateX, rotateY }}
                    whileHover={{ scale: 1.02 }}
                    transition={{ duration: 0.1 }}
                >

                    {/* Fake Browser Header */}
                    <div className="h-10 border-b border-white/10 flex items-center px-4 gap-2 bg-white/5">
                        <div className="flex gap-2">
                            <div className="w-3 h-3 rounded-full bg-red-500/30 border border-red-500/60" />
                            <div className="w-3 h-3 rounded-full bg-yellow-500/30 border border-yellow-500/60" />
                            <div className="w-3 h-3 rounded-full bg-green-500/30 border border-green-500/60" />
                        </div>
                        <div className="ml-4 px-3 py-1 rounded-md bg-black/40 border border-white/10 text-[10px] text-muted-foreground font-mono flex items-center gap-2">
                            <span className="text-green-400">🔒</span>
                            app.cryptai.com/dashboard
                        </div>
                        {/* Make clear this hero panel is an illustrative product
                            preview, not live data, so the numbers below read as a mockup. */}
                        <div className="ml-auto px-2 py-0.5 rounded bg-white/5 border border-white/10 text-[9px] uppercase tracking-wider text-muted-foreground">
                            Preview
                        </div>
                    </div>

                    {/* Dashboard Mock Preview with Rich Content */}
                    <div className="aspect-[16/9] bg-[#0A0A0A] p-4 relative">
                        {/* Main Dashboard Grid */}
                        <div className="grid grid-cols-12 gap-3 h-full">
                            {/* Left Sidebar - Navigation */}
                            <div className="col-span-3 h-full rounded-lg border border-white/10 bg-gradient-to-b from-white/[0.07] to-white/[0.02] backdrop-blur-sm p-2 flex flex-col gap-1">
                                {[
                                    { icon: LayoutDashboard, label: "Dashboard", active: true },
                                    { icon: Bot, label: "Agents", active: false },
                                    { icon: LineChart, label: "Markets", active: false },
                                    { icon: ScrollText, label: "Logs", active: false },
                                    { icon: Settings, label: "Settings", active: false },
                                ].map((item) => (
                                    <div key={item.label} className={`flex items-center gap-2 p-1.5 rounded-md transition-colors ${item.active ? 'bg-indigo-500/20 text-indigo-300' : 'text-white/60 hover:bg-white/5'}`}>
                                        <item.icon className="w-3 h-3" />
                                        <span className="text-[8px] font-medium">{item.label}</span>
                                    </div>
                                ))}

                                <div className="mt-auto pt-2 border-t border-white/10">
                                    <div className="text-[7px] text-white/40 uppercase tracking-wider mb-1.5 px-1">Active Agents</div>
                                    <div className="space-y-1">
                                        {['Data Agent', 'Analysis', 'Execution'].map((agent) => (
                                            <div key={agent} className="flex items-center gap-1.5 px-1">
                                                <div className="w-1 h-1 rounded-full bg-emerald-500 animate-pulse" />
                                                <span className="text-[7px] text-white/70">{agent}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>

                            {/* Right Content Area */}
                            <div className="col-span-9 h-full grid grid-rows-3 gap-3">
                                {/* Top Stats Row */}
                                <div className="row-span-1 grid grid-cols-3 gap-3">
                                    {[
                                        { label: "Portfolio Value", value: "$124,582", change: "+12.4%", positive: true },
                                        { label: "24h P&L", value: "+$4,231", change: "+3.52%", positive: true },
                                        { label: "Win Rate", value: "68.4%", change: "14 trades", positive: true },
                                    ].map((stat, i) => (
                                        <motion.div
                                            key={stat.label}
                                            initial={{ opacity: 0, y: -20 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            transition={{ delay: 0.7 + i * 0.1 }}
                                            className="rounded-lg border border-white/10 bg-gradient-to-br from-white/[0.08] to-white/[0.02] backdrop-blur-sm p-3 relative overflow-hidden"
                                        >
                                            <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/10 to-purple-500/10 opacity-0" />
                                            <div className="relative">
                                                <div className="text-[8px] text-white/60 uppercase tracking-wider mb-1 font-medium">{stat.label}</div>
                                                <div className="text-sm font-bold text-white mb-0.5">{stat.value}</div>
                                                <div className={`text-[8px] font-semibold ${stat.positive ? 'text-emerald-400' : 'text-white/40'}`}>
                                                    {stat.change}
                                                </div>
                                            </div>
                                        </motion.div>
                                    ))}
                                </div>

                                {/* Main Chart Area */}
                                <motion.div
                                    initial={{ opacity: 0, scale: 0.95 }}
                                    animate={{ opacity: 1, scale: 1 }}
                                    transition={{ delay: 0.8, duration: 0.5 }}
                                    className="row-span-2 rounded-lg border border-white/10 bg-gradient-to-br from-white/[0.08] to-white/[0.02] backdrop-blur-sm relative overflow-hidden"
                                >
                                    {/* Chart Header */}
                                    <div className="absolute top-0 left-0 right-0 p-3 flex items-center justify-between z-10">
                                        <div>
                                            <div className="text-[9px] text-white/60 uppercase tracking-wider font-medium">BTC/USD</div>
                                            <div className="text-sm font-bold text-white flex items-center gap-2">
                                                $43,284.50
                                                <span className="text-[8px] text-emerald-400 font-semibold">+2.4%</span>
                                            </div>
                                        </div>
                                        <div className="flex gap-1">
                                            {['1H', '24H', '7D', '1M'].map((tf, i) => (
                                                <div
                                                    key={tf}
                                                    className={`text-[7px] px-2 py-1 rounded font-medium transition-all ${i === 1
                                                        ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 shadow-[0_0_10px_rgba(99,102,241,0.3)]'
                                                        : 'text-white/50 border border-white/10'
                                                        }`}
                                                >
                                                    {tf}
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Price Line Chart */}
                                    <svg
                                        className="absolute inset-0 w-full h-full"
                                        viewBox="0 0 400 200"
                                        preserveAspectRatio="none"
                                    >
                                        <defs>
                                            <linearGradient id="volume-gradient" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="0%" stopColor="#34d399" stopOpacity="0.3" />
                                                <stop offset="100%" stopColor="#34d399" stopOpacity="0.05" />
                                            </linearGradient>
                                        </defs>

                                        {/* Volume Area (Background) */}
                                        <motion.path
                                            d="M0,190 Q40,180 80,185 T160,180 T240,170 T320,175 T400,160 V200 H0 Z"
                                            fill="url(#volume-gradient)"
                                            initial={{ opacity: 0, scaleY: 0 }}
                                            animate={{ opacity: 1, scaleY: 1 }}
                                            transition={{ delay: 1.2, duration: 1 }}
                                            style={{ transformOrigin: "bottom" }}
                                        />

                                        {/* Price Curve Line - Simple Smooth Curve */}
                                        <motion.path
                                            d="M0,140 Q50,120 100,130 T200,110 T300,100 T400,90"
                                            fill="none"
                                            stroke="#10b981"
                                            strokeWidth="2"
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            initial={{ pathLength: 0, opacity: 0 }}
                                            animate={{ pathLength: 1, opacity: 1 }}
                                            transition={{ delay: 1, duration: 2.5, ease: "easeInOut" }}
                                        />

                                        {/* Crosshair Lines - Static Position */}
                                        {(() => {
                                            const staticX = 280;

                                            // Calculate Y position on curve using Bezier math
                                            const calculateY = (x: number) => {
                                                if (x <= 100) {
                                                    const t = x / 100;
                                                    const p0 = { x: 0, y: 140 };
                                                    const p1 = { x: 50, y: 120 };
                                                    const p2 = { x: 100, y: 130 };
                                                    return (1 - t) * (1 - t) * p0.y + 2 * (1 - t) * t * p1.y + t * t * p2.y;
                                                } else if (x <= 200) {
                                                    const t = (x - 100) / 100;
                                                    const p0 = { x: 100, y: 130 };
                                                    const p1 = { x: 150, y: 140 };
                                                    const p2 = { x: 200, y: 110 };
                                                    return (1 - t) * (1 - t) * p0.y + 2 * (1 - t) * t * p1.y + t * t * p2.y;
                                                } else if (x <= 300) {
                                                    const t = (x - 200) / 100;
                                                    const p0 = { x: 200, y: 110 };
                                                    const p1 = { x: 250, y: 80 };
                                                    const p2 = { x: 300, y: 100 };
                                                    return (1 - t) * (1 - t) * p0.y + 2 * (1 - t) * t * p1.y + t * t * p2.y;
                                                } else {
                                                    const t = (x - 300) / 100;
                                                    const p0 = { x: 300, y: 100 };
                                                    const p1 = { x: 350, y: 120 };
                                                    const p2 = { x: 400, y: 90 };
                                                    return (1 - t) * (1 - t) * p0.y + 2 * (1 - t) * t * p1.y + t * t * p2.y;
                                                }
                                            };

                                            const staticY = calculateY(staticX);

                                            return (
                                                <>
                                                    {/* Vertical Line */}
                                                    <line
                                                        x1={staticX}
                                                        y1="0"
                                                        x2={staticX}
                                                        y2="200"
                                                        stroke="#10b981"
                                                        strokeWidth="1"
                                                        strokeDasharray="4,4"
                                                        opacity="0.8"
                                                    />
                                                    {/* Horizontal Line */}
                                                    <line
                                                        x1="0"
                                                        y1={staticY}
                                                        x2="400"
                                                        y2={staticY}
                                                        stroke="#10b981"
                                                        strokeWidth="1"
                                                        strokeDasharray="4,4"
                                                        opacity="0.8"
                                                    />
                                                    {/* Point on Curve */}
                                                    <circle
                                                        cx={staticX}
                                                        cy={staticY}
                                                        r="5"
                                                        fill="#10b981"
                                                        stroke="#fff"
                                                        strokeWidth="2"
                                                        opacity="1"
                                                    />
                                                    {/* Glow effect on point */}
                                                    <circle
                                                        cx={staticX}
                                                        cy={staticY}
                                                        r="10"
                                                        fill="#10b981"
                                                        opacity="0.3"
                                                    />
                                                </>
                                            );
                                        })()}
                                    </svg>

                                    {/* OHLC Tooltip - Static Position */}
                                    <motion.div
                                        initial={{ opacity: 0, scale: 0.9 }}
                                        animate={{ opacity: 1, scale: 1 }}
                                        transition={{ delay: 1.5, duration: 0.3 }}
                                        className="absolute pointer-events-none z-20"
                                        style={{
                                            left: '70%',
                                            top: '51%',
                                            transform: 'translate(15px, -15px)'
                                        }}
                                    >
                                        <div className="bg-black/90 backdrop-blur-md border border-emerald-500/30 rounded-lg p-2 shadow-lg shadow-emerald-500/20">
                                            <div className="text-[8px] text-emerald-400 font-bold mb-1">BTC/USD</div>
                                            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[7px]">
                                                <div className="text-white/50">Open:</div>
                                                <div className="text-white font-semibold">$43,120.00</div>
                                                <div className="text-white/50">High:</div>
                                                <div className="text-emerald-400 font-semibold">$43,450.00</div>
                                                <div className="text-white/50">Low:</div>
                                                <div className="text-red-400 font-semibold">$43,050.00</div>
                                                <div className="text-white/50">Close:</div>
                                                <div className="text-white font-semibold">$43,284.50</div>
                                            </div>
                                        </div>
                                    </motion.div>

                                    {/* Grid Lines */}
                                    <div className="absolute inset-0 opacity-10 pointer-events-none">
                                        {[...Array(5)].map((_, i) => (
                                            <div
                                                key={i}
                                                className="absolute left-0 right-0 border-t border-white/20"
                                                style={{ top: `${(i + 1) * 20}%` }}
                                            />
                                        ))}
                                    </div>

                                    {/* Hover Glow Effect */}
                                    <div className="absolute inset-0 bg-gradient-to-t from-indigo-500/0 via-indigo-500/0 to-indigo-500/0 transition-all duration-500 pointer-events-none" />
                                </motion.div>
                            </div>
                        </div>
                    </div>
                </motion.div>

                {/* Enhanced Glow Effects - Multi-layer */}
                <div className="absolute -inset-8 bg-indigo-500/20 blur-[120px] -z-10 rounded-full opacity-60" />
                <div className="absolute -inset-12 bg-purple-500/10 blur-[150px] -z-20 rounded-full opacity-40" />
            </motion.div>
        </section >
    );
}
