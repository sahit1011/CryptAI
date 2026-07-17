"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Activity, Menu, X, LogOut } from "lucide-react";
import { useState, useEffect } from "react";
import { createClient } from "@/utils/supabase/client";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

export function Navbar() {
    const [isScrolled, setIsScrolled] = useState(false);
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [userEmail, setUserEmail] = useState<string | null>(null);
    const [isLoggingOut, setIsLoggingOut] = useState(false);
    const supabase = createClient();

    useEffect(() => {
        const handleScroll = () => {
            setIsScrolled(window.scrollY > 20);
        };

        window.addEventListener("scroll", handleScroll);
        return () => window.removeEventListener("scroll", handleScroll);
    }, []);

    useEffect(() => {
        // Check initial auth state
        const checkAuth = async () => {
            const { data: { session } } = await supabase.auth.getSession();
            setIsAuthenticated(!!session);
            setUserEmail(session?.user?.email || null);
        };

        checkAuth();

        // Listen for auth changes
        const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
            setIsAuthenticated(!!session);
            setUserEmail(session?.user?.email || null);
        });

        return () => subscription.unsubscribe();
    }, [supabase]);

    const handleLogout = async () => {
        setIsLoggingOut(true);
        await supabase.auth.signOut();
        // Use window.location to force full page reload and clear auth state
        window.location.href = "/";
    };

    const navLinks = [
        { href: "#features", label: "Features" },
        { href: "#architecture", label: "Architecture" },
        { href: "#pricing", label: "Pricing" },
        { href: "#docs", label: "Docs" },
    ];

    return (
        <>
            <nav
                className={`lg:hidden fixed top-0 left-0 right-0 z-50 transition-all duration-500 ${isScrolled
                    ? "py-3 bg-background/85 backdrop-blur-xl border-b border-border shadow-[var(--shadow-elevation-mid)]"
                    : "py-5 bg-background/50 backdrop-blur-md border-b border-transparent"
                    }`}
            >
                <div className="max-w-7xl mx-auto px-6">
                    <div className="flex items-center justify-between relative">
                        {/* Left Side - Logo/Brand */}
                        <Link href="/" className="flex items-center gap-2.5 group z-10">
                            <div className="chip-brand size-8">
                                <Activity className="w-4.5 h-4.5 text-accent-300" />
                            </div>
                            <span className="text-lg font-semibold tracking-tight text-foreground">
                                CryptAI
                            </span>
                        </Link>

                        {/* Center - Navigation Links (quiet: color shift only, 150ms) */}
                        <div className="hidden md:flex lg:hidden items-center gap-1 absolute left-1/2 -translate-x-1/2">
                            {navLinks.map((link) => (
                                <Link
                                    key={link.href}
                                    href={link.href}
                                    className="rounded-md px-3.5 py-2 text-sm font-medium text-muted-foreground transition-colors duration-150 hover:bg-elevated hover:text-foreground"
                                >
                                    {link.label}
                                </Link>
                            ))}
                        </div>

                        {/* Right Side - CTA Buttons or Profile */}
                        <div className="hidden md:flex lg:hidden items-center gap-3 z-10">
                            {isAuthenticated ? (
                                <>
                                    <Link href="/dashboard">
                                        <Button
                                            variant="ghost"
                                            className="text-sm font-medium"
                                        >
                                            Dashboard
                                        </Button>
                                    </Link>
                                    <div className="flex items-center gap-2 px-3 py-2 rounded-full glass-panel">
                                        <Avatar className="h-7 w-7">
                                            <AvatarFallback className="bg-accent/10 text-accent-300 text-xs">
                                                {userEmail?.charAt(0).toUpperCase() || "U"}
                                            </AvatarFallback>
                                        </Avatar>
                                        <span className="text-sm text-muted-foreground max-w-[120px] truncate">
                                            {userEmail}
                                        </span>
                                    </div>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        onClick={handleLogout}
                                        disabled={isLoggingOut}
                                        title="Logout"
                                        aria-label="Logout"
                                    >
                                        <LogOut className="h-4 w-4" />
                                    </Button>
                                </>
                            ) : (
                                <>
                                    <Link
                                        href="/auth/login"
                                        className="rounded-md px-3.5 py-2 text-sm font-medium text-muted-foreground transition-colors duration-150 hover:bg-elevated hover:text-foreground"
                                    >
                                        Log in
                                    </Link>

                                    <Link href="/auth/signup">
                                        <Button className="h-9 px-5">Sign up</Button>
                                    </Link>
                                </>
                            )}
                        </div>

                        {/* Mobile Menu Button */}
                        <button
                            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                            className="md:hidden p-2 rounded-lg glass-panel text-foreground z-10"
                            aria-label="Toggle menu"
                        >
                            {isMobileMenuOpen ? (
                                <X className="w-5 h-5" />
                            ) : (
                                <Menu className="w-5 h-5" />
                            )}
                        </button>
                    </div>
                </div>
            </nav>

            {/* Mobile Menu */}
            <div
                className={`fixed inset-0 z-40 md:hidden transition-all duration-300 ${isMobileMenuOpen
                    ? "opacity-100 pointer-events-auto"
                    : "opacity-0 pointer-events-none"
                    }`}
            >
                {/* Backdrop */}
                <div
                    className="absolute inset-0 bg-background/80 backdrop-blur-xl"
                    onClick={() => setIsMobileMenuOpen(false)}
                />

                {/* Menu Content */}
                <div
                    className={`absolute top-20 left-4 right-4 glass-panel p-6 transition-all duration-300 ${isMobileMenuOpen
                        ? "translate-y-0 opacity-100"
                        : "-translate-y-4 opacity-0"
                        }`}
                >
                    <div className="flex flex-col gap-1">
                        {navLinks.map((link, index) => (
                            <Link
                                key={link.href}
                                href={link.href}
                                onClick={() => setIsMobileMenuOpen(false)}
                                className="px-4 py-3 text-base font-medium text-muted-foreground hover:text-foreground hover:bg-accent/10 rounded-lg transition-all duration-200"
                                style={{
                                    animationDelay: `${index * 50}ms`,
                                }}
                            >
                                {link.label}
                            </Link>
                        ))}
                    </div>

                    <div className="mt-6 pt-6 border-t border-border flex flex-col gap-3">
                        {isAuthenticated ? (
                            <>
                                <Link
                                    href="/dashboard"
                                    onClick={() => setIsMobileMenuOpen(false)}
                                >
                                    <Button
                                        className="w-full h-11"
                                    >
                                        Go to Dashboard
                                    </Button>
                                </Link>
                                <div className="flex items-center gap-3 px-4 py-3 rounded-lg glass-panel">
                                    <Avatar className="h-8 w-8">
                                        <AvatarFallback className="bg-accent/10 text-accent-300">
                                            {userEmail?.charAt(0).toUpperCase() || "U"}
                                        </AvatarFallback>
                                    </Avatar>
                                    <span className="text-sm text-muted-foreground flex-1 truncate">
                                        {userEmail}
                                    </span>
                                </div>
                                <Button
                                    variant="ghost"
                                    onClick={handleLogout}
                                    disabled={isLoggingOut}
                                    className="w-full h-12 rounded-lg"
                                >
                                    <LogOut className="h-4 w-4 mr-2" />
                                    {isLoggingOut ? "Logging out..." : "Logout"}
                                </Button>
                            </>
                        ) : (
                            <>
                                <Link
                                    href="/auth/login"
                                    onClick={() => setIsMobileMenuOpen(false)}
                                    className="px-4 py-3 text-center text-base font-medium text-muted-foreground hover:text-foreground hover:bg-accent/10 rounded-lg transition-all duration-200"
                                >
                                    Log in
                                </Link>

                                <Link
                                    href="/auth/signup"
                                    onClick={() => setIsMobileMenuOpen(false)}
                                >
                                    <Button
                                        className="w-full h-11"
                                    >
                                        Sign up
                                    </Button>
                                </Link>
                            </>
                        )}
                    </div>
                </div>
            </div>
        </>
    );
}
