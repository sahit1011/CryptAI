"use client";

import dynamic from "next/dynamic";
import { SectionHeader } from "../ui/SectionHeader";
import { TickerWidget } from "../widgets/TickerWidget";
import { OrderBookWidget } from "../widgets/OrderBookWidget";
import { LoadingState } from "@/components/ui/states";
import { LineChart } from "lucide-react";

// Dynamically import ChartWidget
const ChartWidget = dynamic(
    () => import("../widgets/ChartWidget").then((mod) => mod.ChartWidget),
    {
        ssr: false,
        loading: () => (
            <div className="flex h-full w-full items-center justify-center rounded-xl border border-border bg-surface/60 backdrop-blur-md">
                <LoadingState title="Loading chart…" />
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
                iconColor="bg-accent-muted text-accent-300"
            />

            {/* Main Chart + Order Book Layout */}
            <div className="grid gap-6 lg:grid-cols-3">
                {/* Chart - 2 columns */}
                <div className="lg:col-span-2 space-y-6">
                    {/* Live Price Chart */}
                    <div className="h-[600px] overflow-hidden rounded-xl border border-border bg-surface/60 shadow-[var(--shadow-elevation-low)] backdrop-blur-md">
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
