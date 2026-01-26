"use client";

import { motion } from "framer-motion";
import { Database, Cpu, BrainCircuit, Wallet } from "lucide-react";

const agents = [
    {
        id: "data",
        title: "Data Agent",
        icon: Database,
        description: "Real-time market data ingestion from multiple exchanges via WebSocket connections.",
        metrics: "1.2k req/s",
        color: "from-blue-500 to-cyan-500",
        iconBg: "bg-blue-500/10",
        border: "border-blue-500/20",
        glow: "group-hover:shadow-[0_0_30px_rgba(59,130,246,0.3)]"
    },
    {
        id: "analysis",
        title: "Analysis Agent",
        icon: BrainCircuit,
        description: "Advanced technical indicators, sentiment analysis, and LLM-powered market insights.",
        metrics: "Processing",
        color: "from-purple-500 to-pink-500",
        iconBg: "bg-purple-500/10",
        border: "border-purple-500/20",
        glow: "group-hover:shadow-[0_0_30px_rgba(168,85,247,0.3)]"
    },
    {
        id: "strategy",
        title: "Strategy Agent",
        icon: Cpu,
        description: "Formulates high-probability trading signals based on multi-factor analysis and risk metrics.",
        metrics: "7 signals",
        color: "from-amber-500 to-orange-500",
        iconBg: "bg-amber-500/10",
        border: "border-amber-500/20",
        glow: "group-hover:shadow-[0_0_30px_rgba(245,158,11,0.3)]"
    },
    {
        id: "execution",
        title: "Execution Agent",
        icon: Wallet,
        description: "Smart order routing with optimal execution, slippage protection, and gas optimization.",
        metrics: "Standby",
        color: "from-emerald-500 to-teal-500",
        iconBg: "bg-emerald-500/10",
        border: "border-emerald-500/20",
        glow: "group-hover:shadow-[0_0_30px_rgba(16,185,129,0.3)]"
    }
];

export function ArchitectureSection() {
    return (
        <section className="py-32 relative overflow-hidden">
            {/* Background Glow */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-indigo-500/5 rounded-full blur-[120px] -z-10" />

            <div className="container mx-auto px-4 md:px-6">
                <div className="text-center max-w-3xl mx-auto mb-20">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5 }}
                        viewport={{ once: true }}
                        className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 border border-white/10 text-xs font-medium text-indigo-300 mb-6 backdrop-blur-sm"
                    >
                        <span className="flex h-2 w-2 rounded-full bg-indigo-500 animate-pulse" />
                        Multi-Agent Architecture
                    </motion.div>
                    <motion.h2
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5, delay: 0.1 }}
                        viewport={{ once: true }}
                        className="text-3xl md:text-5xl font-bold tracking-tight mb-6 bg-clip-text text-transparent bg-[linear-gradient(to_right,white,white,rgba(255,255,255,0.5),white,white)] bg-[length:200%_auto] animate-shine"
                    >
                        Swarm Intelligence Architecture
                    </motion.h2>
                    <motion.p
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5, delay: 0.2 }}
                        viewport={{ once: true }}
                        className="text-lg text-muted-foreground"
                    >
                        Our multi-agent system mimics institutional trading desks. Each specialized agent communicates asynchronously to execute profitable trades with precision.
                    </motion.p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 relative z-10">
                    {agents.map((agent, i) => (
                        <motion.div
                            key={agent.id}
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.5, delay: i * 0.1 }}
                            viewport={{ once: true }}
                            className="group relative"
                        >
                            <div className={`h-full p-6 rounded-xl border ${agent.border} bg-gradient-to-b from-white/[0.07] to-white/[0.02] backdrop-blur-sm hover:from-white/[0.1] hover:to-white/[0.05] transition-all duration-500 ${agent.glow} flex flex-col items-center text-center`}>
                                {/* Icon Container */}
                                <div className="relative mb-6">
                                    <div className={`w-12 h-12 rounded-lg ${agent.iconBg} flex items-center justify-center border ${agent.border} group-hover:scale-110 transition-transform duration-300`}>
                                        <agent.icon className="w-6 h-6 text-white" />
                                    </div>
                                    {/* Status Badge */}
                                    <div className="absolute -top-1 -right-1 px-2 py-0.5 rounded-full bg-black/50 border border-white/10 text-[8px] font-medium text-white/80 backdrop-blur-sm">
                                        {agent.metrics}
                                    </div>
                                </div>

                                {/* Content */}
                                <h3 className={`text-xl font-semibold mb-3 text-white group-hover:text-transparent group-hover:bg-clip-text group-hover:bg-gradient-to-r ${agent.color} transition-all duration-300`}>
                                    {agent.title}
                                </h3>
                                <p className="text-sm text-muted-foreground leading-relaxed">
                                    {agent.description}
                                </p>

                                {/* Gradient Overlay on Hover */}
                                <div className={`absolute inset-0 rounded-xl bg-gradient-to-br ${agent.color} opacity-0 group-hover:opacity-5 transition-opacity duration-500 pointer-events-none`} />
                            </div>
                        </motion.div>
                    ))}
                </div>
            </div>
        </section>
    );
}
