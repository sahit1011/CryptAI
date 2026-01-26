"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { LayoutDashboard, Activity, Bot, Settings, FileText, LogOut, TrendingUp, Home } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { GlassCard } from "@/components/ui/glass-card"
import { createClient } from "@/utils/supabase/client"
import { useState } from "react"
import { useStore } from "@/store/useStore"
import { useMarketStore } from "@/hooks/useMarketData"

const routes = [
    {
        label: "Home",
        icon: Home,
        href: "/",
        color: "text-emerald-400",
    },
    {
        label: "Dashboard",
        icon: LayoutDashboard,
        href: "/dashboard",
        color: "text-blue-400",
    },
    {
        label: "Analytics",
        icon: Activity,
        href: "/dashboard/analytics",
        color: "text-purple-400",
    },
    {
        label: "Agents",
        icon: Bot,
        href: "/dashboard/agents",
        color: "text-pink-400",
    },
    {
        label: "Logs",
        icon: FileText,
        href: "/dashboard/logs",
        color: "text-orange-400",
    },
    {
        label: "Settings",
        icon: Settings,
        href: "/dashboard/settings",
        color: "text-gray-400",
    },
]

export function Sidebar() {
    const pathname = usePathname()
    const router = useRouter()
    const supabase = createClient()
    const [isLoggingOut, setIsLoggingOut] = useState(false)
    const { portfolio } = useStore()
    const { isConnected } = useMarketStore()

    const handleLogout = async () => {
        setIsLoggingOut(true)
        await supabase.auth.signOut()
        // Use window.location to force full page reload and clear auth state
        window.location.href = "/"
    }

    return (
        <div className="flex flex-col h-full bg-[#0A0A0A] border-r border-white/5">
            {/* Logo */}
            <div className="px-6 py-8">
                <Link href="/" className="flex items-center gap-3 group">
                    <div className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center border border-white/10 group-hover:bg-white/10 transition-colors">
                        <Activity className="w-5 h-5 text-white" />
                    </div>
                    <span className="text-lg font-medium tracking-tight text-white">CryptAI</span>
                </Link>
            </div>

            {/* Navigation */}
            <nav className="flex-1 px-4 space-y-1">
                {routes.map((route) => {
                    const isActive = pathname === route.href
                    return (
                        <Link
                            key={route.href}
                            href={route.href}
                            className={cn(
                                "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-all duration-200",
                                isActive
                                    ? "bg-white/10 text-white shadow-sm ring-1 ring-white/5"
                                    : "text-muted-foreground hover:text-white hover:bg-white/5"
                            )}
                        >
                            <route.icon className={cn("h-4 w-4", isActive ? "text-white" : "text-muted-foreground/70")} />
                            {route.label}
                        </Link>
                    )
                })}
            </nav>

            {/* Performance Card */}
            <div className="px-4 pb-4">
                <div className="p-4 rounded-xl bg-gradient-to-b from-white/5 to-transparent border border-white/5 space-y-3">
                    <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-muted-foreground">Total P&L</span>
                        <TrendingUp className={cn("h-3.5 w-3.5", portfolio.totalPnl >= 0 ? "text-emerald-400" : "text-red-400")} />
                    </div>
                    <div className="space-y-1">
                        <div className={cn("text-2xl font-mono font-medium", portfolio.totalPnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                            {isConnected ? `$${portfolio.totalPnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "---"}
                        </div>
                        <div className={cn("text-xs font-medium", portfolio.totalPnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                            {isConnected ? `${portfolio.totalPnl >= 0 ? '+' : ''}${portfolio.totalPnlPercent.toFixed(2)}%` : "---"}
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
                    className="w-full justify-start text-muted-foreground hover:text-white hover:bg-white/5 h-9"
                >
                    <LogOut className="h-4 w-4 mr-3" />
                    {isLoggingOut ? "Logging out..." : "Logout"}
                </Button>
            </div>
        </div>
    )
}
