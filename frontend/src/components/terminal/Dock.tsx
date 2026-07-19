"use client"

import { useMemo } from "react"
import { PnL } from "@/components/ui/value"
import { useStore } from "@/store/useStore"
import { useTerminalStore, type DockTab } from "@/store/useTerminalStore"
import { PositionsTable } from "./PositionsTable"
import { OpenOrdersTab } from "./OpenOrdersTab"
import { HistoryTab } from "./HistoryTab"
import { SetupCards } from "./SetupCards"
import { WireFeed, AgentLivenessChips } from "./WireFeed"
import { cn } from "@/lib/utils"

/*
 * Dock — the workspace's bottom drawer: Positions · Orders · History ·
 * AI Setups · Wire. Height is user-resizable (the seam lives in the shell);
 * the tab strip is 28px; content scrolls inside.
 */

const TABS: { id: DockTab; label: string }[] = [
    { id: "positions", label: "Positions" },
    { id: "orders", label: "Orders" },
    { id: "history", label: "History" },
    { id: "setups", label: "AI Setups" },
    { id: "wire", label: "Wire" },
]

export function Dock({
    collapsed,
    forcedTab,
    hideSetups = false,
}: {
    collapsed: boolean
    forcedTab?: DockTab
    /** Wide layout promotes AI setups to the command rail — drop the tab here. */
    hideSetups?: boolean
}) {
    const storeTab = useTerminalStore((s) => s.dockTab)
    const setDockTab = useTerminalStore((s) => s.setDockTab)
    const activeTrades = useStore((s) => s.activeTrades)
    const portfolioMode = useStore((s) => s.portfolio.mode)

    let tab = forcedTab ?? storeTab
    if (hideSetups && tab === "setups") tab = "positions"
    const openCount = activeTrades.filter((t) => t.status === "OPEN").length
    const netUpnl = useMemo(
        () => activeTrades.reduce((acc, t) => (t.status === "OPEN" ? acc + (t.pnl || 0) : acc), 0),
        [activeTrades],
    )

    return (
        <div className="flex h-full flex-col bg-surface">
            <div className="flex h-7 shrink-0 items-center border-b border-border">
                {(forcedTab
                    ? TABS.filter((t) => t.id === forcedTab)
                    : hideSetups ? TABS.filter((t) => t.id !== "setups") : TABS
                ).map((t) => (
                    <button
                        key={t.id}
                        onClick={() => setDockTab(t.id)}
                        className={cn(
                            "flex h-full items-center gap-1.5 px-3 text-[11px] font-medium transition-colors duration-150",
                            tab === t.id ? "bg-elevated text-foreground" : "text-muted-foreground hover:text-foreground",
                        )}
                    >
                        {t.label}
                        {t.id === "positions" && openCount > 0 && (
                            <span className="flex items-center gap-1">
                                <span className="num rounded-sm bg-muted px-1 text-[10px] text-foreground">{openCount}</span>
                                <PnL className="text-[10px]" value={netUpnl} money decimals={0} />
                            </span>
                        )}
                        {t.id === "positions" && portfolioMode === "paper" && (
                            <span className="rounded-sm border border-info/30 bg-info-muted px-1 py-px text-[9px] font-medium uppercase tracking-wider text-info">
                                paper
                            </span>
                        )}
                        {t.id === "wire" && <AgentLivenessChips />}
                    </button>
                ))}
            </div>

            {!collapsed && (
                <div className="min-h-0 flex-1 overflow-y-auto scroll-terminal">
                    {tab === "positions" && <PositionsTable />}
                    {tab === "orders" && <OpenOrdersTab />}
                    {tab === "history" && <HistoryTab />}
                    {tab === "setups" && <SetupCards />}
                    {tab === "wire" && <WireFeed />}
                </div>
            )}
        </div>
    )
}
