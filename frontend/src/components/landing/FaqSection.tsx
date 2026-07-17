"use client";

import { motion } from "framer-motion";
import { CountUp } from "./CountUp";

/*
 * FaqSection — "The Objection Ledger". A definition list (not an accordion —
 * answers are always on the page; a nervous skeptic shouldn't have to click to
 * learn if their money is safe), in skeptic-funnel order. Each row: the blunt
 * question + a one-word institutional tag on the left, the honest answer on the
 * right with its single load-bearing figure pinned as a "receipt". Every number
 * maps to a real enforced value.
 *
 * Design direction from the marketing-bands design workflow (winner: Objection
 * Ledger), built against CryptAI's real crimson tokens (not the sibling
 * project's emerald the workflow buildNotes mistakenly cited).
 */

const ease = [0.16, 1, 0.3, 1] as const;

type Receipt = { to: number; prefix?: string; suffix?: string; label: string } | { text: string; label: string };

type Row = {
    tag: string;
    q: string;
    a: React.ReactNode;
    receipt: Receipt;
};

const Chip = ({ children }: { children: React.ReactNode }) => (
    <span className="num rounded border border-border bg-elevated px-1.5 py-0.5 text-[0.9em] text-foreground">
        {children}
    </span>
);

const ROWS: Row[] = [
    {
        tag: "Custody",
        q: "Is my money actually safe?",
        a: (
            <>
                Every account starts in paper mode. No real funds move, no order reaches an
                exchange. Live trading is hard-gated in code and off by default.
            </>
        ),
        receipt: { to: 0, label: "orders" },
    },
    {
        tag: "Connectivity",
        q: "Do I have to connect an exchange to try it?",
        a: (
            <>
                No. With nothing connected, the desk trades a paper book against live prices.
                Connect a key only for live execution — and only a <Chip>testnet</Chip> key is
                accepted for now; every key is verified, then stored encrypted.
            </>
        ),
        receipt: { text: "testnet", label: "keys only" },
    },
    {
        tag: "Mandate",
        q: "What can it actually trade?",
        a: (
            <>
                A narrow mandate: <Chip>BTC</Chip> <Chip>ETH</Chip> <Chip>Gold</Chip>. Gold runs
                analysis and paper only — no crypto venue lists it for live orders, so we don&apos;t
                pretend otherwise.
            </>
        ),
        receipt: { to: 3, label: "markets" },
    },
    {
        tag: "Method",
        q: "Isn't this just another hype bot?",
        a: (
            <>
                A hype bot always has a signal. This desk runs 144 analysis cycles a day and most
                clear nothing — typically ~5 setups publish. Silence is the default output, not a
                bug.
            </>
        ),
        receipt: { to: 144, label: "cycles / day" },
    },
    {
        tag: "Terms",
        q: "What does it cost — can I start free?",
        a: (
            <>
                Yes. The paper desk is $0, no card, no trial clock. The full agent pipeline and
                live signals are on the free tier; paid tiers only raise limits.
            </>
        ),
        receipt: { to: 0, prefix: "$", label: "to start" },
    },
    {
        tag: "Failure",
        q: "What happens when the market falls apart?",
        a: (
            <>
                The desk stops itself. Risk is capped at <Chip>2%</Chip> per trade, the day halts at
                a <Chip>6%</Chip> loss, the circuit breaker trips at <Chip>5%</Chip> heat, and never
                more than <Chip>3</Chip> positions run at once. In a crash the emergency exit closes
                reduce-only. Enforced in code, not in copy.
            </>
        ),
        receipt: { to: 2, suffix: "%", label: "max / trade" },
    },
];

function ReceiptTag({ receipt, index }: { receipt: Receipt; index: number }) {
    return (
        <span className="flex items-baseline gap-1.5">
            <span className="num text-lg font-semibold text-accent-300">
                {"text" in receipt ? (
                    receipt.text
                ) : (
                    <CountUp to={receipt.to} prefix={receipt.prefix} suffix={receipt.suffix} delayMs={index * 40} />
                )}
            </span>
            <span className="num text-[11px] text-subtle-foreground">{receipt.label}</span>
        </span>
    );
}

export function FaqSection() {
    return (
        <section id="faq" aria-labelledby="faq-heading" className="relative py-24 md:py-32">
            <div className="container relative z-10 mx-auto max-w-5xl px-4 md:px-6">
                <motion.h2
                    id="faq-heading"
                    initial={{ opacity: 0, y: 12 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-80px" }}
                    transition={{ duration: 0.5, ease }}
                    className="display-3 max-w-2xl text-balance"
                >
                    The questions a <em className="font-serif italic text-accent-300">skeptic</em> should be asking.
                </motion.h2>

                <div className="mt-10 overflow-hidden rounded-lg border border-border bg-surface/40">
                    {/* Masthead — frames it as a document, not a widget. */}
                    <div className="flex items-center justify-between border-b border-border px-6 py-3">
                        <span className="num text-[11px] uppercase tracking-[0.14em] text-subtle-foreground">Ledger</span>
                        <span className="num text-[11px] uppercase tracking-[0.14em] text-subtle-foreground">
                            rev 2026.07 · paper default
                        </span>
                    </div>

                    <dl>
                        {ROWS.map((row, i) => (
                            <motion.div
                                key={row.tag}
                                initial={{ opacity: 0, y: 12 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true, margin: "-60px" }}
                                transition={{ duration: 0.45, delay: i * 0.05, ease }}
                                className="grid gap-y-3 border-t border-border px-6 py-8 md:grid-cols-[minmax(0,0.9fr)_1px_minmax(0,1.4fr)] md:gap-x-8 md:py-9"
                            >
                                <dt className="min-w-0">
                                    <div className="num mb-2 flex items-center gap-2 text-[11px] uppercase tracking-wider text-subtle-foreground">
                                        <span>Q.0{i + 1}</span>
                                        <span className="text-muted-foreground">· {row.tag}</span>
                                    </div>
                                    <p className="text-lg font-medium leading-snug text-foreground">{row.q}</p>
                                </dt>
                                <span aria-hidden className="hidden bg-border md:block" />
                                <dd className="min-w-0 md:pl-2">
                                    <div className="mb-2">
                                        <ReceiptTag receipt={row.receipt} index={i} />
                                    </div>
                                    <p className="max-w-prose text-[15px] leading-relaxed text-muted-foreground">{row.a}</p>
                                </dd>
                            </motion.div>
                        ))}
                    </dl>

                    {/* Reconciliation stamp */}
                    <div className="border-t border-border px-6 py-4 text-right">
                        <span className="num text-[11px] uppercase tracking-wider text-subtle-foreground">
                            Answers reflect the live system, not a roadmap
                        </span>
                    </div>
                </div>

                {/* Terminal-echo closer — quiet link, not a button (CTA owns that). */}
                <p className="mt-5 text-sm text-muted-foreground">
                    Not convinced? Watch it on paper first —{" "}
                    <a href="#cta" className="num text-accent-300 transition-colors duration-150 hover:text-accent-200">
                        $ cryptai start --paper
                    </a>
                </p>
            </div>
        </section>
    );
}
