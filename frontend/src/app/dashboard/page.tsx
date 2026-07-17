"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { OverviewSection } from "@/components/dashboard/sections/OverviewSection";
import { PortfolioSection } from "@/components/dashboard/sections/PortfolioSection";
import { MarketsSection } from "@/components/dashboard/sections/MarketsSection";
import { AgentsSection } from "@/components/dashboard/sections/AgentsSection";
import { SettingsSection } from "@/components/dashboard/sections/SettingsSection";
import { useMarketData } from "@/hooks/useMarketData";
import { motion, AnimatePresence } from "framer-motion";

// Single source of nav truth is the Sidebar (desktop rail + mobile drawer);
// the section itself is URL-driven so views stay shareable/bookmarkable.
export type DashboardSection = "overview" | "portfolio" | "markets" | "agents" | "settings";

const SECTIONS: DashboardSection[] = ["overview", "portfolio", "markets", "agents", "settings"];

const sectionVariants = {
    hidden: { opacity: 0, y: 8 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.3 } },
    exit: { opacity: 0, y: -8, transition: { duration: 0.15 } },
};

function DashboardContent() {
    // Initialize WebSocket connection
    useMarketData();

    const searchParams = useSearchParams();

    const param = searchParams.get("section") as DashboardSection | null;
    const activeSection: DashboardSection =
        param && SECTIONS.includes(param) ? param : "overview";

    return (
        <div className="min-h-screen">
            <div className="mx-auto max-w-7xl px-6 py-8">
                <AnimatePresence mode="wait">
                    <motion.div
                        key={activeSection}
                        variants={sectionVariants}
                        initial="hidden"
                        animate="visible"
                        exit="exit"
                    >
                        {activeSection === "overview" && <OverviewSection />}
                        {activeSection === "portfolio" && <PortfolioSection />}
                        {activeSection === "markets" && <MarketsSection />}
                        {activeSection === "agents" && <AgentsSection />}
                        {activeSection === "settings" && <SettingsSection />}
                    </motion.div>
                </AnimatePresence>
            </div>
        </div>
    );
}

export default function DashboardPage() {
    return (
        <Suspense fallback={<div className="min-h-screen" />}>
            <DashboardContent />
        </Suspense>
    );
}
