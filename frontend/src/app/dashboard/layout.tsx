"use client";

import { Sidebar } from "@/components/dashboard/Sidebar"
import { Header } from "@/components/dashboard/Header"
import { ErrorBoundary } from "@/components/ui/ErrorBoundary"
import { LoadingState } from "@/components/ui/states"
import { Suspense, useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { createClient } from "@/utils/supabase/client"
import { cn } from "@/lib/utils"

export default function DashboardLayout({
    children,
}: {
    children: React.ReactNode
}) {
    const [isLoading, setIsLoading] = useState(true);
    const [mobileNavOpen, setMobileNavOpen] = useState(false);
    const router = useRouter();
    const supabase = createClient();

    useEffect(() => {
        const checkAuth = async () => {
            const { data: { session } } = await supabase.auth.getSession();

            if (!session) {
                router.push("/auth/login");
                return;
            }
            // First-run users pick their preferences (mode + exchange) in onboarding
            // before seeing the dashboard. Fail-open: if the settings API is
            // unreachable (e.g. backend cold start), don't lock users out.
            // Fail-fast too: the free-tier backend cold-starts in minutes — never
            // hold the dashboard hostage on this call. 4s budget, then proceed.
            try {
                const { getSettings } = await import("@/lib/api");
                const s = await Promise.race([
                    getSettings(),
                    new Promise<never>((_, rej) => setTimeout(() => rej(new Error("timeout")), 4000)),
                ]);
                if (s.onboarded === false) {
                    router.push("/onboarding");
                    return;
                }
            } catch { /* fail-open */ }
            setIsLoading(false);
        };

        checkAuth();

        // Listen for auth changes
        const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
            if (!session) {
                router.push("/auth/login");
            }
        });

        return () => subscription.unsubscribe();
    }, [router, supabase]);

    if (isLoading) {
        return (
            <div className="flex h-screen w-screen items-center justify-center bg-background">
                <LoadingState title="Loading dashboard…" />
            </div>
        );
    }

    return (
        <div className="relative h-full bg-background">
            {/* Persistent sidebar (md and up) */}
            <div className="z-[80] hidden h-full md:fixed md:inset-y-0 md:flex md:w-72 md:flex-col">
                <Suspense fallback={<div className="h-full w-full border-r border-border bg-sidebar" />}>
                    <Sidebar />
                </Suspense>
            </div>

            {/* Mobile nav drawer (below md) — same Sidebar in a slide-in sheet */}
            <div
                className={cn(
                    "fixed inset-0 z-[90] md:hidden",
                    mobileNavOpen ? "pointer-events-auto" : "pointer-events-none",
                )}
                aria-hidden={!mobileNavOpen}
            >
                <div
                    className={cn(
                        "absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity duration-300",
                        mobileNavOpen ? "opacity-100" : "opacity-0",
                    )}
                    onClick={() => setMobileNavOpen(false)}
                />
                <div
                    className={cn(
                        "absolute inset-y-0 left-0 flex w-72 max-w-[82vw] flex-col shadow-[var(--shadow-elevation-high)] transition-transform duration-300 ease-out",
                        mobileNavOpen ? "translate-x-0" : "-translate-x-full",
                    )}
                >
                    <Suspense fallback={<div className="h-full w-full border-r border-border bg-sidebar" />}>
                        <Sidebar onNavigate={() => setMobileNavOpen(false)} />
                    </Suspense>
                </div>
            </div>

            <main className="h-full md:pl-72">
                <Header onMenuClick={() => setMobileNavOpen(true)} />
                <div className="h-full p-4 sm:p-6 lg:p-8">
                    <ErrorBoundary>
                        {children}
                    </ErrorBoundary>
                </div>
            </main>
        </div>
    )
}
