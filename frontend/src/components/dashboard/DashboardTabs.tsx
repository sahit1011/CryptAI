"use client";

import { motion } from "framer-motion";
import { LayoutDashboard, Wallet, LineChart, TrendingUp, Bot } from "lucide-react";
import { cn } from "@/lib/utils";

export type DashboardSection = "overview" | "portfolio" | "markets" | "trading" | "agents";

interface DashboardTabsProps {
    activeSection: DashboardSection;
    onSectionChange: (section: DashboardSection) => void;
}

const tabs = [
    {
        id: "overview" as DashboardSection,
        label: "Overview",
        icon: LayoutDashboard,
    },
    {
        id: "portfolio" as DashboardSection,
        label: "Portfolio",
        icon: Wallet,
    },
    {
        id: "markets" as DashboardSection,
        label: "Markets",
        icon: LineChart,
    },
    {
        id: "trading" as DashboardSection,
        label: "Trading",
        icon: TrendingUp,
    },
    {
        id: "agents" as DashboardSection,
        label: "AI Agents",
        icon: Bot,
    },
];

export function DashboardTabs({ activeSection, onSectionChange }: DashboardTabsProps) {
    return (
        <div className="border-b border-white/10 bg-[#0A0A0A]/80 backdrop-blur-xl sticky top-0 z-40">
            <div className="max-w-7xl mx-auto px-6">
                <nav className="flex items-center gap-1 -mb-px overflow-x-auto scrollbar-hide">
                    {tabs.map((tab) => {
                        const Icon = tab.icon;
                        const isActive = activeSection === tab.id;

                        return (
                            <button
                                key={tab.id}
                                onClick={() => onSectionChange(tab.id)}
                                className={cn(
                                    "relative flex items-center gap-2 px-6 py-4 text-sm font-medium transition-all duration-200 whitespace-nowrap",
                                    isActive
                                        ? "text-white"
                                        : "text-muted-foreground hover:text-white"
                                )}
                            >
                                <Icon
                                    className={cn(
                                        "w-4 h-4 transition-all duration-200",
                                        isActive && "text-emerald-400"
                                    )}
                                />
                                <span>{tab.label}</span>

                                {/* Active indicator */}
                                {isActive && (
                                    <motion.div
                                        layoutId="activeTab"
                                        className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-emerald-400 via-cyan-400 to-emerald-400"
                                        transition={{
                                            type: "spring",
                                            stiffness: 500,
                                            damping: 30,
                                        }}
                                    />
                                )}

                                {/* Hover background */}
                                {!isActive && (
                                    <div className="absolute inset-0 bg-white/0 hover:bg-white/5 transition-colors duration-200 rounded-t-lg" />
                                )}
                            </button>
                        );
                    })}
                </nav>
            </div>
        </div>
    );
}
