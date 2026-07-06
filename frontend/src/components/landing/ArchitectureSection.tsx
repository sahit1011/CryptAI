"use client";

import { motion } from "framer-motion";
import { Database, Cpu, BrainCircuit, Wallet } from "lucide-react";
import type { CSSProperties, ComponentType } from "react";

/*
 * ArchitectureSection — the multi-agent "swarm" band. Glass panels on
 * bg-background with a crimson aurora/grid atmosphere. To honor the strict
 * red/black identity, the 4 agent cards stay within the crimson accent ramp
 * (accent-300 -> accent-600, a subtle pipeline "deepening" from data to
 * execution) rather than using multiple hues; agents remain distinguishable by
 * icon, title, and status word. Status pills are illustrative descriptors.
 */

type Agent = {
    id: string;
    title: string;
    icon: ComponentType<{ className?: string }>;
    description: string;
    status: string;
    /** Crimson-ramp token that gives this agent its identity. */
    hue: string;
};

const agents: Agent[] = [
    {
        id: "data",
        title: "Data Agent",
        icon: Database,
        description:
            "Streams real-time market data from multiple exchanges over resilient WebSocket connections.",
        status: "Ingesting",
        hue: "var(--accent-300)",
    },
    {
        id: "analysis",
        title: "Analysis Agent",
        icon: BrainCircuit,
        description:
            "Runs technical indicators, sentiment models, and LLM-powered reasoning over incoming signals.",
        status: "Analyzing",
        hue: "var(--accent-400)",
    },
    {
        id: "strategy",
        title: "Strategy Agent",
        icon: Cpu,
        description:
            "Formulates high-probability signals from multi-factor analysis and calibrated risk metrics.",
        status: "Deciding",
        hue: "var(--accent-500)",
    },
    {
        id: "execution",
        title: "Execution Agent",
        icon: Wallet,
        description:
            "Routes orders with optimal execution, slippage protection, and gas-aware settlement.",
        status: "Executing",
        hue: "var(--accent-600)",
    },
];

/** Per-card CSS vars derived from the agent's chart-token hue. */
type AgentStyle = CSSProperties & Record<"--hue", string>;

export function ArchitectureSection() {
    return (
        <section className="relative py-24 md:py-32 overflow-hidden">
            {/* Crimson atmosphere — reuse foundation utilities, no per-section hex. */}
            <div className="aurora -z-10" aria-hidden>
                <div className="grid-perspective" />
            </div>

            <div className="container relative z-10 mx-auto max-w-6xl px-4 md:px-6">
                <div className="mx-auto mb-16 max-w-2xl text-center">
                    <motion.span
                        initial={{ opacity: 0, y: 24 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: "-80px" }}
                        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                        className="inline-flex items-center gap-2 rounded-full glass-panel px-3 py-1 label-md text-accent-300"
                    >
                        <span className="flex h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
                        Multi-Agent Architecture
                    </motion.span>
                    <motion.h2
                        initial={{ opacity: 0, y: 24 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: "-80px" }}
                        transition={{ duration: 0.5, delay: 0.08, ease: [0.16, 1, 0.3, 1] }}
                        className="display-3 mt-4 text-balance"
                    >
                        Swarm intelligence architecture
                    </motion.h2>
                    <motion.p
                        initial={{ opacity: 0, y: 24 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: "-80px" }}
                        transition={{ duration: 0.5, delay: 0.16, ease: [0.16, 1, 0.3, 1] }}
                        className="body-md text-muted-foreground mt-4 text-pretty"
                    >
                        Modeled on an institutional trading desk: specialized agents pass
                        work to one another asynchronously, turning raw market data into
                        precise, risk-aware execution.
                    </motion.p>
                </div>

                <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
                    {agents.map((agent, i) => {
                        const style: AgentStyle = { "--hue": agent.hue };
                        return (
                            <motion.div
                                key={agent.id}
                                initial={{ opacity: 0, y: 24 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true, margin: "-80px" }}
                                transition={{
                                    duration: 0.5,
                                    delay: i * 0.08,
                                    ease: [0.16, 1, 0.3, 1],
                                }}
                                style={style}
                                className="group glass-panel glass-panel-hover flex h-full flex-col p-6"
                            >
                                <div className="mb-5 flex items-start justify-between">
                                    {/* Identity chip — tinted with the agent's chart hue. */}
                                    <span
                                        className="inline-flex h-11 w-11 items-center justify-center rounded-md border transition-transform duration-300 group-hover:scale-110"
                                        style={{
                                            backgroundColor:
                                                "color-mix(in oklch, var(--hue) 14%, transparent)",
                                            borderColor:
                                                "color-mix(in oklch, var(--hue) 32%, transparent)",
                                            color: "var(--hue)",
                                        }}
                                    >
                                        <agent.icon className="h-5 w-5" />
                                    </span>

                                    {/* Status pill — illustrative descriptor, not live data. */}
                                    <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background/40 px-2 py-0.5 text-[10px] font-medium text-subtle-foreground backdrop-blur-sm">
                                        <span
                                            className="h-1 w-1 rounded-full"
                                            style={{ backgroundColor: "var(--hue)" }}
                                        />
                                        {agent.status}
                                    </span>
                                </div>

                                <h3 className="heading-4 mb-2">{agent.title}</h3>
                                <p className="body-sm">{agent.description}</p>

                                {/* Hairline "index" footer — mono numeral, terminal feel. */}
                                <div className="mt-5 flex items-center gap-2 border-t border-border pt-3">
                                    <span
                                        className="num text-xs font-semibold"
                                        style={{ color: "var(--hue)" }}
                                    >
                                        {String(i + 1).padStart(2, "0")}
                                    </span>
                                    <span className="body-xs uppercase tracking-wider">
                                        Agent
                                    </span>
                                </div>
                            </motion.div>
                        );
                    })}
                </div>
            </div>
        </section>
    );
}
