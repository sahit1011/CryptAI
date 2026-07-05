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
                    ? "py-3 bg-[#0A0A0A]/95 backdrop-blur-xl border-b border-white/10 shadow-2xl shadow-emerald-500/5"
                    : "py-5 bg-[#0A0A0A]/60 backdrop-blur-md border-b border-white/5"
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
                                {/* Simple icon container without gradient */}
                                <div className="relative w-full h-full rounded-xl bg-white/10 flex items-center justify-center border border-white/10 group-hover:bg-white/15 group-hover:border-white/20 transition-all group-hover:scale-105 backdrop-blur-md">
                                    <Activity className="w-5 h-5 text-white" />
                                </div>
                            </div>

                            <span className="text-xl font-bold tracking-tight text-white group-hover:text-emerald-300 transition-colors duration-300">
                                CryptAI
                            </span>
                        </Link>

                        {/* Center - Navigation Links */}
                        <div className="hidden md:flex items-center gap-2 absolute left-1/2 -translate-x-1/2">
                            {navLinks.map((link) => (
                                <Link
                                    key={link.href}
                                    href={link.href}
                                    className="relative px-5 py-2 text-sm font-medium text-gray-400 hover:text-white transition-all duration-300 group"
                                >
                                    <span className="relative z-10">{link.label}</span>

                                    {/* Hover background with emerald-cyan gradient */}
                                    <div className="absolute inset-0 rounded-lg bg-gradient-to-r from-emerald-500/0 via-cyan-500/0 to-emerald-500/0 group-hover:from-emerald-500/10 group-hover:via-cyan-500/10 group-hover:to-emerald-500/10 transition-all duration-300" />

                                    {/* Bottom border animation with emerald-cyan gradient */}
                                    <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-0 h-[2px] bg-gradient-to-r from-emerald-400 via-cyan-400 to-emerald-400 group-hover:w-3/4 transition-all duration-300" />
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
                                            className="text-sm font-medium text-gray-400 hover:text-white hover:bg-white/5"
                                        >
                                            Dashboard
                                        </Button>
                                    </Link>
                                    <div className="flex items-center gap-2 px-3 py-2 rounded-full bg-white/5 border border-white/10">
                                        <Avatar className="h-7 w-7">
                                            <AvatarFallback className="bg-emerald-500/10 text-emerald-400 text-xs">
                                                {userEmail?.charAt(0).toUpperCase() || "U"}
                                            </AvatarFallback>
                                        </Avatar>
                                        <span className="text-sm text-gray-400 max-w-[120px] truncate">
                                            {userEmail}
                                        </span>
                                    </div>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        onClick={handleLogout}
                                        disabled={isLoggingOut}
                                        className="text-gray-400 hover:text-white hover:bg-white/5"
                                        title="Logout"
                                    >
                                        <LogOut className="h-4 w-4" />
                                    </Button>
                                </>
                            ) : (
                                <>
                                    <Link
                                        href="/auth/login"
                                        className="relative px-4 py-2 text-sm font-medium text-gray-400 hover:text-white transition-all duration-300 group"
                                    >
                                        <span className="relative z-10">Log in</span>
                                        <div className="absolute inset-0 rounded-lg bg-white/0 group-hover:bg-white/5 transition-all duration-300" />
                                    </Link>

                                    <Link href="/auth/signup" className="group">
                                        <Button
                                            variant="secondary"
                                            className="relative h-10 px-6 rounded-full bg-white text-black font-medium overflow-hidden transition-all duration-300 hover:scale-105 hover:shadow-lg hover:shadow-emerald-500/20"
                                        >
                                            {/* Animated gradient background on hover with emerald-cyan */}
                                            <div className="absolute inset-0 bg-gradient-to-r from-emerald-400 via-cyan-400 to-emerald-400 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />

                                            <span className="relative z-10 group-hover:text-white transition-colors duration-300">
                                                Sign up
                                            </span>

                                            {/* Shine effect */}
                                            <div className="absolute inset-0 -translate-x-full group-hover:translate-x-full transition-transform duration-1000 bg-gradient-to-r from-transparent via-white/30 to-transparent skew-x-12" />
                                        </Button>
                                    </Link>
                                </>
                            )}
                        </div>

                        {/* Mobile Menu Button */}
                        <button
                            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                            className="md:hidden p-2 rounded-lg bg-white/5 hover:bg-white/10 transition-colors z-10"
                            aria-label="Toggle menu"
                        >
                            {isMobileMenuOpen ? (
                                <X className="w-5 h-5 text-white" />
                            ) : (
                                <Menu className="w-5 h-5 text-white" />
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
                    className="absolute inset-0 bg-black/80 backdrop-blur-xl"
                    onClick={() => setIsMobileMenuOpen(false)}
                />

                {/* Menu Content */}
                <div
                    className={`absolute top-20 left-4 right-4 bg-[#0A0A0A]/95 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-2xl transition-all duration-300 ${isMobileMenuOpen
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
                                className="px-4 py-3 text-base font-medium text-gray-400 hover:text-white hover:bg-white/5 rounded-lg transition-all duration-200"
                                style={{
                                    animationDelay: `${index * 50}ms`,
                                }}
                            >
                                {link.label}
                            </Link>
                        ))}
                    </div>

                    <div className="mt-6 pt-6 border-t border-white/10 flex flex-col gap-3">
                        {isAuthenticated ? (
                            <>
                                <Link
                                    href="/dashboard"
                                    onClick={() => setIsMobileMenuOpen(false)}
                                >
                                    <Button
                                        variant="secondary"
                                        className="w-full h-12 rounded-full bg-white text-black hover:bg-gradient-to-r hover:from-emerald-400 hover:via-cyan-400 hover:to-emerald-400 hover:text-white font-medium transition-all duration-300"
                                    >
                                        Go to Dashboard
                                    </Button>
                                </Link>
                                <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-white/5 border border-white/10">
                                    <Avatar className="h-8 w-8">
                                        <AvatarFallback className="bg-emerald-500/10 text-emerald-400">
                                            {userEmail?.charAt(0).toUpperCase() || "U"}
                                        </AvatarFallback>
                                    </Avatar>
                                    <span className="text-sm text-gray-400 flex-1 truncate">
                                        {userEmail}
                                    </span>
                                </div>
                                <Button
                                    variant="ghost"
                                    onClick={handleLogout}
                                    disabled={isLoggingOut}
                                    className="w-full h-12 text-gray-400 hover:text-white hover:bg-white/5 rounded-lg"
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
                                    className="px-4 py-3 text-center text-base font-medium text-gray-400 hover:text-white hover:bg-white/5 rounded-lg transition-all duration-200"
                                >
                                    Log in
                                </Link>

                                <Link
                                    href="/auth/signup"
                                    onClick={() => setIsMobileMenuOpen(false)}
                                >
                                    <Button
                                        variant="secondary"
                                        className="w-full h-12 rounded-full bg-white text-black hover:bg-gradient-to-r hover:from-emerald-400 hover:via-cyan-400 hover:to-emerald-400 hover:text-white font-medium transition-all duration-300"
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
