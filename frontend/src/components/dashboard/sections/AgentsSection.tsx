"use client";

import { AgentFeed } from "../widgets/AgentFeed";
import { ActiveTrades } from "../widgets/ActiveTrades";
import { SectionHeader } from "../ui/SectionHeader";

export function AgentsSection() {
    return (
        <div className="space-y-6">
            {/* Compact working header — matches every other section. */}
            <SectionHeader
                title="AI Agents"
                description="Monitor the autonomous trading agents and their live decisions."
            />

            {/* Agent feed + active positions */}
            <div className="grid gap-6 lg:grid-cols-2">
                <AgentFeed />
                <ActiveTrades />
            </div>
        </div>
    );
}
