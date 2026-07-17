"use client";

import { motion } from "framer-motion";

/*
 * ProofSection — "The Standing Orders". No fabricated testimonials (we have no
 * users to quote, and faking them would betray the brand). Instead: a two-voice
 * ledger — each plain-language promise (left) paired with the exact mechanism in
 * code that enforces it (right), split by a semantic hairline spine. Every
 * mechanism string maps to real, verifiable system behavior.
 *
 * Design direction from the marketing-bands design workflow (winner: Standing
 * Orders), built against CryptAI's real crimson tokens.
 */

const ease = [0.16, 1, 0.3, 1] as const;

type Order = {
    promise: React.ReactNode;
    mechanism: React.ReactNode;
};

const ORDERS: Order[] = [
    {
        promise: (
            <>
                Your money <em className="font-serif italic text-accent-300">never</em> touches us.
            </>
        ),
        mechanism: "non-custodial · you connect your own exchange keys · Fernet-encrypted per-user vault · no CryptAI wallet exists",
    },
    {
        promise: <>No real capital is at risk. Not yet, by design.</>,
        mechanism: (
            <>
                USE_TESTNET=true · LIVE_TRADING_CONFIRMED=false ·{" "}
                <span className="text-accent-300 line-through decoration-accent">mainnet</span> orders refused at the gate
            </>
        ),
    },
    {
        promise: <>Risk is decided by rules, not a model&apos;s mood.</>,
        mechanism: "deterministic risk gate · sizing + hard stops in code · the model proposes, the gate disposes",
    },
    {
        promise: <>One analysis. Every desk sees the same read.</>,
        mechanism: "shared analysis runs once per cycle → fans out per user · no private signal, no pay-to-front-run",
    },
    {
        promise: <>You can read the machine.</>,
        mechanism: "open multi-agent pipeline · LangGraph orchestrator · every agent's activity streamed to your dashboard",
    },
];

export function ProofSection() {
    return (
        <section className="relative py-24 md:py-32">
            <div className="container relative z-10 mx-auto max-w-5xl px-4 md:px-6">
                {/* Thesis — names the absence of social proof, replaces it with enforcement. */}
                <div className="flex flex-col justify-between gap-3 md:flex-row md:items-baseline">
                    <motion.p
                        initial={{ opacity: 0, y: 12 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: "-80px" }}
                        transition={{ duration: 0.5, ease }}
                        className="max-w-[60ch] text-lg leading-relaxed text-muted-foreground"
                    >
                        We can&apos;t show you customer logos yet. So here&apos;s the next best thing:
                        the constraints this system is built to obey — and what enforces each one.
                    </motion.p>
                    <span className="num shrink-0 text-[11px] uppercase tracking-[0.14em] text-subtle-foreground">
                        standing orders · enforced in code
                    </span>
                </div>

                {/* The ledger — two voices, a spine between them. */}
                <div className="mt-12">
                    {ORDERS.map((order, i) => (
                        <motion.div
                            key={i}
                            initial={{ opacity: 0, y: 14 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true, margin: "-70px" }}
                            transition={{ duration: 0.5, delay: i * 0.06, ease }}
                            className="grid gap-4 border-t border-border py-6 md:grid-cols-[1fr_1px_22rem] md:gap-0"
                        >
                            {/* Promise */}
                            <p className="text-balance pr-0 text-xl font-medium leading-snug text-foreground md:pr-10 md:text-[1.6rem]">
                                {order.promise}
                            </p>
                            {/* Spine (desktop only) */}
                            <span aria-hidden className="hidden bg-border-strong md:block" />
                            {/* Mechanism — the machine's own words */}
                            <p className="num text-[13px] leading-relaxed text-muted-foreground md:pl-8">
                                {order.mechanism}
                            </p>
                        </motion.div>
                    ))}
                    <div className="border-t border-border" />
                </div>

                {/* Signature — turns the ledger into a signed document. */}
                <div className="mt-6 text-right">
                    <a
                        href="https://github.com/sahit1011"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="num text-sm text-muted-foreground transition-colors duration-150 hover:text-foreground"
                    >
                        — enforced, not promised. read the source ↗
                    </a>
                </div>
            </div>
        </section>
    );
}
