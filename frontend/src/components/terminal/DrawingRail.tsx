"use client"

import { useEffect, useState } from "react"
import {
    MousePointer2, Minus, MoveUpRight, TrendingUp, Tag, Rows3, AudioWaveform,
    Brush, MessageSquareText, Magnet, Repeat2, Eraser,
} from "lucide-react"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { getChart, onChartReady } from "@/lib/chart/chartHandle"
import { useTerminalStore } from "@/store/useTerminalStore"
import { cn } from "@/lib/utils"

/*
 * DrawingRail — 40px tool rail. Arms a klinecharts overlay for interactive
 * drawing under groupId 'user-draw'; the eraser clears ONLY that group (AI
 * levels and position lines are never touched). Magnet + continuous-draw are
 * sticky toggles, persisted with the workspace.
 */

const USER_DRAW_GROUP = "user-draw"

const TOOLS: { name: string; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { name: "segment", label: "Trend line", icon: TrendingUp },
    { name: "rayLine", label: "Ray", icon: MoveUpRight },
    { name: "horizontalStraightLine", label: "Horizontal line", icon: Minus },
    { name: "priceLine", label: "Price line", icon: Tag },
    { name: "priceChannelLine", label: "Price channel", icon: Rows3 },
    { name: "fibonacciLine", label: "Fibonacci", icon: AudioWaveform },
    { name: "brush", label: "Brush", icon: Brush },
    { name: "simpleAnnotation", label: "Annotation", icon: MessageSquareText },
]

export function DrawingRail() {
    const [isReady, setReady] = useState(false)
    const [activeTool, setActiveTool] = useState<string | null>(null)
    const isMagnetOn = useTerminalStore((s) => s.isMagnetOn)
    const toggleMagnet = useTerminalStore((s) => s.toggleMagnet)
    const isContinuous = useTerminalStore((s) => s.isContinuousDrawing)
    const toggleContinuous = useTerminalStore((s) => s.toggleContinuousDrawing)

    useEffect(() => onChartReady(setReady), [])

    const arm = (name: string) => {
        const chart = getChart()
        if (!chart) return
        setActiveTool(name)
        chart.createOverlay({
            name,
            groupId: USER_DRAW_GROUP,
            mode: isMagnetOn ? "weak_magnet" : "normal",
            onDrawEnd: () => {
                if (useTerminalStore.getState().isContinuousDrawing) {
                    // Re-arm the same tool on the next frame (continuous drawing).
                    setTimeout(() => arm(name), 0)
                } else {
                    setActiveTool(null)
                }
                return false
            },
        })
    }

    const clearDrawings = () => {
        getChart()?.removeOverlay({ groupId: USER_DRAW_GROUP })
        setActiveTool(null)
    }

    return (
        <div className="flex w-10 shrink-0 flex-col items-center gap-0.5 bg-surface py-1.5">
            <RailButton
                label="Select / pan"
                active={activeTool === null}
                disabled={!isReady}
                onClick={() => setActiveTool(null)}
            >
                <MousePointer2 className="size-3.5" />
            </RailButton>

            <div className="my-1 h-px w-6 bg-border" aria-hidden />

            {TOOLS.map((t) => (
                <RailButton key={t.name} label={t.label} active={activeTool === t.name} disabled={!isReady} onClick={() => arm(t.name)}>
                    <t.icon className="size-3.5" />
                </RailButton>
            ))}

            <div className="my-1 h-px w-6 bg-border" aria-hidden />

            <RailButton label={`Magnet ${isMagnetOn ? "on" : "off"} — snap to OHLC`} active={isMagnetOn} disabled={!isReady} onClick={toggleMagnet}>
                <Magnet className="size-3.5" />
            </RailButton>
            <RailButton label={`Continuous drawing ${isContinuous ? "on" : "off"}`} active={isContinuous} disabled={!isReady} onClick={toggleContinuous}>
                <Repeat2 className="size-3.5" />
            </RailButton>

            <div className="mt-auto" />

            <Popover>
                <PopoverTrigger asChild>
                    <button
                        title="Clear my drawings"
                        disabled={!isReady}
                        className="flex size-8 items-center justify-center rounded-md text-subtle-foreground transition-colors duration-150 hover:bg-elevated hover:text-loss disabled:opacity-40"
                    >
                        <Eraser className="size-3.5" />
                    </button>
                </PopoverTrigger>
                <PopoverContent side="right" className="w-56 p-3">
                    <p className="mb-2 text-xs text-foreground">Clear all your drawings?</p>
                    <p className="mb-3 text-[11px] text-muted-foreground">
                        Only removes what you drew — AI levels and position lines stay.
                    </p>
                    <button
                        onClick={clearDrawings}
                        className="w-full rounded-md border border-loss/30 bg-loss/10 py-1.5 text-xs font-medium text-loss transition-colors duration-150 hover:bg-loss/20"
                    >
                        Clear drawings
                    </button>
                </PopoverContent>
            </Popover>
        </div>
    )
}

function RailButton({
    label, active, disabled, onClick, children,
}: {
    label: string
    active: boolean
    disabled: boolean
    onClick: () => void
    children: React.ReactNode
}) {
    return (
        <button
            title={label}
            aria-label={label}
            disabled={disabled}
            onClick={onClick}
            className={cn(
                "flex size-8 items-center justify-center rounded-md transition-colors duration-150 disabled:opacity-40",
                active ? "bg-accent-muted text-accent-400" : "text-subtle-foreground hover:bg-elevated hover:text-foreground",
            )}
        >
            {children}
        </button>
    )
}
