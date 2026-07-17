"use client";

import {
    AnimatePresence,
    motion,
    MotionValue,
    useMotionValue,
    useReducedMotion,
    useSpring,
    useTransform,
} from "framer-motion";
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
import { useEffect, useRef, useState } from "react";
import { createClient } from "@/utils/supabase/client";
import { cn } from "@/lib/utils";

/*
 * LandingDock — the desktop header as a macOS-style dock (mechanics adapted
 * from 21st.dev's Floating Dock, rebuilt in the house system): squircle
 * app-icon cells that magnify toward the cursor with spring physics, tooltips
 * beneath (it hangs from the top edge, so growth and labels go downward).
 * Auth-aware: signed-out gets Log in / Start free; signed-in gets Dashboard /
 * Sign out. Reduced motion renders the dock static. Desktop only — the mobile
 * bar + drawer in Navbar stays.
 */

type DockLink = {
    title: string;
    href: string;
    icon: LucideIcon;
    /** The one accent moment in the dock (Start free / Dashboard). */
    accent?: boolean;
    onClick?: () => void;
};

const NAV_LINKS: DockLink[] = [
    { title: "CryptAI — Home", href: "/", icon: Activity },
    { title: "Features", href: "#features", icon: Layers },
    { title: "Architecture", href: "#architecture", icon: Workflow },
    { title: "Pricing", href: "#pricing", icon: Wallet },
    { title: "Docs", href: "#docs", icon: BookOpen },
];

// Cell + glyph sizes at rest and at the cursor peak.
const CELL = 38;
const CELL_PEAK = 58;
const GLYPH = 17;
const GLYPH_PEAK = 26;
const REACH = 130; // px of cursor influence to either side

export function LandingDock() {
    const reduced = useReducedMotion() ?? false;
    const mouseX = useMotionValue(Infinity);
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

    const authLinks: DockLink[] = isAuthenticated
        ? [
            { title: "Dashboard", href: "/dashboard", icon: LayoutDashboard, accent: true },
            {
                title: "Sign out",
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
            { title: "Log in", href: "/auth/login", icon: LogIn },
            { title: "Start free", href: "/auth/signup", icon: UserPlus, accent: true },
        ];

    return (
        <motion.nav
            aria-label="Primary"
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            onMouseMove={(e) => !reduced && mouseX.set(e.clientX)}
            onMouseLeave={() => mouseX.set(Infinity)}
            className="fixed left-1/2 top-4 z-50 hidden -translate-x-1/2 items-start gap-1.5 rounded-xl border border-border bg-background/80 px-2.5 pb-2 pt-2 backdrop-blur-md lg:flex"
        >
            {NAV_LINKS.map((link) => (
                <DockCell key={link.title} link={link} mouseX={mouseX} reduced={reduced} />
            ))}

            {/* Hairline divider between navigation and account actions. */}
            <span aria-hidden className="mx-1 h-[38px] w-px self-start bg-border" />

            {authLinks.map((link) => (
                <DockCell key={link.title} link={link} mouseX={mouseX} reduced={reduced} />
            ))}
        </motion.nav>
    );
}

function DockCell({
    link,
    mouseX,
    reduced,
}: {
    link: DockLink;
    mouseX: MotionValue<number>;
    reduced: boolean;
}) {
    // React-compiler opt-out: reading ref.current inside the useTransform
    // callback is the canonical dock-magnification pattern — the callback runs
    // on motion frames, not during render.
    "use no memo";
    const ref = useRef<HTMLDivElement>(null);
    const [hovered, setHovered] = useState(false);
    const Icon = link.icon;

    const distance = useTransform(mouseX, (val) => {
        const bounds = ref.current?.getBoundingClientRect() ?? { x: 0, width: 0 };
        return val - bounds.x - bounds.width / 2;
    });

    const cellSize = useSpring(
        useTransform(distance, [-REACH, 0, REACH], [CELL, CELL_PEAK, CELL]),
        { mass: 0.1, stiffness: 160, damping: 13 },
    );
    const glyphSize = useSpring(
        useTransform(distance, [-REACH, 0, REACH], [GLYPH, GLYPH_PEAK, GLYPH]),
        { mass: 0.1, stiffness: 160, damping: 13 },
    );

    return (
        <Link
            href={link.href}
            aria-label={link.title}
            onClick={(e) => {
                if (link.onClick) {
                    e.preventDefault();
                    link.onClick();
                }
            }}
        >
            <motion.div
                ref={ref}
                style={reduced ? { width: CELL, height: CELL } : { width: cellSize, height: cellSize }}
                onMouseEnter={() => setHovered(true)}
                onMouseLeave={() => setHovered(false)}
                className={cn(
                    "relative flex items-center justify-center rounded-lg border transition-colors duration-150",
                    link.accent
                        ? "border-accent/30 bg-primary text-primary-foreground"
                        : "border-transparent bg-elevated/60 text-muted-foreground hover:border-border hover:text-foreground",
                )}
            >
                <AnimatePresence>
                    {hovered && (
                        <motion.span
                            initial={{ opacity: 0, y: -6, x: "-50%" }}
                            animate={{ opacity: 1, y: 0, x: "-50%" }}
                            exit={{ opacity: 0, y: -4, x: "-50%" }}
                            transition={{ duration: 0.15 }}
                            className="absolute left-1/2 top-full mt-2 w-fit whitespace-pre rounded-md border border-border bg-elevated px-2 py-0.5 text-xs text-foreground"
                        >
                            {link.title}
                        </motion.span>
                    )}
                </AnimatePresence>
                {reduced ? (
                    <Icon style={{ width: GLYPH, height: GLYPH }} />
                ) : (
                    <motion.span style={{ width: glyphSize, height: glyphSize }} className="flex items-center justify-center">
                        <Icon className="h-full w-full" />
                    </motion.span>
                )}
            </motion.div>
        </Link>
    );
}
