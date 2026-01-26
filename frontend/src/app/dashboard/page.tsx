"use client";

import { useState } from "react";
import { DashboardTabs, DashboardSection } from "@/components/dashboard/DashboardTabs";
import { OverviewSection } from "@/components/dashboard/sections/OverviewSection";
import { PortfolioSection } from "@/components/dashboard/sections/PortfolioSection";
import { MarketsSection } from "@/components/dashboard/sections/MarketsSection";
import { AgentsSection } from "@/components/dashboard/sections/AgentsSection";
import { useMarketData } from "@/hooks/useMarketData";
import { motion, AnimatePresence } from "framer-motion";

export default function DashboardPage() {
    // Initialize WebSocket connection
    useMarketData();

    const [activeSection, setActiveSection] = useState<DashboardSection>("overview");

    // Animation variants for section transitions
    const sectionVariants = {
        hidden: { opacity: 0, y: 20 },
        visible: {
            opacity: 1,
            y: 0,
            transition: {
                duration: 0.3,
            },
        },
        exit: {
            opacity: 0,
            y: -20,
            transition: {
                duration: 0.2,
            },
        },
    };

    return (
        <div className="min-h-screen">
            {/* Tab Navigation */}
            <DashboardTabs activeSection={activeSection} onSectionChange={setActiveSection} />

            {/* Section Content */}
            <div className="max-w-7xl mx-auto px-6 py-8">
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
                            <div className="text-center py-20">
                                <h2 className="heading-2 text-white mb-4">Trading Section</h2>
                                <p className="body-md text-muted-foreground">
                                    Coming soon - Advanced trading interface
                                </p>
                            </div>
                        )}
                    </motion.div>
                </AnimatePresence>
            </div>
        </div>
    );
}
