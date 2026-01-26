"use client";

import { SectionHeader } from "../ui/SectionHeader";
import { AgentFeed } from "../widgets/AgentFeed";
import { ActiveTrades } from "../widgets/ActiveTrades";
import { Bot } from "lucide-react";

export function AgentsSection() {
    return (
        <div className="space-y-8">
            {/* Header */}
            <SectionHeader
                title="AI Agents"
                description="Monitor autonomous trading agents and their activities"
                icon={Bot}
                iconColor="bg-purple-500/10 text-purple-400"
            />

            {/* Agent Feed and Trades */}
            <div className="grid gap-6 lg:grid-cols-2">
                <AgentFeed />
                <ActiveTrades />
            </div>
        </div>
    );
}
