"use client";

import { type ReactNode, useEffect } from "react";
import Lenis from "lenis";

/*
 * SmoothScroll — Lenis-driven inertial scrolling for the landing page. This is
 * the substrate the scroll-scrubbed scenes ride on: without easing, scrubbed
 * reveals feel notchy. Skipped entirely under prefers-reduced-motion (native
 * scrolling remains untouched).
 */
export function SmoothScroll({ children }: { children: ReactNode }) {
    useEffect(() => {
        if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
        const lenis = new Lenis({ lerp: 0.1, wheelMultiplier: 1 });
        let raf = 0;
        const loop = (time: number) => {
            lenis.raf(time);
            raf = requestAnimationFrame(loop);
        };
        raf = requestAnimationFrame(loop);
        return () => {
            cancelAnimationFrame(raf);
            lenis.destroy();
        };
    }, []);

    return <>{children}</>;
}
