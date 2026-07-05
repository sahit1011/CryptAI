"use client";

import { motion, useInView } from "framer-motion";
import { useRef, useState, useEffect } from "react";
import { cn } from "@/lib/utils";

const stats = [
    { label: "Total Volume Traded", value: "$2.4B+", color: "text-white", glow: "shadow-indigo-500/20" },
    { label: "Active Agents", value: "12,450", color: "text-indigo-300", glow: "shadow-indigo-500/20" },
    { label: "Uptime", value: "99.99%", color: "text-emerald-300", glow: "shadow-emerald-500/20" },
    { label: "Avg. Execution Speed", value: "<50ms", color: "text-purple-300", glow: "shadow-purple-500/20" },
];

const ScrambleText = ({ children, className, delay = 0 }: { children: string, className?: string, delay?: number }) => {
    const ref = useRef(null);
    const isInView = useInView(ref, { once: true, margin: "-50px" });
    const [text, setText] = useState(children);
    const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()";

    useEffect(() => {
        if (!isInView) return;

        const timeout = setTimeout(() => {
            let iteration = 0;
            const interval = setInterval(() => {
                setText(
                    children
                        .split("")
                        .map((letter, index) => {
                            if (index < iteration) {
                                return children[index];
                            }
                            return chars[Math.floor(Math.random() * chars.length)];
                        })
                        .join("")
                );

                if (iteration >= children.length) {
                    clearInterval(interval);
                }

                iteration += 1 / 3;
            }, 30);

            return () => clearInterval(interval);
        }, delay * 1000);

        return () => clearTimeout(timeout);
    }, [isInView, children, delay]);

    return (
        <span ref={ref} className={cn("inline-block tabular-nums", className)}>
            {text}
        </span>
    );
};

export function StatsSection() {
    return (
        <section className="py-12 border-b border-white/10 bg-[#0A0A0A] relative overflow-hidden">
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-indigo-900/20 via-[#0A0A0A] to-[#0A0A0A] pointer-events-none" />

            {/* Grid Pattern - Increased opacity */}
            <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808015_1px,transparent_1px),linear-gradient(to_bottom,#80808015_1px,transparent_1px)] bg-[size:24px_24px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_50%,#000_70%,transparent_100%)] pointer-events-none" />

            <div className="container mx-auto px-4 md:px-6 relative z-10">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-0">
                    {stats.map((stat, i) => (
                        <motion.div
                            key={i}
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.5, delay: i * 0.1 }}
                            viewport={{ once: true }}
                            className="flex flex-col items-center justify-center text-center p-6 group relative transition-colors duration-300"
                        >
                            <div className={cn("text-4xl md:text-5xl font-bold mb-3 tracking-tight relative z-10 drop-shadow-sm", stat.color)}>
                                <ScrambleText delay={i * 0.1 + 0.2}>
                                    {stat.value}
                                </ScrambleText>
                            </div>
                            <div className="text-sm text-muted-foreground uppercase tracking-wider font-medium relative z-10 group-hover:text-white transition-colors duration-300">
                                {stat.label}
                            </div>
                        </motion.div>
                    ))}
                </div>
            </div>
        </section>
    );
}
