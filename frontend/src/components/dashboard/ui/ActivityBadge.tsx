"use client"

import { useEffect, useState } from "react"
import { API_URL } from "@/lib/api"
import { describeActivity, type ActivityDisplay, type ActivityTone, type PulseResponse } from "@/lib/pulse"
import { cn } from "@/lib/utils"

/*
 * ActivityBadge — "how active is this hour, historically?" plus live conditions.
 *
 * Shared by the desk (the route a new user lands on) and the chart footer. It was
 * originally only in the terminal footer, which meant the market-activity signal the
 * product promises was two nav clicks away from the landing page and invisible below
 * the md breakpoint — shipped but unreachable.
 *
 * Every honesty rule lives in lib/pulse.ts (tested there): past tense, sourced, and
 * an unavailable signal plane renders as UNKNOWN rather than as a calm market. This
 * component only renders what describeActivity returns.
 */

const PULSE_POLL_MS = 60_000

const TONE: Record<ActivityTone, { dot: string; text: string }> = {
    peak: { dot: "bg-profit", text: "text-profit" },
    active: { dot: "bg-info", text: "text-info" },
    quiet: { dot: "bg-muted-foreground", text: "text-muted-foreground" },
    neutral: { dot: "bg-muted-foreground/50", text: "text-subtle-foreground" },
}

export function useActivity(): ActivityDisplay | null {
    const [display, setDisplay] = useState<ActivityDisplay | null>(null)

    useEffect(() => {
        let cancelled = false
        const load = async () => {
            try {
                const r = await fetch(`${API_URL}/api/pulse`, { cache: "no-store" })
                const body = r.ok ? ((await r.json()) as PulseResponse) : null
                if (!cancelled) setDisplay(describeActivity(body))
            } catch {
                if (!cancelled) setDisplay(describeActivity(null))
            }
        }
        const t = setTimeout(load, 0)
        const id = setInterval(load, PULSE_POLL_MS)
        return () => { cancelled = true; clearTimeout(t); clearInterval(id) }
    }, [])

    return display
}

/** Full-width card for the desk. */
export function ActivityBadge() {
    const a = useActivity()
    if (!a) return null
    return (
        <div
            className="flex items-center gap-3 rounded-xl border border-border bg-surface px-4 py-3"
            title={a.title}
        >
            <span className={cn("size-2 shrink-0 rounded-full", TONE[a.tone].dot)} />
            <div className="min-w-0">
                <p className="body-sm text-foreground">
                    Market activity this hour:{" "}
                    <span className={cn("font-medium", TONE[a.tone].text)}>{a.rank}</span>
                    <span className="text-subtle-foreground"> historically</span>
                    {a.live && <span className="text-subtle-foreground"> · {a.live}</span>}
                </p>
                <p className="label-md text-subtle-foreground">
                    Measured from past data, not a forecast — hover for the sample.
                </p>
            </div>
        </div>
    )
}
