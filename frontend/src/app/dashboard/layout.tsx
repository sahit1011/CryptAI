"use client";

import { Sidebar } from "@/components/dashboard/Sidebar"
import { Header } from "@/components/dashboard/Header"
import { ErrorBoundary } from "@/components/ui/ErrorBoundary"
import { LoadingState } from "@/components/ui/states"
import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { createClient } from "@/utils/supabase/client"

export default function DashboardLayout({
    children,
}: {
    children: React.ReactNode
}) {
    const [isLoading, setIsLoading] = useState(true);
    const router = useRouter();
    const supabase = createClient();

    useEffect(() => {
        const checkAuth = async () => {
            const { data: { session } } = await supabase.auth.getSession();

            if (!session) {
                router.push("/auth/login");
            } else {
                setIsLoading(false);
            }
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
            <div className="z-[80] hidden h-full md:fixed md:inset-y-0 md:flex md:w-72 md:flex-col">
                <Sidebar />
            </div>
            <main className="h-full md:pl-72">
                <Header />
                <div className="h-full p-8">
                    <ErrorBoundary>
                        {children}
                    </ErrorBoundary>
                </div>
            </main>
        </div>
    )
}
