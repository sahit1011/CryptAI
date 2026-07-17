"use client";

import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

/*
 * CTASection — the closing invitation, in the product's own voice: a serif
 * headline and a terminal prompt line instead of another bordered marketing
 * card. The prompt is the brand moment; the buttons do the work.
 */
export function CTASection() {
    return (
        <section className="relative overflow-hidden py-28 md:py-36">
            <div className="container relative z-10 mx-auto max-w-6xl px-4 md:px-6">
                <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-80px" }}
                    transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
                    className="max-w-3xl"
                >
                    <h2 className="display-2 text-balance">
                        The whole pipeline,{" "}
                        <em className="font-serif text-accent-300">behind your account.</em>
                    </h2>

                    <p className="body-md mt-5 max-w-xl text-pretty text-muted-foreground">
                        Start safely on testnet paper trading, watch how the agents argue
                        each setup, and connect your exchange only when you&apos;re ready —
                        you keep custody the whole way.
                    </p>

                    {/* The prompt — brand voice, not decoration. */}
                    <div className="mt-9 flex max-w-xl items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3">
                        <span className="num text-sm text-subtle-foreground">$</span>
                        <span className="num flex-1 text-sm text-foreground">
                            cryptai start --paper
                            <span className="type-cursor ml-1 inline-block h-[1em] w-[0.5ch] translate-y-[0.15em] bg-accent" />
                        </span>
                        <Button asChild size="sm" className="shrink-0">
                            <Link href="/auth/signup">
                                Run it
                                <ArrowRight className="size-3.5" />
                            </Link>
                        </Button>
                    </div>

                    <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2">
                        <Link
                            href="/contact"
                            className="text-sm font-medium text-muted-foreground transition-colors duration-150 hover:text-foreground"
                        >
                            Talk to us
                        </Link>
                        <span className="num text-xs text-subtle-foreground">
                            no credit card · non-custodial · cancel anytime
                        </span>
                    </div>
                </motion.div>
            </div>
        </section>
    );
}
