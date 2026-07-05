"use client";

import { motion } from "framer-motion";
import { Bot, LineChart, ShieldCheck, Zap } from "lucide-react";

/*
 * FeaturesSection — concise "why CryptAI" band. Emerald icon chips + glass
 * panels on bg-background. Copy is product-forward and honest (no fake social
 * proof). A section agent may expand this; keep the emerald token conventions.
 */

const features = [
    {
        icon: Bot,
        title: "Autonomous agents",
        body: "A swarm of specialized agents handles data, analysis, and execution so strategies run without babysitting.",
    },
    {
        icon: LineChart,
        title: "Backtest with confidence",
        body: "Validate strategies against historical markets before a single live order is placed.",
    },
    {
        icon: Zap,
        title: "Real-time execution",
        body: "Live market data streams into the engine and turns signals into orders in milliseconds.",
    },
    {
        icon: ShieldCheck,
        title: "Testnet-first & non-custodial",
        body: "Start safely on testnet and keep control of your keys — CryptAI never takes custody of funds.",
    },
];

export function FeaturesSection() {
    return (
        <section className="relative py-24 md:py-32">
            <div className="container relative z-10 px-4 md:px-6 mx-auto max-w-6xl">
                <div className="text-center max-w-2xl mx-auto mb-14">
                    <span className="label-md text-accent-300">Why CryptAI</span>
                    <h2 className="display-3 mt-3 text-balance">
                        A quant desk that runs itself
                    </h2>
                    <p className="body-md text-muted-foreground mt-4 text-pretty">
                        Everything you need to research, validate, and deploy algorithmic
                        strategies — in one cohesive terminal.
                    </p>
                </div>

                <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
                    {features.map((feature, i) => (
                        <motion.div
                            key={feature.title}
                            initial={{ opacity: 0, y: 24 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true, margin: "-80px" }}
                            transition={{ duration: 0.5, delay: i * 0.08, ease: [0.16, 1, 0.3, 1] }}
                            className="glass-panel glass-panel-hover p-6"
                        >
                            <span className="chip-emerald w-10 h-10 mb-4">
                                <feature.icon className="w-5 h-5" />
                            </span>
                            <h3 className="heading-4 mb-2">{feature.title}</h3>
                            <p className="body-sm">{feature.body}</p>
                        </motion.div>
                    ))}
                </div>
            </div>
        </section>
    );
}
