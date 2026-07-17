"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ArrowRight, Activity, Loader2 } from "lucide-react";
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

        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : "Something went wrong.");
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
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : "Something went wrong.");
            setLoading(false);
        }
    };

    return (
        <div className="grain relative flex min-h-screen items-center justify-center overflow-hidden bg-background py-12 text-foreground">
            <BackgroundGrid />

            <div className="relative z-10 w-full max-w-md px-6">
                {/* Wordmark */}
                <Link href="/" className="mb-10 flex items-center justify-center gap-2.5">
                    <div className="chip-brand size-8">
                        <Activity className="size-4.5 text-accent-300" />
                    </div>
                    <span className="text-lg font-semibold tracking-tight text-foreground">CryptAI</span>
                </Link>

                <div className="rounded-xl border border-border bg-surface p-8">
                    <h1 className="heading-2 text-foreground">
                        Open your <em className="font-serif text-accent-300">desk.</em>
                    </h1>
                    <p className="body-sm mt-1.5">
                        Free to start — paper trading with virtual money.
                    </p>

                    {error && (
                        <div className="mt-5 rounded-md border border-loss/25 bg-loss/10 px-3.5 py-2.5 text-sm text-loss">
                            {error}
                        </div>
                    )}

                    <form onSubmit={handleSignup} className="mt-6 space-y-4">
                        <div className="space-y-1.5">
                            <Label htmlFor="name" className="text-sm text-muted-foreground">Name</Label>
                            <Input
                                id="name"
                                type="text"
                                placeholder="Your name"
                                className="h-11 border-border bg-elevated/50"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                required
                            />
                        </div>

                        <div className="space-y-1.5">
                            <Label htmlFor="email" className="text-sm text-muted-foreground">Email</Label>
                            <Input
                                id="email"
                                type="email"
                                placeholder="name@example.com"
                                className="h-11 border-border bg-elevated/50"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                required
                            />
                        </div>

                        <div className="grid gap-4 sm:grid-cols-2">
                            <div className="space-y-1.5">
                                <Label htmlFor="password" className="text-sm text-muted-foreground">Password</Label>
                                <Input
                                    id="password"
                                    type="password"
                                    placeholder="••••••••"
                                    className="h-11 border-border bg-elevated/50"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    required
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label htmlFor="confirmPassword" className="text-sm text-muted-foreground">Confirm</Label>
                                <Input
                                    id="confirmPassword"
                                    type="password"
                                    placeholder="••••••••"
                                    className="h-11 border-border bg-elevated/50"
                                    value={confirmPassword}
                                    onChange={(e) => setConfirmPassword(e.target.value)}
                                    required
                                />
                            </div>
                        </div>

                        <Button type="submit" disabled={loading} className="h-11 w-full">
                            {loading ? (
                                <Loader2 className="size-4 animate-spin" />
                            ) : (
                                <>
                                    Create account <ArrowRight className="size-4" />
                                </>
                            )}
                        </Button>
                    </form>

                    <div className="relative my-6">
                        <div className="absolute inset-0 flex items-center">
                            <span className="w-full border-t border-border" />
                        </div>
                        <div className="relative flex justify-center">
                            <span className="num bg-surface px-3 text-[11px] uppercase tracking-wider text-subtle-foreground">
                                or
                            </span>
                        </div>
                    </div>

                    <Button
                        variant="outline"
                        onClick={handleGoogleSignup}
                        disabled={loading}
                        className="h-11 w-full"
                    >
                        <GoogleIcon />
                        Continue with Google
                    </Button>
                </div>

                <p className="mt-6 text-center text-sm text-muted-foreground">
                    Already have an account?{" "}
                    <Link
                        href="/auth/login"
                        className="font-medium text-accent-300 transition-colors duration-150 hover:text-accent-200"
                    >
                        Sign in
                    </Link>
                </p>
            </div>
        </div>
    );
}
