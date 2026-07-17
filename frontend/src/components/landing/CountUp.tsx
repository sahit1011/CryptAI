"use client";

import { animate, useInView, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

/*
 * CountUp — animates a number from `from` to `to` once it scrolls into view,
 * formatted with thousands grouping + optional prefix/suffix. Used by the
 * pricing ledger (count from the Free baseline up to each tier's limit) and
 * the FAQ receipts (settle the one anchor figure per row).
 *
 * Reduced motion / headless: renders the final value immediately (duration 0),
 * so content is never gated behind the animation.
 */
export function CountUp({
    to,
    from = 0,
    prefix = "",
    suffix = "",
    decimals = 0,
    durationMs = 900,
    delayMs = 0,
    className,
}: {
    to: number;
    from?: number;
    prefix?: string;
    suffix?: string;
    decimals?: number;
    durationMs?: number;
    delayMs?: number;
    className?: string;
}) {
    const ref = useRef<HTMLSpanElement>(null);
    const inView = useInView(ref, { once: true, margin: "-60px" });
    const reduced = useReducedMotion();
    const [value, setValue] = useState(from);

    useEffect(() => {
        if (!inView) return;
        const controls = animate(from, to, {
            duration: reduced ? 0 : durationMs / 1000,
            delay: reduced ? 0 : delayMs / 1000,
            ease: [0.22, 1, 0.36, 1],
            onUpdate: (v) => setValue(v),
        });
        return () => controls.stop();
    }, [inView, reduced, from, to, durationMs, delayMs]);

    const formatted = value.toLocaleString("en-US", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    });

    return (
        <span ref={ref} className={className}>
            {prefix}
            {formatted}
            {suffix}
        </span>
    );
}
