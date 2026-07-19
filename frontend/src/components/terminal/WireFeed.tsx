"use client"

import { useEffect, useState } from "react"
import { EmptyState } from "@/components/ui/states"
import { useStore, type AgentLog } from "@/store/useStore"
import { getEngine } from "@/lib/api"
import { cn } from "@/lib/utils"

/*
 * The Wire — the agents' tape as bylined dispatches: mono timestamp · agent
 * byline · message. Severity tones the BYLINE only; EXECUTION rows carry a
 * hairline-left in accent-300 (structural crimson, one purpose). Newest first.
 */

const AGENTS = ["DATA", "ANALYSIS", "STRATEGY", "RISK", "EXECUTION"] as const
const LIVE_WINDOW_MS = 60_000

const BYLINE_TONE: Record<AgentLog["agent"], string> = {
    DATA: "text-info",
    ANALYSIS: "text-accent-300",
    STRATEGY: "text-warning",
    RISK: "text-loss",
    EXECUTION: "text-profit",
}

export function WireFeed() {
    const agentLogs = useStore((s) => s.agentLogs)
    const [isEngineOn, setEngineOn] = useState<boolean | null>(null)

    useEffect(() => {
        let stopped = false
        getEngine().then((e) => { if (!stopped) setEngineOn(e.enabled) }).catch(() => { })
        return () => { stopped = true }
    }, [])

    if (agentLogs.length === 0) {
        return (
            <EmptyState
                title="The Wire is quiet"
                description={isEngineOn === false
                    ? "Engine off — dispatches resume when an admin arms it."
                    : "Agent dispatches stream here live: data syncs, analysis calls, risk verdicts, executions."}
            />
        )
    }

    return (
        <div className="flex flex-col">
            {isEngineOn === false && (
                <p className="border-b border-border px-3 py-1.5 text-[11px] text-subtle-foreground">
                    Engine off — this is the last session&apos;s tape.
                </p>
            )}
            <div className="divide-y divide-border/60">
                {agentLogs.map((log) => (
                    <div
                        key={log.id}
                        className={cn(
                            "flex items-baseline gap-2.5 px-3 py-[5px]",
                            // Execution dispatches carry the tape's one structural crimson
                            // mark: a true 1px hairline, per the design system's hairline law.
                            log.agent === "EXECUTION" && "border-l border-l-accent-300/70",
                        )}
                    >
                        <span className="num shrink-0 text-[10px] text-subtle-foreground">{log.timestamp}</span>
                        <span className={cn(
                            "label-md w-20 shrink-0",
                            log.severity === "warning" ? "text-warning" : log.severity === "error" ? "text-loss" : BYLINE_TONE[log.agent],
                        )}>
                            {log.agent}
                        </span>
                        <span className="min-w-0 flex-1 text-xs leading-snug text-muted-foreground">{log.message}</span>
                    </div>
                ))}
            </div>
        </div>
    )
}

/**
 * Five 2-char agent chips whose dots brighten when that agent dispatched within
 * the last 60s — liveness at a glance, on the Wire tab header.
 */
export function AgentLivenessChips() {
    const agentLogs = useStore((s) => s.agentLogs)
    // Wall-clock in state (render purity); decays liveness even without new logs.
    const [now, setNow] = useState(0)

    useEffect(() => {
        const t = setTimeout(() => setNow(Date.now()), 0)
        const id = setInterval(() => setNow(Date.now()), 15_000)
        return () => { clearTimeout(t); clearInterval(id) }
    }, [])
    const liveAgents = new Set<string>()
    for (const log of agentLogs) {
        // timestamps are locale strings; approximate liveness by list recency —
        // the newest 100 logs are session-scoped, so index-0 freshness is enough.
        if (liveAgents.size === AGENTS.length) break
        const t = Date.parse(`${new Date(now).toDateString()} ${log.timestamp}`)
        if (Number.isFinite(t) && now - t < LIVE_WINDOW_MS) liveAgents.add(log.agent)
        else break // logs are newest-first: once stale, the rest are staler
    }

    return (
        <span className="flex items-center gap-1">
            {AGENTS.map((a) => (
                <span key={a} className="flex items-center gap-px" title={`${a} ${liveAgents.has(a) ? "active <60s" : "idle"}`}>
                    <span className={cn(
                        "size-1 rounded-full",
                        liveAgents.has(a) ? "bg-profit" : "bg-muted",
                    )} />
                    <span className="text-[8px] uppercase text-subtle-foreground">{a.slice(0, 2)}</span>
                </span>
            ))}
        </span>
    )
}
