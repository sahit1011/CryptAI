"use client"

import Link from "next/link"
import { usePathname, useSearchParams } from "next/navigation"
import { LayoutDashboard, Activity, Bot, Wallet, LineChart, LogOut, TrendingUp, TrendingDown, Home, Plug, Radar } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { PnL } from "@/components/ui/value"
import { createClient } from "@/utils/supabase/client"
import { useState } from "react"
import { useStore } from "@/store/useStore"
import { useMarketStore } from "@/hooks/useMarketData"

// Nav maps to the real dashboard sections (URL-driven via ?section=), so nothing
// points at a route that doesn't exist. `section` is matched against ?section=.
const routes = [
    { label: "Home", icon: Home, href: "/", section: null },
    { label: "Overview", icon: LayoutDashboard, href: "/dashboard", section: "overview" },
    { label: "Portfolio", icon: Wallet, href: "/dashboard?section=portfolio", section: "portfolio" },
    { label: "Markets", icon: LineChart, href: "/dashboard?section=markets", section: "markets" },
    { label: "Signals", icon: Radar, href: "/dashboard?section=signals", section: "signals" },
    { label: "Connect", icon: Plug, href: "/dashboard?section=connect", section: "connect" },
    { label: "AI Agents", icon: Bot, href: "/dashboard?section=agents", section: "agents" },
]

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
    const pathname = usePathname()
    const searchParams = useSearchParams()
    const currentSection = searchParams.get("section") || "overview"
    const supabase = createClient()
    const [isLoggingOut, setIsLoggingOut] = useState(false)
    const { portfolio } = useStore()
    const { status } = useMarketStore()

    // Only trust P&L once the live feed is open; otherwise show honest dashes.
    const live = status === "open"
    const gain = portfolio.totalPnl >= 0

    const handleLogout = async () => {
        setIsLoggingOut(true)
        await supabase.auth.signOut()
        // Force full page reload to clear auth state.
        window.location.href = "/"
    }

    return (
        <div className="flex h-full flex-col border-r border-border bg-sidebar">
            {/* Logo */}
            <div className="px-6 py-8">
                <Link href="/" className="group flex items-center gap-3">
                    <div className="flex size-8 items-center justify-center rounded-lg border border-border bg-accent-muted text-accent transition-colors group-hover:border-border-strong">
                        <Activity className="size-5" />
                    </div>
                    <span className="text-lg font-semibold tracking-tight text-foreground">CryptAI</span>
                </Link>
            </div>

            {/* Navigation */}
            <nav className="flex-1 space-y-1 px-4">
                {routes.map((route) => {
                    const isActive =
                        route.section === null
                            ? pathname === "/"
                            : pathname === "/dashboard" && currentSection === route.section
                    return (
                        <Link
                            key={route.href}
                            href={route.href}
                            onClick={onNavigate}
                            className={cn(
                                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors duration-200",
                                isActive
                                    ? "bg-elevated text-foreground ring-1 ring-border"
                                    : "text-muted-foreground hover:bg-elevated/60 hover:text-foreground"
                            )}
                        >
                            <route.icon
                                className={cn(
                                    "size-4 transition-colors",
                                    isActive ? "text-accent" : "text-subtle-foreground"
                                )}
                            />
                            {route.label}
                        </Link>
                    )
                })}
            </nav>

            {/* Total P&L — real store data, honest dashes when feed is down */}
            <div className="px-4 pb-4">
                <div className="space-y-3 rounded-xl border border-border bg-surface p-4">
                    <div className="flex items-center justify-between">
                        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                            Total P&L
                        </span>
                        {live ? (
                            gain ? (
                                <TrendingUp className="size-3.5 text-profit" />
                            ) : (
                                <TrendingDown className="size-3.5 text-loss" />
                            )
                        ) : (
                            <TrendingUp className="size-3.5 text-subtle-foreground" />
                        )}
                    </div>
                    <div className="space-y-1">
                        <PnL
                            value={live ? portfolio.totalPnl : null}
                            prefix="$"
                            className="text-2xl font-semibold"
                        />
                        <div>
                            <PnL
                                value={live ? portfolio.totalPnlPercent : null}
                                percent
                                className="text-xs font-medium"
                            />
                        </div>
                    </div>
                </div>
            </div>

            {/* Logout */}
            <div className="px-4 pb-6">
                <Button
                    variant="ghost"
                    onClick={handleLogout}
                    disabled={isLoggingOut}
                    className="h-9 w-full justify-start"
                >
                    <LogOut className="mr-3 size-4" />
                    {isLoggingOut ? "Logging out…" : "Logout"}
                </Button>
            </div>
        </div>
    )
}
