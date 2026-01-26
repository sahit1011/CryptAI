"use client";

import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

export function CTASection() {
    return (
        <section className="py-32 relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-b from-transparent to-indigo-950/20 pointer-events-none" />

            <div className="container mx-auto px-4 md:px-6 relative z-10 text-center">
                <h2 className="text-4xl md:text-5xl font-bold tracking-tight mb-6 bg-clip-text text-transparent bg-[linear-gradient(to_right,white,white,rgba(255,255,255,0.5),white,white)] bg-[length:200%_auto] animate-shine">
                    Ready to automate your strategy?
                </h2>
                <p className="text-xl text-muted-foreground max-w-2xl mx-auto mb-10">
                    Join thousands of traders who have switched to autonomous agent-based trading.
                    Start small, scale infinitely.
                </p>

                <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                    <Link href="/auth/signup">
                        <Button size="lg" className="h-14 px-8 rounded-full bg-white text-black hover:bg-white/90 text-lg font-medium shadow-xl hover:shadow-2xl hover:shadow-white/20 transition-all">
                            Get Started for Free <ArrowRight className="ml-2 w-5 h-5" />
                        </Button>
                    </Link>
                    <Link href="/contact">
                        <Button variant="ghost" size="lg" className="h-14 px-8 rounded-full text-lg font-medium hover:bg-white/5">
                            Contact Sales
                        </Button>
                    </Link>
                </div>
            </div>
        </section>
    );
}
