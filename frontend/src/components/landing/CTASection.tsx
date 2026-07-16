"use client";

import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

/*
 * CTASection — the closing invitation. One crimson atmosphere layer, a glass
 * panel for depth, an crimson filled primary CTA (no white buttons), and honest,
 * confident copy (no fabricated "thousands of traders" social proof).
 */
export function CTASection() {
    return (
        <section className="relative overflow-hidden py-28 md:py-36">
            {/* Continuous crimson atmosphere — reuses the shared aurora/grid utilities. */}
            <div className="aurora z-0" aria-hidden>
                <div className="grid-perspective" />
            </div>

            <div className="container relative z-10 mx-auto px-4 md:px-6">
                <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-80px" }}
                    transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                    className="mx-auto max-w-3xl rounded-xl border border-border bg-surface px-6 py-14 md:px-14 md:py-16"
                >
                    <span className="eyebrow text-accent-300">Get started</span>

                    <h2 className="display-2 mt-4 max-w-xl text-balance">
                        Put a whole trading desk behind your account.
                    </h2>

                    <p className="body-md text-muted-foreground mt-5 max-w-xl text-pretty">
                        Spin up the agent pipeline in minutes. Start safely on testnet paper
                        trading, watch how it argues each setup, and connect your exchange only
                        when you&apos;re ready — you keep custody the whole way.
                    </p>

                    <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
                        <Button asChild size="lg" className="h-11 px-6 text-[15px]">
                            <Link href="/auth/signup">
                                Start free on testnet
                                <ArrowRight className="size-4" />
                            </Link>
                        </Button>
                        <Button asChild variant="ghost" size="lg" className="h-11 px-4 text-[15px]">
                            <Link href="/contact">Talk to us</Link>
                        </Button>
                    </div>

                    <p className="num mt-8 text-xs text-subtle-foreground">
                        No credit card · non-custodial · cancel anytime
                    </p>
                </motion.div>
            </div>
        </section>
    );
}
