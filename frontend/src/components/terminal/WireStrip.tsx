"use client"

import { useStore } from "@/store/useStore"
import { useTerminalStore } from "@/store/useTerminalStore"

/*
 * WireStrip — 28px under the chart: the single newest agent dispatch, so the
 * AI never disappears behind a dock tab. Click opens the full Wire.
 */
export function WireStrip() {
    const newest = useStore((s) => s.agentLogs[0])
    const setDockTab = useTerminalStore((s) => s.setDockTab)

    return (
        <button
            onClick={() => setDockTab("wire")}
            title="Open the Wire"
            className="flex h-7 shrink-0 items-center gap-2.5 border-t border-border bg-surface px-3 text-left transition-colors duration-150 hover:bg-elevated"
        >
            <span className="label-md shrink-0 text-subtle-foreground">The Wire</span>
            {newest ? (
                <>
                    <span className="num shrink-0 text-[10px] text-subtle-foreground">{newest.timestamp}</span>
                    <span className="label-md shrink-0 text-accent-300">{newest.agent}</span>
                    <span className="min-w-0 flex-1 truncate text-[11px] text-muted-foreground">{newest.message}</span>
                </>
            ) : (
                <span className="text-[11px] text-subtle-foreground">quiet — dispatches stream here while the engine runs</span>
            )}
        </button>
    )
}
