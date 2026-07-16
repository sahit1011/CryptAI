"use client";

import { motion } from "framer-motion";
import { LayoutDashboard, Wallet, LineChart, Radar, Plug, Bot } from "lucide-react";
import { cn } from "@/lib/utils";

export type DashboardSection = "overview" | "portfolio" | "markets" | "signals" | "connect" | "agents";

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
        id: "signals" as DashboardSection,
        label: "Signals",
        icon: Radar,
    },
    {
        id: "connect" as DashboardSection,
        label: "Connect",
        icon: Plug,
    },
    {
        id: "agents" as DashboardSection,
        label: "AI Agents",
        icon: Bot,
    },
];

export function DashboardTabs({ activeSection, onSectionChange }: DashboardTabsProps) {
    return (
        <div className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-xl">
            <div className="mx-auto max-w-7xl px-6">
                <nav className="scroll-terminal -mb-px flex items-center gap-1 overflow-x-auto">
                    {tabs.map((tab) => {
                        const Icon = tab.icon;
                        const isActive = activeSection === tab.id;

                        return (
                            <button
                                key={tab.id}
                                onClick={() => onSectionChange(tab.id)}
                                className={cn(
                                    "relative flex items-center gap-2 whitespace-nowrap px-5 py-3.5 text-sm font-medium transition-colors duration-200 outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
                                    isActive
                                        ? "text-foreground"
                                        : "text-muted-foreground hover:text-foreground"
                                )}
                            >
                                <Icon
                                    className={cn(
                                        "h-4 w-4 transition-colors duration-200",
                                        isActive ? "text-accent" : "text-subtle-foreground"
                                    )}
                                />
                                <span>{tab.label}</span>

                                {/* Active indicator — single emerald hairline */}
                                {isActive && (
                                    <motion.div
                                        layoutId="activeTab"
                                        className="absolute inset-x-0 bottom-0 h-0.5 bg-accent"
                                        transition={{
                                            type: "spring",
                                            stiffness: 500,
                                            damping: 30,
                                        }}
                                    />
                                )}
                            </button>
                        );
                    })}
                </nav>
            </div>
        </div>
    );
}
