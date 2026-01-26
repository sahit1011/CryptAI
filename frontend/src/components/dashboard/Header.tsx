"use client"

import { Bell, Search, LogOut, TrendingUp, TrendingDown } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Input } from "@/components/ui/input"
import { useState, useEffect } from "react"
import { createClient } from "@/utils/supabase/client"
import { useRouter } from "next/navigation"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover"

// Mock trade data - replace with real WebSocket data
const recentTrades = [
    { id: 1, pair: "BTC/USDT", type: "LONG", pnl: 125.50, time: "2 min ago", profit: true },
    { id: 2, pair: "ETH/USDT", type: "SHORT", pnl: -45.20, time: "5 min ago", profit: false },
    { id: 3, pair: "SOL/USDT", type: "LONG", pnl: 89.30, time: "12 min ago", profit: true },
    { id: 4, pair: "BNB/USDT", type: "LONG", pnl: 234.75, time: "18 min ago", profit: true },
    { id: 5, pair: "ADA/USDT", type: "SHORT", pnl: -12.80, time: "25 min ago", profit: false },
]

export function Header() {
    const [userEmail, setUserEmail] = useState<string | null>(null)
    const [isLoggingOut, setIsLoggingOut] = useState(false)
    const router = useRouter()
    const supabase = createClient()

    useEffect(() => {
        const getUser = async () => {
            const { data: { session } } = await supabase.auth.getSession()
            setUserEmail(session?.user?.email || null)
        }
        getUser()
    }, [supabase])

    const handleLogout = async () => {
        setIsLoggingOut(true)
        await supabase.auth.signOut()
        // Use window.location to force full page reload and clear auth state
        window.location.href = "/"
    }

    return (
        <div className="sticky top-0 z-40 flex items-center justify-between px-8 h-16 border-b border-white/5 bg-[#0A0A0A]/80 backdrop-blur-xl">
            <div className="flex items-center gap-4 flex-1">
                {/* Command Search */}
                <div className="relative max-w-md w-full group">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground group-focus-within:text-white transition-colors" />
                    <Input
                        placeholder="Search markets, agents, or commands..."
                        className="pl-10 pr-12 bg-white/5 border-transparent focus:border-white/10 focus:bg-white/10 h-10 text-sm transition-all placeholder:text-muted-foreground/50 rounded-lg"
                    />
                    <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1">
                        <kbd className="pointer-events-none inline-flex h-5 select-none items-center gap-1 rounded border border-white/10 bg-black px-1.5 font-mono text-[10px] font-medium text-muted-foreground opacity-50">
                            <span className="text-xs">⌘</span>K
                        </kbd>
                    </div>
                </div>
            </div>

            <div className="flex items-center gap-4">
                {/* System Status */}
                <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    <span className="text-xs font-medium text-emerald-500">System Operational</span>
                </div>

                <div className="h-4 w-px bg-white/10 mx-2" />

                {/* Live Trades Notifications */}
                <Popover>
                    <PopoverTrigger asChild>
                        <Button variant="ghost" size="icon" className="relative hover:bg-white/5 text-muted-foreground hover:text-white">
                            <Bell className="h-5 w-5" />
                            <span className="absolute top-2.5 right-2.5 w-1.5 h-1.5 bg-emerald-500 rounded-full ring-2 ring-[#0A0A0A]" />
                        </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-80 p-0 bg-[#0A0A0A] border-white/10" align="end">
                        <div className="p-4 border-b border-white/10">
                            <h3 className="font-semibold text-white">Live Trades</h3>
                            <p className="text-xs text-muted-foreground">Recent trading activity</p>
                        </div>
                        <div className="max-h-[400px] overflow-y-auto">
                            {recentTrades.map((trade) => (
                                <div
                                    key={trade.id}
                                    className="p-3 border-b border-white/5 hover:bg-white/5 transition-colors"
                                >
                                    <div className="flex items-start justify-between">
                                        <div className="flex-1">
                                            <div className="flex items-center gap-2">
                                                <span className="text-sm font-medium text-white">{trade.pair}</span>
                                                <span className={`text-xs px-1.5 py-0.5 rounded ${trade.type === "LONG" ? "bg-emerald-500/10 text-emerald-400" : "bg-orange-500/10 text-orange-400"}`}>
                                                    {trade.type}
                                                </span>
                                            </div>
                                            <p className="text-xs text-muted-foreground mt-1">{trade.time}</p>
                                        </div>
                                        <div className={`flex items-center gap-1 ${trade.profit ? "text-emerald-400" : "text-red-400"}`}>
                                            {trade.profit ? (
                                                <TrendingUp className="h-3 w-3" />
                                            ) : (
                                                <TrendingDown className="h-3 w-3" />
                                            )}
                                            <span className="text-sm font-mono font-medium">
                                                {trade.profit ? "+" : ""}${trade.pnl.toFixed(2)}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="p-3 border-t border-white/10">
                            <Button variant="ghost" className="w-full text-sm text-muted-foreground hover:text-white">
                                View all trades
                            </Button>
                        </div>
                    </PopoverContent>
                </Popover>

                {/* User Profile Dropdown */}
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button variant="ghost" className="gap-2 hover:bg-white/5 h-9 pl-2 pr-3 rounded-full border border-transparent hover:border-white/10">
                            <Avatar className="h-6 w-6">
                                <AvatarFallback className="bg-emerald-500/10 text-emerald-400 text-xs">
                                    {userEmail?.charAt(0).toUpperCase() || "U"}
                                </AvatarFallback>
                            </Avatar>
                            <span className="text-sm font-medium hidden md:inline text-muted-foreground group-hover:text-white">
                                {userEmail?.split("@")[0] || "User"}
                            </span>
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent className="w-56 bg-[#0A0A0A] border-white/10" align="end">
                        <DropdownMenuLabel className="text-muted-foreground">
                            <div className="flex flex-col space-y-1">
                                <p className="text-sm font-medium text-white">My Account</p>
                                <p className="text-xs text-muted-foreground truncate">{userEmail}</p>
                            </div>
                        </DropdownMenuLabel>
                        <DropdownMenuSeparator className="bg-white/10" />
                        <DropdownMenuItem
                            onClick={handleLogout}
                            disabled={isLoggingOut}
                            className="text-red-400 focus:text-red-400 focus:bg-red-500/10 cursor-pointer"
                        >
                            <LogOut className="mr-2 h-4 w-4" />
                            <span>{isLoggingOut ? "Logging out..." : "Logout"}</span>
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>
            </div>
        </div>
    )
}
