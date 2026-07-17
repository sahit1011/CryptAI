"use client";

import { motion, useReducedMotion } from "framer-motion";
import { useId } from "react";

/*
 * EquityCurve — a lightweight SVG area+line of a cumulative realized-P&L series.
 * No chart library: the series is small and we want full control of the crimson
 * house look. The final point is emphasized; the line draws in on mount.
 * Colored by whether the run ends up or down (profit/loss semantics).
 */
export function EquityCurve({
    series,
    height = 120,
    className,
}: {
    series: number[];
    height?: number;
    className?: string;
}) {
    const reduced = useReducedMotion();
    const uid = useId().replace(/:/g, "");

    if (series.length < 2) return null;

    const W = 1000;
    const H = height;
    const pad = 8;
    const min = Math.min(...series);
    const max = Math.max(...series);
    const span = max - min || 1;
    const up = series[series.length - 1] >= series[0];
    const stroke = up ? "var(--profit)" : "var(--loss)";

    const x = (i: number) => (i / (series.length - 1)) * W;
    const y = (v: number) => pad + (1 - (v - min) / span) * (H - pad * 2);

    const linePath = series.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    const areaPath = `${linePath} L${W},${H} L0,${H} Z`;
    // Baseline (zero) if it falls within the visible range.
    const zeroY = min <= 0 && max >= 0 ? y(0) : null;

    return (
        <svg
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="none"
            className={className}
            style={{ width: "100%", height }}
            aria-hidden
        >
            <defs>
                <linearGradient id={`eq-${uid}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={stroke} stopOpacity="0.16" />
                    <stop offset="100%" stopColor={stroke} stopOpacity="0" />
                </linearGradient>
            </defs>

            {zeroY !== null && (
                <line x1="0" y1={zeroY} x2={W} y2={zeroY} stroke="var(--border-strong)" strokeWidth="1" strokeDasharray="4 5" />
            )}

            <motion.path
                d={areaPath}
                fill={`url(#eq-${uid})`}
                initial={{ opacity: 0 }}
                whileInView={{ opacity: 1 }}
                viewport={{ once: true }}
                transition={{ duration: 0.8, delay: 0.3 }}
            />
            <motion.path
                d={linePath}
                fill="none"
                stroke={stroke}
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                initial={{ pathLength: reduced ? 1 : 0 }}
                whileInView={{ pathLength: 1 }}
                viewport={{ once: true }}
                transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1] }}
                vectorEffect="non-scaling-stroke"
            />
            <motion.circle
                cx={x(series.length - 1)}
                cy={y(series[series.length - 1])}
                r="3.5"
                fill={stroke}
                initial={{ opacity: 0 }}
                whileInView={{ opacity: 1 }}
                viewport={{ once: true }}
                transition={{ delay: reduced ? 0 : 1.3 }}
            />
        </svg>
    );
}
