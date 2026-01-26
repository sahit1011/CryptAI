"use client";

import dynamic from "next/dynamic";
import { SectionHeader } from "../ui/SectionHeader";
import { TickerWidget } from "../widgets/TickerWidget";
import { OrderBookWidget } from "../widgets/OrderBookWidget";
import { LineChart } from "lucide-react";

// Dynamically import ChartWidget
const ChartWidget = dynamic(
    () => import("../widgets/ChartWidget").then((mod) => mod.ChartWidget),
    {
        ssr: false,
        loading: () => (
            <div className="h-full w-full glass-card animate-pulse rounded-xl flex items-center justify-center">
                <span className="text-muted-foreground text-sm">Loading Chart...</span>
            </div>
        ),
    }
);

export function MarketsSection() {
    return (
        <div className="space-y-8">
            {/* Header */}
            <SectionHeader
                title="Markets"
                description="Real-time price charts, order books, and market data"
                icon={LineChart}
                iconColor="bg-cyan-500/10 text-cyan-400"
            />

            {/* Main Chart + Order Book Layout */}
            <div className="grid gap-6 lg:grid-cols-3">
                {/* Chart - 2 columns */}
                <div className="lg:col-span-2 space-y-6">
                    {/* Live Price Chart */}
                    <div className="h-[600px] rounded-xl overflow-hidden border border-white/5 bg-[#0A0A0A]/50 backdrop-blur-sm">
                        <ChartWidget />
                    </div>

                    {/* Ticker Widget */}
                    <TickerWidget />
                </div>

                {/* Order Book - 1 column */}
                <div className="space-y-6">
                    <div className="h-[600px]">
                        <OrderBookWidget />
                    </div>
                </div>
            </div>
        </div>
    );
}
