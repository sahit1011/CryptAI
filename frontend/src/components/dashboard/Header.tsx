"use client"

import { Bell, Search, LogOut, Menu } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { PnL } from "@/components/ui/value"
import { ConnectionStatus } from "@/components/ui/connection-status"
import { useState, useEffect } from "react"
import { createClient } from "@/utils/supabase/client"
import { useStore } from "@/store/useStore"
import { useMarketStore } from "@/hooks/useMarketData"
import { AccountChip } from "./ui/AccountChip"
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

export function Header({ onMenuClick }: { onMenuClick?: () => void }) {
    const [userEmail, setUserEmail] = useState<string | null>(null)
    const [isLoggingOut, setIsLoggingOut] = useState(false)
    const supabase = createClient()

    // Real recent trades from the store (closed history first, then open
    // positions). Never fabricated — if the store is empty we show an honest
    // "no activity" line in the notifications popover.
    const { tradeHistory, activeTrades, currency, setCurrency } = useStore()
    const { status } = useMarketStore()

    const recentTrades = [...tradeHistory, ...activeTrades].slice(0, 5).map((trade) => ({
        id: trade.id,
        pair: trade.symbol,
        side: trade.side,
        pnl: trade.pnl ?? 0,
        time:
            trade.exitTime || trade.entryTime
                ? new Date(trade.exitTime || trade.entryTime!).toLocaleTimeString()
                : trade.status === "OPEN"
                    ? "Open"
                    : "",
    }))

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
        // Force a full reload to clear auth state.
        window.location.href = "/"
    }

    return (
        <div className="sticky top-0 z-40 flex h-16 items-center justify-between border-b border-border bg-background/80 px-6 backdrop-blur-xl">
            {/* Mobile menu button — opens the sidebar drawer (hidden once the
                persistent sidebar shows at md). */}
            {onMenuClick ? (
                <Button
                    variant="ghost"
                    size="icon"
                    className="-ml-2 mr-1 md:hidden"
                    onClick={onMenuClick}
                    aria-label="Open navigation menu"
                >
                    <Menu className="h-5 w-5" />
                </Button>
            ) : null}

            {/* Command search (decorative for now; collapse on phones to save space) */}
            <div className="hidden flex-1 items-center gap-4 sm:flex">
                <div className="group relative w-full max-w-md">
                    <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle-foreground transition-colors group-focus-within:text-foreground" />
                    <Input
                        placeholder="Search markets, agents, or commands…"
                        className="h-9 rounded-md pl-9 pr-12"
                    />
                    <kbd className="num pointer-events-none absolute right-3 top-1/2 inline-flex h-5 -translate-y-1/2 select-none items-center gap-1 rounded border border-border bg-elevated px-1.5 text-[10px] font-medium text-subtle-foreground">
                        ⌘K
                    </kbd>
                </div>
            </div>

            <div className="flex items-center gap-3">
                {/* Which account am I looking at — chrome, never a menu. */}
                <AccountChip />

                {/* Currency toggle — values are USD internally; user picks display ($/₹) */}
                <div className="flex items-center rounded-md border border-border bg-elevated/40 p-0.5" role="group" aria-label="Display currency">
                    {(["USD", "INR"] as const).map((c) => (
                        <button
                            key={c}
                            onClick={() => setCurrency(c)}
                            aria-pressed={currency === c}
                            aria-label={c === "USD" ? "Show values in US Dollars" : "Show values in Indian Rupees"}
                            className={
                                "num size-6 rounded text-sm font-semibold leading-none transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 " +
                                (currency === c
                                    ? "bg-accent-muted text-accent"
                                    : "text-subtle-foreground hover:text-foreground")
                            }
                            title={c === "USD" ? "Show values in US Dollars" : "Show values in Indian Rupees"}
                        >
                            {c === "USD" ? "$" : "₹"}
                        </button>
                    ))}
                </div>

                {/* Live feed status — driven by the real WS connection */}
                <ConnectionStatus status={status} className="hidden md:inline-flex" />

                <div className="mx-1 hidden h-4 w-px bg-border md:block" />

                {/* Recent trades notifications */}
                <Popover>
                    <PopoverTrigger asChild>
                        <Button variant="ghost" size="icon" className="relative" aria-label="Recent trade notifications">
                            <Bell className="h-5 w-5" />
                            {recentTrades.length > 0 && (
                                <span className="absolute right-2.5 top-2.5 size-1.5 rounded-full bg-accent ring-2 ring-background" />
                            )}
                        </Button>
                    </PopoverTrigger>
                    <PopoverContent
                        className="w-80 border-border bg-surface p-0"
                        align="end"
                    >
                        <div className="border-b border-border px-4 py-3">
                            <h3 className="text-sm font-semibold text-foreground">
                                Recent Trades
                            </h3>
                            <p className="text-xs text-muted-foreground">
                                Latest trading activity
                            </p>
                        </div>
                        <div className="scroll-terminal max-h-[400px] overflow-y-auto">
                            {recentTrades.length === 0 ? (
                                <div className="px-4 py-6 text-center text-xs text-muted-foreground">
                                    No recent trading activity yet
                                </div>
                            ) : (
                                recentTrades.map((trade) => (
                                    <div
                                        key={trade.id}
                                        className="flex items-start justify-between border-b border-border/60 px-4 py-3 transition-colors hover:bg-elevated/40"
                                    >
                                        <div className="flex-1">
                                            <div className="flex items-center gap-2">
                                                <span className="num text-sm font-medium text-foreground">
                                                    {trade.pair || "—"}
                                                </span>
                                                <Badge
                                                    variant={trade.side === "LONG" ? "profit" : "warning"}
                                                    className="px-1.5 py-0 text-[10px]"
                                                >
                                                    {trade.side}
                                                </Badge>
                                            </div>
                                            <p className="num mt-1 text-xs text-subtle-foreground">
                                                {trade.time}
                                            </p>
                                        </div>
                                        <PnL
                                            value={trade.pnl}
                                            money
                                            className="text-sm font-medium"
                                        />
                                    </div>
                                ))
                            )}
                        </div>
                    </PopoverContent>
                </Popover>

                {/* User profile */}
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button
                            variant="ghost"
                            className="h-9 gap-2 rounded-full border border-transparent pl-1.5 pr-3 hover:border-border"
                        >
                            <Avatar className="size-6">
                                <AvatarFallback className="bg-accent-muted text-xs text-accent-300">
                                    {userEmail?.charAt(0).toUpperCase() || "U"}
                                </AvatarFallback>
                            </Avatar>
                            <span className="hidden text-sm font-medium text-muted-foreground md:inline">
                                {userEmail?.split("@")[0] || "User"}
                            </span>
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent
                        className="w-56 border-border bg-surface"
                        align="end"
                    >
                        <DropdownMenuLabel>
                            <div className="flex flex-col space-y-1">
                                <p className="text-sm font-medium text-foreground">
                                    My Account
                                </p>
                                <p className="truncate text-xs text-muted-foreground">
                                    {userEmail || "—"}
                                </p>
                            </div>
                        </DropdownMenuLabel>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                            onClick={handleLogout}
                            disabled={isLoggingOut}
                            className="cursor-pointer text-loss focus:bg-loss-muted focus:text-loss"
                        >
                            <LogOut className="mr-2 h-4 w-4" />
                            <span>{isLoggingOut ? "Logging out…" : "Logout"}</span>
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>
            </div>
        </div>
    )
}
