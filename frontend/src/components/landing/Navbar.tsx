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
        { href: "#how-it-works", label: "Architecture" },
        { href: "#pricing", label: "Pricing" },
        { href: "#docs", label: "Docs" },
    ];

    return (
        <>
            <nav
                className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 ${isScrolled
                    ? "py-3 bg-background/85 backdrop-blur-xl border-b border-border shadow-[var(--shadow-elevation-mid)]"
                    : "py-5 bg-background/50 backdrop-blur-md border-b border-transparent"
                    }`}
            >
                <div className="max-w-7xl mx-auto px-6">
                    <div className="flex items-center justify-between relative">
                        {/* Left Side - Logo/Brand */}
                        <Link href="/" className="flex items-center gap-3 group z-10">
                            <div
                                className={`relative transition-all duration-300 ${isScrolled ? "w-9 h-9" : "w-10 h-10"
                                    }`}
                            >
                                {/* Emerald brand mark */}
                                <div className="chip-emerald w-full h-full group-hover:emerald-glow group-hover:scale-105 transition-all duration-300">
                                    <Activity className="w-5 h-5 text-accent-300" />
                                </div>
                            </div>

                            <span className="text-xl font-bold font-mono tracking-tight text-foreground group-hover:text-accent-300 transition-colors duration-300">
                                CryptAI
                            </span>
                        </Link>

                        {/* Center - Navigation Links */}
                        <div className="hidden md:flex items-center gap-2 absolute left-1/2 -translate-x-1/2">
                            {navLinks.map((link) => (
                                <Link
                                    key={link.href}
                                    href={link.href}
                                    className="relative px-5 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-all duration-300 group"
                                >
                                    <span className="relative z-10">{link.label}</span>

                                    {/* Hover background — emerald tint */}
                                    <div className="absolute inset-0 rounded-lg bg-accent/0 group-hover:bg-accent/10 transition-all duration-300" />

                                    {/* Bottom border animation — emerald */}
                                    <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-0 h-[2px] bg-accent group-hover:w-3/4 transition-all duration-300" />
                                </Link>
                            ))}
                        </div>

                        {/* Right Side - CTA Buttons or Profile */}
                        <div className="hidden md:flex items-center gap-3 z-10">
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
                                    >
                                        <LogOut className="h-4 w-4" />
                                    </Button>
                                </>
                            ) : (
                                <>
                                    <Link
                                        href="/auth/login"
                                        className="relative px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-all duration-300 group"
                                    >
                                        <span className="relative z-10">Log in</span>
                                        <div className="absolute inset-0 rounded-lg bg-accent/0 group-hover:bg-accent/10 transition-all duration-300" />
                                    </Link>

                                    <Link href="/auth/signup">
                                        <Button
                                            className="h-10 px-6 rounded-full bg-primary text-primary-foreground hover:bg-accent-400 font-medium emerald-glow transition-transform hover:scale-[1.03]"
                                        >
                                            Sign up
                                        </Button>
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
                                        className="w-full h-12 rounded-full bg-primary text-primary-foreground hover:bg-accent-400 font-medium emerald-glow"
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
                                        className="w-full h-12 rounded-full bg-primary text-primary-foreground hover:bg-accent-400 font-medium emerald-glow"
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
