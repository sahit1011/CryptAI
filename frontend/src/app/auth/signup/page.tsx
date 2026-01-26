"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ArrowRight, Activity, Mail, Lock, User, Loader2 } from "lucide-react";
import { BackgroundGrid } from "@/components/landing/BackgroundGrid";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/utils/supabase/client";

const GoogleIcon = () => (
    <svg className="mr-2 h-4 w-4" aria-hidden="true" focusable="false" data-prefix="fab" data-icon="google" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 488 512">
        <path fill="currentColor" d="M488 261.8C488 403.3 391.1 504 248 504 110.8 504 0 393.2 0 256S110.8 8 248 8c66.8 0 123 24.5 166.3 64.9l-67.5 64.9C258.5 52.6 94.3 116.6 94.3 256c0 86.5 69.1 156.6 153.7 156.6 98.2 0 135-70.4 140.8-106.9H248v-85.3h236.1c2.3 12.7 3.9 24.9 3.9 41.4z"></path>
    </svg>
);

export default function SignupPage() {
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const router = useRouter();
    const supabase = createClient();

    const handleSignup = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError(null);

        if (password !== confirmPassword) {
            setError("Passwords do not match");
            setLoading(false);
            return;
        }

        try {
            const { error } = await supabase.auth.signUp({
                email,
                password,
                options: {
                    data: {
                        full_name: name,
                    },
                    emailRedirectTo: `${window.location.origin}/auth/callback`,
                },
            });

            if (error) throw error;

            // Check if session was created (auto-confirm enabled)
            const { data: { session } } = await supabase.auth.getSession();
            if (session) {
                router.push("/dashboard");
                router.refresh();
            } else {
                setError("Please check your email to confirm your account.");
            }

        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleGoogleSignup = async () => {
        setLoading(true);
        setError(null);
        try {
            const { error } = await supabase.auth.signInWithOAuth({
                provider: "google",
                options: {
                    redirectTo: `${window.location.origin}/auth/callback`,
                },
            });
            if (error) throw error;
        } catch (err: any) {
            setError(err.message);
            setLoading(false);
        }
    };

    return (
        <div className="flex min-h-screen items-center justify-center bg-[#0A0A0A] text-foreground relative overflow-hidden py-12">
            {/* Background Grid */}
            <BackgroundGrid />

            {/* Additional Emerald-Cyan Glow */}
            <div className="absolute inset-0 z-0 pointer-events-none">
                <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-emerald-500/10 blur-[120px]" />
                <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full bg-cyan-500/10 blur-[120px]" />
            </div>

            <div className="w-full max-w-md p-8 relative z-10">
                {/* Logo */}
                <Link href="/" className="flex justify-center mb-8 group">
                    <div className="flex items-center gap-3">
                        <div className="w-12 h-12 rounded-xl bg-white/10 flex items-center justify-center border border-white/10 backdrop-blur-md shadow-xl group-hover:bg-white/15 group-hover:scale-105 transition-all">
                            <Activity className="w-6 h-6 text-white" />
                        </div>
                        <span className="text-2xl font-bold tracking-tight text-white group-hover:text-emerald-300 transition-colors">
                            CryptAI
                        </span>
                    </div>
                </Link>

                {/* Auth Card */}
                <div className="glass-card rounded-2xl p-8 space-y-6 relative overflow-hidden">
                    {/* Gradient Border Effect */}
                    <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-emerald-500/20 via-cyan-500/20 to-emerald-500/20 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />

                    <div className="text-center space-y-2 relative z-10">
                        <h1 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-emerald-400 via-cyan-400 to-emerald-400 bg-clip-text text-transparent">
                            Create an account
                        </h1>
                        <p className="text-sm text-muted-foreground">
                            Join the future of algorithmic trading
                        </p>
                    </div>

                    {error && (
                        <div className="bg-red-500/10 border border-red-500/20 text-red-400 px-4 py-2 rounded-lg text-sm text-center">
                            {error}
                        </div>
                    )}

                    <form onSubmit={handleSignup} className="space-y-4 relative z-10">
                        <div className="space-y-2">
                            <Label htmlFor="name" className="text-sm font-medium text-gray-300">
                                Full Name
                            </Label>
                            <div className="relative group">
                                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 group-focus-within:text-emerald-400 transition-colors" />
                                <Input
                                    id="name"
                                    type="text"
                                    placeholder="John Doe"
                                    className="pl-10 h-11 bg-white/5 border-white/10 focus:border-emerald-500/50 focus:ring-2 focus:ring-emerald-500/20 placeholder:text-muted-foreground/50 transition-all"
                                    value={name}
                                    onChange={(e) => setName(e.target.value)}
                                    required
                                />
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="email" className="text-sm font-medium text-gray-300">
                                Email
                            </Label>
                            <div className="relative group">
                                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 group-focus-within:text-emerald-400 transition-colors" />
                                <Input
                                    id="email"
                                    type="email"
                                    placeholder="name@example.com"
                                    className="pl-10 h-11 bg-white/5 border-white/10 focus:border-emerald-500/50 focus:ring-2 focus:ring-emerald-500/20 placeholder:text-muted-foreground/50 transition-all"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    required
                                />
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="password" className="text-sm font-medium text-gray-300">
                                Password
                            </Label>
                            <div className="relative group">
                                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 group-focus-within:text-emerald-400 transition-colors" />
                                <Input
                                    id="password"
                                    type="password"
                                    placeholder="••••••••"
                                    className="pl-10 h-11 bg-white/5 border-white/10 focus:border-emerald-500/50 focus:ring-2 focus:ring-emerald-500/20 placeholder:text-muted-foreground/50 transition-all"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    required
                                />
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="confirmPassword" className="text-sm font-medium text-gray-300">
                                Confirm Password
                            </Label>
                            <div className="relative group">
                                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 group-focus-within:text-emerald-400 transition-colors" />
                                <Input
                                    id="confirmPassword"
                                    type="password"
                                    placeholder="••••••••"
                                    className="pl-10 h-11 bg-white/5 border-white/10 focus:border-emerald-500/50 focus:ring-2 focus:ring-emerald-500/20 placeholder:text-muted-foreground/50 transition-all"
                                    value={confirmPassword}
                                    onChange={(e) => setConfirmPassword(e.target.value)}
                                    required
                                />
                            </div>
                        </div>

                        <Button
                            type="submit"
                            disabled={loading}
                            className="w-full h-11 bg-white text-black hover:bg-white/90 font-medium transition-all hover:scale-[1.02] shadow-lg shadow-white/20 relative z-10 group overflow-hidden"
                        >
                            <span className="relative z-10 flex items-center justify-center">
                                {loading ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                    <>
                                        Create Account <ArrowRight className="ml-2 h-4 w-4 group-hover:translate-x-1 transition-transform" />
                                    </>
                                )}
                            </span>
                            {/* Shine effect */}
                            <div className="absolute inset-0 -translate-x-full group-hover:translate-x-full transition-transform duration-1000 bg-gradient-to-r from-transparent via-white/30 to-transparent skew-x-12" />
                        </Button>
                    </form>

                    <div className="relative z-10">
                        <div className="absolute inset-0 flex items-center">
                            <span className="w-full border-t border-white/10" />
                        </div>
                        <div className="relative flex justify-center text-xs uppercase">
                            <span className="bg-[#0A0A0A] px-2 text-muted-foreground">
                                Or continue with
                            </span>
                        </div>
                    </div>

                    <Button
                        variant="outline"
                        onClick={handleGoogleSignup}
                        disabled={loading}
                        className="w-full h-11 border-white/10 bg-white/5 hover:bg-white/10 hover:text-white hover:border-emerald-500/30 transition-all relative z-10 group"
                    >
                        <GoogleIcon />
                        Google
                    </Button>
                </div>

                <p className="mt-6 text-center text-sm text-muted-foreground relative z-10">
                    Already have an account?{" "}
                    <Link
                        href="/auth/login"
                        className="text-emerald-400 hover:text-emerald-300 font-medium transition-colors hover:underline"
                    >
                        Sign in
                    </Link>
                </p>
            </div>
        </div>
    );
}
