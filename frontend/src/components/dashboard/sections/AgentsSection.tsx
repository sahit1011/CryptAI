"use client";

import { Bot } from "lucide-react";
import { AgentFeed } from "../widgets/AgentFeed";
import { ActiveTrades } from "../widgets/ActiveTrades";

export function AgentsSection() {
    return (
        <div className="space-y-6">
            {/* Header (connection status lives in the global top bar + per-panel) */}
            <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                    <div className="flex size-10 items-center justify-center rounded-lg border border-border bg-accent-muted text-accent">
                        <Bot className="h-5 w-5" />
                    </div>
                    <div>
                        <h1 className="heading-2 text-foreground">AI Agents</h1>
                        <p className="body-sm mt-1 max-w-2xl">
                            Monitor the autonomous trading agents and their live decisions.
                        </p>
                    </div>
                </div>
            </div>

            {/* Agent feed + active positions */}
            <div className="grid gap-6 lg:grid-cols-2">
                <AgentFeed />
                <ActiveTrades />
            </div>
        </div>
    );
}
