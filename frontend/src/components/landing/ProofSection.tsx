"use client";

import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { Check, ShieldCheck } from "lucide-react";
import { useRef } from "react";

/*
 * ProofSection — "The Enforcement Log". No fabricated testimonials (we have no
 * users to quote, and faking them betrays the brand). Instead: a live
 * verification console. Each standing order is a promise paired with the exact
 * mechanisms that enforce it, shown as scannable mono tokens. A crimson
 * verification spine fills as you scroll; each order's node locks and stamps
 * "ENFORCED" as it enters view — the section audits itself in front of you.
 *
 * Every mechanism string maps to real, verifiable system behavior.
 */

const ease = [0.16, 1, 0.3, 1] as const;

type Order = {
    promise: React.ReactNode;
    tokens: React.ReactNode[];
};

const ORDERS: Order[] = [
    {
        promise: (
            <>
                Your money <em className="font-serif italic text-accent-300">never</em> touches us.
            </>
        ),
        tokens: ["non-custodial", "your own exchange keys", "Fernet-encrypted vault", "no CryptAI wallet"],
    },
    {
        promise: <>No real capital is at risk. Not yet, by design.</>,
        tokens: [
            "USE_TESTNET=true",
            "LIVE_TRADING_CONFIRMED=false",
            <>
                <span className="text-accent-300 line-through decoration-accent">mainnet</span> refused at the gate
            </>,
        ],
    },
    {
        promise: <>Risk is decided by rules, not a model&apos;s mood.</>,
        tokens: ["deterministic gate", "sizing + hard stops in code", "model proposes · gate disposes"],
    },
    {
        promise: <>One analysis. Every desk sees the same read.</>,
        tokens: ["runs once per cycle", "fans out per user", "no pay-to-front-run"],
    },
    {
        promise: <>You can read the machine.</>,
        tokens: ["open multi-agent pipeline", "LangGraph orchestrator", "streamed to your dashboard"],
    },
];

function Token({ children }: { children: React.ReactNode }) {
    return (
        <span className="num rounded border border-border bg-elevated/60 px-2 py-1 text-[11px] text-muted-foreground">
            {children}
        </span>
    );
}

function OrderRow({ order, index }: { order: Order; index: number }) {
    const reduced = useReducedMotion();
    return (
        <motion.div
            initial={reduced ? undefined : "idle"}
            whileInView="active"
            viewport={{ once: true, margin: "-25% 0px -25% 0px" }}
            className="relative grid grid-cols-[48px_1fr] gap-x-3 border-t border-border py-7 md:grid-cols-[64px_1fr_auto] md:gap-x-5 md:py-8"
        >
            {/* Node on the spine — locks crimson when the row activates. */}
            <div className="flex justify-center pt-1">
                <motion.span
                    variants={{
                        idle: { backgroundColor: "rgba(255,255,255,0.06)", borderColor: "rgba(255,255,255,0.14)", scale: 1 },
                        active: { backgroundColor: "var(--accent)", borderColor: "var(--accent)", scale: [1, 1.35, 1] },
                    }}
                    transition={{ duration: 0.5, ease }}
                    className="relative z-10 mt-1 flex size-3 items-center justify-center rounded-full border"
                >
                    <motion.span
                        aria-hidden
                        variants={{ idle: { opacity: 0, scale: 1 }, active: { opacity: [0, 0.5, 0], scale: [1, 3, 3.6] } }}
                        transition={{ duration: 0.9, ease }}
                        className="absolute inset-0 rounded-full bg-accent"
                    />
                </motion.span>
            </div>

            {/* Promise + enforcement tokens */}
            <div>
                <div className="flex items-baseline gap-3">
                    <span className="num text-xs text-subtle-foreground">
                        {String(index + 1).padStart(2, "0")}
                    </span>
                    <p className="text-balance text-xl font-medium leading-snug text-foreground md:text-[1.55rem]">
                        {order.promise}
                    </p>
                </div>
                <div className="mt-3.5 flex min-w-0 flex-wrap gap-2 md:ml-8">
                    {order.tokens.map((t, i) => (
                        <Token key={i}>{t}</Token>
                    ))}
                </div>
            </div>

            {/* ENFORCED stamp — hits when the row activates. */}
            <motion.div
                variants={{
                    idle: reduced ? {} : { opacity: 0, scale: 0.9 },
                    active: { opacity: 1, scale: 1 },
                }}
                transition={{ duration: 0.4, delay: 0.15, ease }}
                className="col-start-2 mt-3 flex items-center gap-1.5 self-start md:col-start-3 md:mt-1 md:justify-self-end"
            >
                <Check className="size-3.5 text-accent-300" />
                <span className="num text-[11px] uppercase tracking-[0.14em] text-accent-300">Enforced</span>
            </motion.div>
        </motion.div>
    );
}

export function ProofSection() {
    const reduced = useReducedMotion();
    const consoleRef = useRef<HTMLDivElement>(null);
    // Verification spine fills as the console scrolls through the viewport.
    const { scrollYProgress } = useScroll({
        target: consoleRef,
        offset: ["start 0.75", "end 0.6"],
    });
    const spineScale = useTransform(scrollYProgress, [0, 1], [0, 1]);

    return (
        <section className="relative py-24 md:py-32">
            <div className="container relative z-10 mx-auto max-w-5xl px-4 md:px-6">
                {/* Thesis — names the absence of social proof, replaces it with enforcement. */}
                <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
                    <motion.h2
                        initial={{ opacity: 0, y: 12 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: "-80px" }}
                        transition={{ duration: 0.55, ease }}
                        className="display-3 max-w-2xl text-balance"
                    >
                        No testimonials. Just the constraints this system{" "}
                        <em className="font-serif italic text-accent-300">cannot break.</em>
                    </motion.h2>
                    <span className="num flex shrink-0 items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-subtle-foreground">
                        <ShieldCheck className="size-3.5 text-accent-300" />
                        enforced in code
                    </span>
                </div>

                <p className="body-md mt-4 max-w-xl text-muted-foreground">
                    We can&apos;t show you customer logos yet. So here&apos;s the next best thing —
                    every promise below is one the code is structurally forced to keep.
                </p>

                {/* The console */}
                <div className="mt-12 overflow-hidden rounded-xl border border-border bg-surface/40">
                    <div className="flex items-center justify-between border-b border-border px-5 py-3 md:px-6">
                        <span className="num text-[11px] uppercase tracking-[0.14em] text-subtle-foreground">
                            Enforcement log
                        </span>
                        <span className="num flex items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-accent-300">
                            <span className="size-1.5 animate-pulse-subtle rounded-full bg-accent" />
                            5 / 5 active
                        </span>
                    </div>

                    <div ref={consoleRef} className="relative px-5 md:px-6">
                        {/* Verification spine: hairline track + crimson scroll-fill, behind the nodes. */}
                        <span
                            aria-hidden
                            className="pointer-events-none absolute bottom-8 top-8 w-px bg-border"
                            style={{ left: "calc(1.25rem + 24px)" }}
                        />
                        <motion.span
                            aria-hidden
                            className="pointer-events-none absolute bottom-8 top-8 w-px origin-top bg-accent"
                            style={{ left: "calc(1.25rem + 24px)", scaleY: reduced ? 1 : spineScale }}
                        />
                        {/* First row drops its top border so it meets the console header cleanly. */}
                        <div className="[&>div:first-child]:border-t-0">
                            {ORDERS.map((order, i) => (
                                <OrderRow key={i} order={order} index={i} />
                            ))}
                        </div>
                    </div>

                    {/* Signature — turns the log into a signed document. */}
                    <div className="border-t border-border px-5 py-4 text-right md:px-6">
                        <a
                            href="https://github.com/sahit1011"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="num text-xs text-muted-foreground transition-colors duration-150 hover:text-foreground"
                        >
                            — enforced, not promised. read the source ↗
                        </a>
                    </div>
                </div>
            </div>
        </section>
    );
}
