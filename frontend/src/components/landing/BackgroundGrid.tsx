"use client";

import { useEffect, useState } from "react";

/*
 * BackgroundGrid — the shared landing atmosphere.
 *
 * Layers (back to front):
 *   1. .aurora            — two drifting blurred crimson radial glows over canvas
 *   2. .grid-perspective  — hairline crimson grid, masked to fade at the edges
 *   3. crimson motes      — very subtle drifting particles (client-only)
 *
 * It should feel like one continuous crimson atmosphere down the page. All
 * colors come from the --accent-* tokens; no off-brand hues, no hardcoded hex.
 * Particle positions are generated client-side (Math.random never runs during
 * render — the initial render has an empty particle list) to avoid hydration
 * mismatch and satisfy the React compiler.
 */

type Mote = {
    left: string;
    top: string;
    size: number;
    opacity: number;
    delay: number;
    duration: number;
};

function generateMotes(): Mote[] {
    return Array.from({ length: 22 }, () => ({
        left: `${Math.random() * 100}%`,
        top: `${55 + Math.random() * 45}%`,
        size: Math.random() * 2 + 1.5,
        opacity: Math.random() * 0.35 + 0.15,
        delay: Math.random() * 12,
        duration: Math.random() * 10 + 14,
    }));
}

export const BackgroundGrid = () => {
    const [motes, setMotes] = useState<Mote[]>([]);

    useEffect(() => {
        // Client-only: defer so the impure generation runs in a callback, not
        // synchronously during the effect's first paint path. Runs once.
        let cancelled = false;
        queueMicrotask(() => {
            if (!cancelled) setMotes(generateMotes());
        });
        return () => {
            cancelled = true;
        };
    }, []);

    return (
        <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
            {/* Crimson aurora + masked perspective grid (pure CSS utilities). */}
            <div className="aurora">
                <div className="grid-perspective" />
            </div>

            {/* Subtle crimson motes drifting upward. */}
            <div className="absolute inset-0">
                {motes.map((mote, i) => (
                    <span
                        key={i}
                        className="absolute rounded-full bg-accent-300"
                        style={{
                            left: mote.left,
                            top: mote.top,
                            width: mote.size,
                            height: mote.size,
                            animation: `particle-rise ${mote.duration}s ease-in-out ${mote.delay}s infinite`,
                            // Per-particle peak opacity read by the keyframe.
                            ["--p-opacity" as string]: mote.opacity,
                        }}
                    />
                ))}
            </div>
        </div>
    );
};
