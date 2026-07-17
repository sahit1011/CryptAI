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
    Home,
    Layers,
    LayoutDashboard,
    LogOut,
    Wallet,
    Workflow,
    type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { createClient } from "@/utils/supabase/client";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

/*
 * LandingDock v3 — no container box: bare icons spaced across the top center,
 * macOS magnification toward the cursor, and the icon's NAME rises beneath the
 * zoomed glyph. Brand sits left; profile / auth actions live in a conventional
 * right-side cluster. A soft top scrim (gradient, not a bar) keeps everything
 * readable over the hero. Reduced motion: static icons, labels on hover.
 */

const NAV_ICONS: { label: string; href: string; icon: LucideIcon }[] = [
    { label: "Home", href: "/", icon: Home },
    { label: "Features", href: "#features", icon: Layers },
    { label: "Architecture", href: "#architecture", icon: Workflow },
    { label: "Pricing", href: "#pricing", icon: Wallet },
    { label: "Docs", href: "#docs", icon: BookOpen },
];

const GLYPH = 21;
const GLYPH_PEAK = 32;
const REACH = 110;

export function LandingDock() {
    const reduced = useReducedMotion() ?? false;
    const mouseX = useMotionValue(Infinity);
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [userEmail, setUserEmail] = useState<string | null>(null);
    const supabase = createClient();

    useEffect(() => {
        supabase.auth.getSession().then(({ data: { session } }) => {
            setIsAuthenticated(!!session);
            setUserEmail(session?.user?.email ?? null);
        });
        const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, session) => {
            setIsAuthenticated(!!session);
            setUserEmail(session?.user?.email ?? null);
        });
        return () => subscription.unsubscribe();
    }, [supabase]);

    return (
        <header className="fixed inset-x-0 top-0 z-50 hidden md:block" aria-label="Primary">
            {/* Soft scrim — legibility without a bar. */}
            <div
                aria-hidden
                className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-background/85 via-background/40 to-transparent"
            />

            <div className="relative mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
                {/* Brand — left */}
                <Link href="/" className="flex items-center gap-2.5">
                    <span className="chip-brand size-8">
                        <Activity className="size-4.5 text-accent-300" />
                    </span>
                    <span className="text-lg font-semibold tracking-tight text-foreground">CryptAI</span>
                </Link>

                {/* Bare magnifying icons — center */}
                <nav
                    onMouseMove={(e) => !reduced && mouseX.set(e.clientX)}
                    onMouseLeave={() => mouseX.set(Infinity)}
                    className="absolute left-1/2 top-0 flex h-16 -translate-x-1/2 items-start gap-9 pt-4"
                >
                    {[
                        ...NAV_ICONS,
                        ...(isAuthenticated
                            ? [{ label: "Dashboard", href: "/dashboard", icon: LayoutDashboard }]
                            : []),
                    ].map((item) => (
                        <DockIcon key={item.label} item={item} mouseX={mouseX} reduced={reduced} />
                    ))}
                </nav>

                {/* Auth cluster — right */}
                <div className="flex items-center gap-3">
                    {isAuthenticated ? (
                        <>
                            <Avatar className="size-8" title={userEmail ?? undefined}>
                                <AvatarFallback className="bg-accent/10 text-xs text-accent-300">
                                    {userEmail?.charAt(0).toUpperCase() || "U"}
                                </AvatarFallback>
                            </Avatar>
                            <Button
                                variant="ghost"
                                size="icon"
                                aria-label="Sign out"
                                onClick={() => {
                                    supabase.auth.signOut().then(() => {
                                        window.location.href = "/";
                                    });
                                }}
                            >
                                <LogOut className="size-4" />
                            </Button>
                        </>
                    ) : (
                        <>
                            <Link
                                href="/auth/login"
                                className="rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors duration-150 hover:text-foreground"
                            >
                                Log in
                            </Link>
                            <Link href="/auth/signup">
                                <Button className="h-9 px-5">Sign up</Button>
                            </Link>
                        </>
                    )}
                </div>
            </div>
        </header>
    );
}

function DockIcon({
    item,
    mouseX,
    reduced,
}: {
    item: { label: string; href: string; icon: LucideIcon };
    mouseX: MotionValue<number>;
    reduced: boolean;
}) {
    // React-compiler opt-out: reading ref.current inside the useTransform
    // callback is the canonical dock-magnification pattern — the callback runs
    // on motion frames, not during render.
    "use no memo";
    const ref = useRef<HTMLAnchorElement>(null);
    const [hovered, setHovered] = useState(false);
    const Icon = item.icon;

    const distance = useTransform(mouseX, (val) => {
        const bounds = ref.current?.getBoundingClientRect() ?? { x: 0, width: 0 };
        return val - bounds.x - bounds.width / 2;
    });

    const size = useSpring(
        useTransform(distance, [-REACH, 0, REACH], [GLYPH, GLYPH_PEAK, GLYPH]),
        { mass: 0.1, stiffness: 170, damping: 13 },
    );

    return (
        <Link
            ref={ref}
            href={item.href}
            aria-label={item.label}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
            className="relative flex w-8 flex-col items-center"
        >
            {/* Fixed-height glyph slot so magnification never shifts neighbors down. */}
            <span className="flex h-9 items-end justify-center">
                {reduced ? (
                    <Icon
                        width={GLYPH}
                        height={GLYPH}
                        className={hovered ? "text-foreground" : "text-muted-foreground"}
                    />
                ) : (
                    <motion.span
                        style={{ width: size, height: size }}
                        className={`transition-colors duration-150 ${
                            hovered ? "text-foreground" : "text-muted-foreground"
                        }`}
                    >
                        <Icon className="h-full w-full" />
                    </motion.span>
                )}
            </span>

            {/* The name rises under the zoomed glyph. */}
            <AnimatePresence>
                {hovered && (
                    <motion.span
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -3 }}
                        transition={{ duration: 0.16 }}
                        className="pointer-events-none absolute top-full mt-1 whitespace-nowrap text-[11px] font-medium text-foreground"
                    >
                        {item.label}
                    </motion.span>
                )}
            </AnimatePresence>
        </Link>
    );
}
