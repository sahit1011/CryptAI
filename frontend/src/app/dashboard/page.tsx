"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { DashboardTabs, DashboardSection } from "@/components/dashboard/DashboardTabs";
import { OverviewSection } from "@/components/dashboard/sections/OverviewSection";
import { PortfolioSection } from "@/components/dashboard/sections/PortfolioSection";
import { MarketsSection } from "@/components/dashboard/sections/MarketsSection";
import { AgentsSection } from "@/components/dashboard/sections/AgentsSection";
import { useMarketData } from "@/hooks/useMarketData";
import { Badge } from "@/components/ui/badge";
import { Wrench } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

const SECTIONS: DashboardSection[] = ["overview", "portfolio", "markets", "trading", "agents"];

const sectionVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.3 } },
    exit: { opacity: 0, y: -20, transition: { duration: 0.2 } },
};

function DashboardContent() {
    // Initialize WebSocket connection
    useMarketData();

    const router = useRouter();
    const searchParams = useSearchParams();

    // Section is driven by the URL (?section=), so the sidebar links and the top tabs
    // stay in sync and each section is directly shareable/bookmarkable.
    const param = searchParams.get("section") as DashboardSection | null;
    const activeSection: DashboardSection =
        param && SECTIONS.includes(param) ? param : "overview";

    const setActiveSection = (section: DashboardSection) => {
        router.replace(section === "overview" ? "/dashboard" : `/dashboard?section=${section}`, {
            scroll: false,
        });
    };

    return (
        <div className="min-h-screen">
            <DashboardTabs activeSection={activeSection} onSectionChange={setActiveSection} />

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
                        {activeSection === "trading" && (
                            <div className="flex flex-col items-center py-20 text-center">
                                <Badge variant="secondary" className="mb-6 gap-1.5">
                                    <Wrench className="size-3" />
                                    Coming soon
                                </Badge>
                                <h2 className="heading-2 mb-4 text-foreground">Manual Trading</h2>
                                <p className="body-md mx-auto max-w-md text-muted-foreground">
                                    A manual order-entry interface is not available yet. Trading is
                                    currently handled by the autonomous agents — monitor activity in
                                    the Overview and Agents tabs.
                                </p>
                            </div>
                        )}
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
