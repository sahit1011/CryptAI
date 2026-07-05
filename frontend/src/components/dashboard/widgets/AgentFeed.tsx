"use client"

import { useRef, useEffect } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { EmptyState } from "@/components/ui/states"
import { ConnectionStatus } from "@/components/ui/connection-status"
import { useStore } from "@/store/useStore"
import { useMarketStore } from "@/hooks/useMarketData"
import { cn } from "@/lib/utils"
import { Terminal } from "lucide-react"
import type { AgentLog } from "@/store/useStore"

/*
 * Agent Feed — the terminal's log stream. Real agent activity flows in from the
 * WS (agent_activity / agent_update) into the zustand store; nothing is faked.
 * When there are no events we render an honest EmptyState. The live pill is
 * driven by the actual WS connection status.
 *
 * Timestamps + message text use monospace so the stream reads like a terminal.
 * Agents/severities map to semantic tokens only (emerald / red / amber / blue).
 */

// Each agent maps to one of the chart/semantic hues — no raw tailwind colors.
const AGENT_BADGE: Record<AgentLog["agent"], string> = {
    DATA: "bg-info-muted text-info",
    ANALYSIS: "bg-accent-muted text-accent-300",
    STRATEGY: "bg-warning-muted text-warning",
    RISK: "bg-loss-muted text-loss",
    EXECUTION: "bg-profit-muted text-profit",
}

// Severity tints the message text against the neutral default.
const SEVERITY_TEXT: Record<AgentLog["severity"], string> = {
    success: "text-profit",
    warning: "text-warning",
    error: "text-loss",
    info: "text-foreground",
}

export function AgentFeed() {
    const { agentLogs } = useStore()
    const { status } = useMarketStore()
    const scrollRef = useRef<HTMLDivElement>(null)

    // Auto-scroll to the newest entry as logs stream in (real terminal behavior).
    useEffect(() => {
        const viewport = scrollRef.current?.querySelector(
            "[data-radix-scroll-area-viewport]",
        )
        if (viewport) {
            viewport.scrollTo({ top: viewport.scrollHeight, behavior: "smooth" })
        }
    }, [agentLogs])

    return (
        <div className="flex h-[500px] flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-[var(--shadow-elevation-low)]">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-border bg-elevated/40 px-4 py-3">
                <div className="flex items-center gap-2">
                    <Terminal className="h-4 w-4 text-subtle-foreground" />
                    <h3 className="text-sm font-semibold tracking-tight text-foreground">
                        Agent Feed
                    </h3>
                    <span className="num text-xs text-subtle-foreground">
                        {agentLogs.length} events
                    </span>
                </div>
                <ConnectionStatus status={status} />
            </div>

            {/* Stream */}
            <ScrollArea className="scroll-terminal flex-1" ref={scrollRef}>
                {agentLogs.length === 0 ? (
                    <EmptyState
                        icon={<Terminal />}
                        title="Waiting for agent activity"
                        description="Autonomous trading cycles run on the backend. Live agent decisions will stream here as they happen."
                    />
                ) : (
                    <div className="divide-y divide-border/60">
                        {agentLogs.map((log) => (
                            <div
                                key={log.id}
                                className="flex items-start gap-3 px-4 py-2 text-sm transition-colors hover:bg-elevated/40 animate-fade-in"
                            >
                                <span className="num mt-0.5 min-w-[64px] text-xs text-subtle-foreground">
                                    {log.timestamp}
                                </span>
                                <Badge
                                    className={cn(
                                        "num min-w-[84px] justify-center border-transparent px-2 py-0.5 text-[10px] font-medium",
                                        AGENT_BADGE[log.agent],
                                    )}
                                >
                                    {log.agent}
                                </Badge>
                                <span
                                    className={cn(
                                        "flex-1 leading-relaxed",
                                        SEVERITY_TEXT[log.severity] ?? "text-foreground",
                                    )}
                                >
                                    {log.message}
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </ScrollArea>
        </div>
    )
}
