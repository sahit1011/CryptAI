"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ArrowRight, Activity, AlertCircle } from "lucide-react";
import { BackgroundGrid } from "@/components/landing/BackgroundGrid";

export default function AuthCodeErrorPage() {
    return (
        <div className="flex min-h-screen items-center justify-center bg-background text-foreground relative overflow-hidden">
            {/* Background Grid */}
            <BackgroundGrid />

            {/* Additional Emerald-Cyan Glow */}
            <div className="absolute inset-0 z-0 pointer-events-none">
                <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-accent/10 blur-[120px]" />
                <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full bg-accent/10 blur-[120px]" />
            </div>

            <div className="w-full max-w-md p-8 relative z-10">
                {/* Logo */}
                <Link href="/" className="flex justify-center mb-8 group">
                    <div className="flex items-center gap-3">
                        <div className="w-12 h-12 rounded-xl bg-accent/10 flex items-center justify-center border border-border backdrop-blur-md shadow-xl group-hover:bg-accent/15 group-hover:scale-105 transition-all">
                            <Activity className="w-6 h-6 text-foreground" />
                        </div>
                        <span className="text-2xl font-bold tracking-tight text-foreground group-hover:text-accent-300 transition-colors">
                            CryptAI
                        </span>
                    </div>
                </Link>

                {/* Error Card */}
                <div className="glass-card rounded-2xl p-8 space-y-6 relative overflow-hidden">
                    {/* Gradient Border Effect */}
                    <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-red-500/20 via-orange-500/20 to-red-500/20 opacity-50 pointer-events-none" />

                    <div className="text-center space-y-4 relative z-10">
                        {/* Error Icon */}
                        <div className="flex justify-center">
                            <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center border border-red-500/20">
                                <AlertCircle className="w-8 h-8 text-red-400" />
                            </div>
                        </div>

                        <h1 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-red-400 via-orange-400 to-red-400 bg-clip-text text-transparent">
                            Authentication Error
                        </h1>

                        <p className="text-sm text-muted-foreground">
                            We encountered an issue while trying to authenticate your account.
                        </p>

                        <div className="bg-red-500/10 border border-red-500/20 text-red-400 px-4 py-3 rounded-lg text-sm">
                            <p className="font-medium mb-1">Possible reasons:</p>
                            <ul className="text-left list-disc list-inside space-y-1 text-xs">
                                <li>The authentication code has expired</li>
                                <li>The code was already used</li>
                                <li>There was a network error</li>
                                <li>Google OAuth is not properly configured</li>
                            </ul>
                        </div>
                    </div>

                    <div className="space-y-3 relative z-10">
                        <Link href="/auth/login" className="block">
                            <Button
                                className="w-full h-11 bg-primary text-primary-foreground hover:bg-accent-400 font-medium transition-all hover:scale-[1.02] brand-glow relative z-10 group overflow-hidden"
                            >
                                <span className="relative z-10 flex items-center justify-center">
                                    Try Again <ArrowRight className="ml-2 h-4 w-4 group-hover:translate-x-1 transition-transform" />
                                </span>
                                {/* Shine effect */}
                                <div className="absolute inset-0 -translate-x-full group-hover:translate-x-full transition-transform duration-1000 bg-gradient-to-r from-transparent via-white/30 to-transparent skew-x-12" />
                            </Button>
                        </Link>

                        <Link href="/auth/signup" className="block">
                            <Button
                                variant="outline"
                                className="w-full h-11 border-border bg-elevated hover:bg-muted hover:text-foreground hover:border-accent/30 transition-all"
                            >
                                Create New Account
                            </Button>
                        </Link>
                    </div>
                </div>

                <p className="mt-6 text-center text-sm text-muted-foreground relative z-10">
                    Need help?{" "}
                    <Link
                        href="/"
                        className="text-accent hover:text-accent-300 font-medium transition-colors hover:underline"
                    >
                        Contact Support
                    </Link>
                </p>
            </div>
        </div>
    );
}
