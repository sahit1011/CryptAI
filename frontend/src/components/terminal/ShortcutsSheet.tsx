"use client"

import {
    Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"

/*
 * ShortcutsSheet — Shift+? reference. Deliberately no buy/sell hotkeys:
 * order placement always goes through the ticket's confirm contract.
 */

const GROUPS: { title: string; rows: [string, string][] }[] = [
    {
        title: "Market",
        rows: [
            ["/", "Switch symbol"],
            ["1 – 6", "Timeframe (5m → 1d)"],
            ["i", "Indicators"],
        ],
    },
    {
        title: "AI",
        rows: [
            ["f", "Plot newest setup"],
            ["x", "Clear plotted setup"],
        ],
    },
    {
        title: "Workspace",
        rows: [
            ["t", "Focus trade ticket"],
            ["p / o / h / a / w", "Dock tabs"],
            ["`", "Collapse dock"],
            ["Esc", "Cancel drawing / close"],
        ],
    },
]

export function ShortcutsSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-sm">
                <DialogHeader>
                    <DialogTitle>Keyboard shortcuts</DialogTitle>
                    <DialogDescription>
                        No buy/sell hotkeys by design — placement always passes the ticket&apos;s confirm step.
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                    {GROUPS.map((g) => (
                        <div key={g.title}>
                            <p className="label-md mb-1.5 text-subtle-foreground">{g.title}</p>
                            <div className="divide-y divide-border overflow-hidden rounded-md border border-border">
                                {g.rows.map(([key, desc]) => (
                                    <div key={key} className="flex items-center justify-between bg-surface px-3 py-1.5">
                                        <span className="text-xs text-muted-foreground">{desc}</span>
                                        <kbd className="num rounded-sm border border-border bg-elevated px-1.5 py-0.5 text-[10px] text-foreground">
                                            {key}
                                        </kbd>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            </DialogContent>
        </Dialog>
    )
}
