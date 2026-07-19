"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useTerminalStore, DOCK_MAX, DOCK_DEFAULT, type DockTab } from "@/store/useTerminalStore"
import { useStore } from "@/store/useStore"
import { INTERVALS } from "@/lib/chart/klines"
import { HeaderBar } from "./HeaderBar"
import { DrawingRail } from "./DrawingRail"
import { ChartPanel } from "./ChartPanel"
import { OrderBookPanel } from "./OrderBookPanel"
import { TradeTicket } from "./TradeTicket"
import { Dock } from "./Dock"
import { WireStrip } from "./WireStrip"
import { FooterStrip } from "./FooterStrip"
import { ShortcutsSheet } from "./ShortcutsSheet"
import { cn } from "@/lib/utils"

/*
 * TerminalShell — THE DESK's zone map.
 *
 *   header 44px  ─────────────────────────────────────────────
 *   rail 40px │ chart column (toolbar/chart/wire/dock) │ 324px
 *   footer 28px ─────────────────────────────────────────────
 *
 * Every seam is a 1px hairline; no drop shadows in the workspace. Only the
 * chart is 2-axis fluid; only the dock height is user-resizable. Below lg the
 * desk stacks: chart on top, one panel at a time behind a tab strip.
 */

const MOBILE_TABS: { id: DockTab | "ticket" | "book"; label: string }[] = [
    { id: "ticket", label: "Ticket" },
    { id: "book", label: "Book" },
    { id: "positions", label: "Positions" },
    { id: "history", label: "History" },
    { id: "setups", label: "AI" },
    { id: "wire", label: "Wire" },
]

function useIsDesktop(): boolean | null {
    const [isDesktop, setIsDesktop] = useState<boolean | null>(null)
    useEffect(() => {
        const mq = window.matchMedia("(min-width: 1024px)")
        const update = () => setIsDesktop(mq.matches)
        update()
        mq.addEventListener("change", update)
        return () => mq.removeEventListener("change", update)
    }, [])
    return isDesktop
}

export function TerminalShell() {
    const isDesktop = useIsDesktop()
    const [isShortcutsOpen, setShortcutsOpen] = useState(false)
    const [mobileTab, setMobileTab] = useState<(typeof MOBILE_TABS)[number]["id"]>("ticket")

    // --- Keyboard map (desktop; suppressed while typing / dialogs open) ------
    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            const target = e.target as HTMLElement | null
            if (
                target &&
                (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable ||
                    target.closest("[role=dialog]"))
            ) {
                if (e.key === "Escape") (target as HTMLInputElement).blur?.()
                return
            }
            const s = useTerminalStore.getState()

            if (e.key === "?" && e.shiftKey) { e.preventDefault(); setShortcutsOpen((v) => !v); return }
            if (e.key === "/") { e.preventDefault(); document.getElementById("symbol-switcher")?.click(); return }
            if (e.key === "`") { e.preventDefault(); s.toggleDockCollapsed(); return }

            const tfIndex = Number(e.key) - 1
            if (tfIndex >= 0 && tfIndex < INTERVALS.length && !e.metaKey && !e.ctrlKey) {
                s.setInterval(INTERVALS[tfIndex].id)
                return
            }
            const tabKeys: Record<string, DockTab> = { p: "positions", o: "orders", h: "history", a: "setups", w: "wire" }
            if (tabKeys[e.key]) { s.setDockTab(tabKeys[e.key]); return }

            if (e.key === "t") {
                e.preventDefault()
                document.getElementById("ticket-entry")?.focus()
                return
            }
            if (e.key === "f") {
                // Plot the newest setup for the active symbol (ChartPanel reacts to the id).
                const signal = useStore.getState().signals.find((sig) => sig.symbol === s.symbol)
                if (signal) s.setPlottedSignalId(signal.id)
                return
            }
            if (e.key === "x") {
                s.setPlottedSignalId(null)
                return
            }
            // Esc while drawing is handled by klinecharts' built-in hotkeys (v10).
        }
        window.addEventListener("keydown", onKey)
        return () => window.removeEventListener("keydown", onKey)
    }, [])

    if (isDesktop === null) {
        // First client frame: match the desktop shell's chrome so there's no flash.
        return <div className="flex h-full flex-col bg-background" />
    }

    return (
        <div className="flex h-full flex-col bg-background">
            <HeaderBar />

            {isDesktop ? <DesktopWorkspace /> : <MobileWorkspace tab={mobileTab} onTab={setMobileTab} />}

            <FooterStrip />
            <ShortcutsSheet open={isShortcutsOpen} onOpenChange={setShortcutsOpen} />
        </div>
    )
}

/* ---------------------------------- Desktop -------------------------------- */

function DesktopWorkspace() {
    const dockHeight = useTerminalStore((s) => s.dockHeight)
    const isDockCollapsed = useTerminalStore((s) => s.isDockCollapsed)
    const setDockHeight = useTerminalStore((s) => s.setDockHeight)

    // Dock resize: pointer-drag on the 4px seam, zero transitions (tracks pointer).
    const dragState = useRef<{ startY: number; startH: number } | null>(null)
    const onSeamPointerDown = useCallback((e: React.PointerEvent) => {
        e.preventDefault()
        dragState.current = { startY: e.clientY, startH: useTerminalStore.getState().dockHeight }
        const onMove = (ev: PointerEvent) => {
            const d = dragState.current
            if (!d) return
            setDockHeight(d.startH + (d.startY - ev.clientY))
        }
        const onUp = () => {
            dragState.current = null
            window.removeEventListener("pointermove", onMove)
            window.removeEventListener("pointerup", onUp)
        }
        window.addEventListener("pointermove", onMove)
        window.addEventListener("pointerup", onUp)
    }, [setDockHeight])

    const onSeamDoubleClick = useCallback(() => {
        const h = useTerminalStore.getState().dockHeight
        setDockHeight(h >= DOCK_MAX - 8 ? DOCK_DEFAULT : DOCK_MAX)
    }, [setDockHeight])

    return (
        <div className="flex min-h-0 flex-1 border-t border-border">
            <DrawingRail />

            {/* Chart column: toolbar+chart / wire strip / dock. */}
            <div className="flex min-w-0 flex-1 flex-col border-l border-border">
                <div className="min-h-0 flex-1">
                    <ChartPanel />
                </div>

                <WireStrip />

                {/* Dock resize seam — hairline that strengthens on hover. */}
                <div
                    role="separator"
                    aria-orientation="horizontal"
                    aria-label="Resize dock"
                    onPointerDown={onSeamPointerDown}
                    onDoubleClick={onSeamDoubleClick}
                    className="h-1 shrink-0 cursor-row-resize border-t border-border transition-colors duration-150 hover:border-border-strong hover:bg-elevated"
                />

                <div
                    style={{ height: isDockCollapsed ? 28 : dockHeight }}
                    className={cn("shrink-0", isDockCollapsed && "overflow-hidden")}
                >
                    <Dock collapsed={isDockCollapsed} />
                </div>
            </div>

            {/* Right rail: order book over trade ticket — always simultaneously visible. */}
            <aside className="flex w-[324px] shrink-0 flex-col border-l border-border bg-surface">
                <div className="min-h-0 flex-1">
                    <OrderBookPanel />
                </div>
                <div className="shrink-0 border-t border-border">
                    <TradeTicket />
                </div>
            </aside>
        </div>
    )
}

/* ---------------------------------- Mobile --------------------------------- */

function MobileWorkspace({
    tab,
    onTab,
}: {
    tab: (typeof MOBILE_TABS)[number]["id"]
    onTab: (t: (typeof MOBILE_TABS)[number]["id"]) => void
}) {
    return (
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto border-t border-border">
            <div className="h-[56vh] min-h-[380px] shrink-0">
                <ChartPanel />
            </div>

            {/* One panel at a time behind a tab strip. */}
            <div className="sticky top-0 z-10 flex shrink-0 items-center gap-0 overflow-x-auto border-y border-border bg-surface">
                {MOBILE_TABS.map((t) => (
                    <button
                        key={t.id}
                        onClick={() => onTab(t.id)}
                        className={cn(
                            "shrink-0 px-3.5 py-2 text-xs font-medium transition-colors duration-150",
                            tab === t.id ? "bg-elevated text-foreground" : "text-muted-foreground hover:text-foreground",
                        )}
                    >
                        {t.label}
                    </button>
                ))}
            </div>

            <div className="min-h-0 flex-1 bg-surface">
                {tab === "ticket" && <TradeTicket />}
                {tab === "book" && <div className="h-[440px]"><OrderBookPanel /></div>}
                {(tab === "positions" || tab === "orders" || tab === "history" || tab === "setups" || tab === "wire") && (
                    <div className="h-[440px]">
                        <Dock collapsed={false} forcedTab={tab} />
                    </div>
                )}
            </div>
        </div>
    )
}
