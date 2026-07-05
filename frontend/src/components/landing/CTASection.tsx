"use client";

import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

/*
 * CTASection — the closing invitation. One emerald atmosphere layer, a glass
 * panel for depth, an emerald filled primary CTA (no white buttons), and honest,
 * confident copy (no fabricated "thousands of traders" social proof).
 */
export function CTASection() {
    return (
        <section className="relative overflow-hidden py-28 md:py-36">
            {/* Continuous emerald atmosphere — reuses the shared aurora/grid utilities. */}
            <div className="aurora z-0" aria-hidden>
                <div className="grid-perspective" />
            </div>

            <div className="container relative z-10 mx-auto px-4 md:px-6">
                <motion.div
                    initial={{ opacity: 0, y: 24 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-80px" }}
                    transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                    className="glass-panel mx-auto max-w-3xl px-6 py-14 text-center md:px-14 md:py-16"
                >
                    <span className="label-md text-accent-300">Get started</span>

                    <h2 className="display-3 mt-4 text-balance">
                        Put your strategy on{" "}
                        <span className="text-gradient-brand animate-shine bg-[length:200%_auto]">
                            autopilot
                        </span>
                    </h2>

                    <p className="body-md text-muted-foreground mx-auto mt-5 max-w-xl text-pretty">
                        Spin up an autonomous trading agent in minutes. Start safely on
                        testnet, validate against real market history, and go live only when
                        you&apos;re ready — you keep custody the whole way.
                    </p>

                    <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
                        <Button
                            asChild
                            size="lg"
                            className="brand-glow h-12 rounded-full px-8 text-base"
                        >
                            <Link href="/auth/signup">
                                Start free on testnet
                                <ArrowRight className="ml-1 h-5 w-5" />
                            </Link>
                        </Button>
                        <Button
                            asChild
                            variant="outline"
                            size="lg"
                            className="h-12 rounded-full px-8 text-base"
                        >
                            <Link href="/contact">Talk to us</Link>
                        </Button>
                    </div>

                    <p className="body-xs mt-6">
                        No credit card required · Non-custodial · Cancel anytime
                    </p>
                </motion.div>
            </div>
        </section>
    );
}
