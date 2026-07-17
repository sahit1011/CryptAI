"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
    Activity,
    BookOpen,
    Layers,
    LayoutDashboard,
    LogIn,
    LogOut,
    UserPlus,
    Wallet,
    Workflow,
    type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { createClient } from "@/utils/supabase/client";
import { cn } from "@/lib/utils";

/*
 * LandingDock v2 — a floating command-bar dock: every item is icon + LABEL
 * (readable, not symbol-guessing), with a shared highlight that MORPHS between
 * items on hover (layoutId spring) — the cinematic touch is the movement of
 * the light, not icon magnification. One accent item (Start free / Dashboard).
 * Auth-aware; reduced motion swaps the morph for a plain hover fill.
 */

type DockItem = {
    label: string;
    href: string;
    icon: LucideIcon;
    accent?: boolean;
    onClick?: () => void;
};

const NAV_ITEMS: DockItem[] = [
    { label: "Features", href: "#features", icon: Layers },
    { label: "Architecture", href: "#architecture", icon: Workflow },
    { label: "Pricing", href: "#pricing", icon: Wallet },
    { label: "Docs", href: "#docs", icon: BookOpen },
];

export function LandingDock() {
    const reduced = useReducedMotion() ?? false;
    const [hovered, setHovered] = useState<string | null>(null);
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const supabase = createClient();

    useEffect(() => {
        supabase.auth.getSession().then(({ data: { session } }) => {
            setIsAuthenticated(!!session);
        });
        const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, session) => {
            setIsAuthenticated(!!session);
        });
        return () => subscription.unsubscribe();
    }, [supabase]);

    const authItems: DockItem[] = isAuthenticated
        ? [
            { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard, accent: true },
            {
                label: "Sign out",
                href: "/",
                icon: LogOut,
                onClick: () => {
                    supabase.auth.signOut().then(() => {
                        window.location.href = "/";
                    });
                },
            },
        ]
        : [
            { label: "Log in", href: "/auth/login", icon: LogIn },
            { label: "Start free", href: "/auth/signup", icon: UserPlus, accent: true },
        ];

    return (
        <motion.nav
            aria-label="Primary"
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            onMouseLeave={() => setHovered(null)}
            className="fixed left-1/2 top-4 z-50 hidden -translate-x-1/2 items-center gap-1 rounded-xl border border-border bg-background/85 p-1.5 backdrop-blur-md md:flex"
        >
            {/* Brand — part of the dock, not a separate bar. */}
            <Link
                href="/"
                className="mr-1 flex items-center gap-2 rounded-lg px-2.5 py-1.5 transition-colors duration-150 hover:bg-elevated"
            >
                <span className="chip-brand size-6">
                    <Activity className="size-3.5 text-accent-300" />
                </span>
                <span className="text-sm font-semibold tracking-tight text-foreground">CryptAI</span>
            </Link>

            <span aria-hidden className="mx-0.5 h-5 w-px bg-border" />

            {NAV_ITEMS.map((item) => (
                <DockButton
                    key={item.label}
                    item={item}
                    hovered={hovered}
                    setHovered={setHovered}
                    reduced={reduced}
                />
            ))}

            <span aria-hidden className="mx-0.5 h-5 w-px bg-border" />

            {authItems.map((item) => (
                <DockButton
                    key={item.label}
                    item={item}
                    hovered={hovered}
                    setHovered={setHovered}
                    reduced={reduced}
                />
            ))}
        </motion.nav>
    );
}

function DockButton({
    item,
    hovered,
    setHovered,
    reduced,
}: {
    item: DockItem;
    hovered: string | null;
    setHovered: (l: string | null) => void;
    reduced: boolean;
}) {
    const Icon = item.icon;

    if (item.accent) {
        return (
            <Link
                href={item.href}
                onClick={(e) => {
                    if (item.onClick) {
                        e.preventDefault();
                        item.onClick();
                    }
                }}
                className="ml-0.5 flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-accent/25 bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors duration-150 hover:bg-primary-hover"
            >
                <Icon className="size-3.5" />
                {item.label}
            </Link>
        );
    }

    return (
        <Link
            href={item.href}
            onClick={(e) => {
                if (item.onClick) {
                    e.preventDefault();
                    item.onClick();
                }
            }}
            onMouseEnter={() => setHovered(item.label)}
            className={cn(
                "relative flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition-colors duration-150",
                hovered === item.label ? "text-foreground" : "text-muted-foreground",
                reduced && "hover:bg-elevated hover:text-foreground",
            )}
        >
            {/* The moving light: one shared highlight morphs between items. */}
            {!reduced && (
                <AnimatePresence>
                    {hovered === item.label && (
                        <motion.span
                            layoutId="dock-highlight"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            transition={{ type: "spring", stiffness: 320, damping: 28 }}
                            className="absolute inset-0 rounded-lg bg-elevated"
                        />
                    )}
                </AnimatePresence>
            )}
            <Icon className="relative z-10 size-3.5" />
            <span className="relative z-10">{item.label}</span>
        </Link>
    );
}
