import Link from "next/link";
import { Activity, Github, Twitter, MessageCircle } from "lucide-react";

import { LiveTicker } from "./LiveTicker";

/*
 * Footer — on-brand, tidy. Tokened surface (no hardcoded canvas hex), crimson
 * wordmark/accents, mono wordmark, and a subtle crimson status dot. The stats
 * band lives in page.tsx (not duplicated here). LiveTicker renders only when
 * real prices are available.
 */

const columns: { heading: string; links: { label: string; href: string }[] }[] = [
    {
        heading: "Product",
        links: [
            { label: "Features", href: "#" },
            { label: "Architecture", href: "#" },
            { label: "Pricing", href: "#" },
            { label: "Changelog", href: "#" },
            { label: "Docs", href: "#" },
        ],
    },
    {
        heading: "Company",
        links: [
            { label: "About", href: "#" },
            { label: "Blog", href: "#" },
            { label: "Careers", href: "#" },
            { label: "Contact", href: "/contact" },
        ],
    },
    {
        heading: "Legal",
        links: [
            { label: "Privacy Policy", href: "#" },
            { label: "Terms of Service", href: "#" },
            { label: "Risk Disclosure", href: "#" },
        ],
    },
];

const socials: { label: string; href: string; icon: typeof Github }[] = [
    { label: "GitHub", href: "#", icon: Github },
    { label: "Twitter", href: "#", icon: Twitter },
    { label: "Discord", href: "#", icon: MessageCircle },
];

export function Footer() {
    return (
        <footer className="relative border-t border-border bg-background pb-24">
            <div className="container mx-auto px-4 pt-16 md:px-6">
                <div className="mb-12 grid grid-cols-2 gap-8 md:grid-cols-4">
                    <div className="col-span-2 md:col-span-1">
                        <Link href="/" className="mb-4 flex items-center gap-2">
                            <span className="chip-brand h-8 w-8">
                                <Activity className="h-4 w-4" />
                            </span>
                            <span className="font-mono text-lg font-semibold tracking-tight text-foreground">
                                CryptAI
                            </span>
                        </Link>
                        <p className="body-sm mb-6 max-w-xs">
                            Autonomous, agent-based crypto trading infrastructure. Built for
                            performance, safety, and scale.
                        </p>
                        <div className="flex gap-3">
                            {socials.map(({ label, href, icon: Icon }) => (
                                <Link
                                    key={label}
                                    href={href}
                                    aria-label={label}
                                    className="flex h-9 w-9 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors hover:border-accent/45 hover:text-accent"
                                >
                                    <Icon className="h-4 w-4" />
                                </Link>
                            ))}
                        </div>
                    </div>

                    {columns.map((col) => (
                        <div key={col.heading}>
                            <h4 className="label-md mb-4 text-foreground">{col.heading}</h4>
                            <ul className="space-y-2.5">
                                {col.links.map((link) => (
                                    <li key={link.label}>
                                        <Link
                                            href={link.href}
                                            className="body-sm transition-colors hover:text-accent"
                                        >
                                            {link.label}
                                        </Link>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    ))}
                </div>

                <div className="flex flex-col items-center justify-between gap-4 border-t border-border pt-8 md:flex-row">
                    <p className="body-xs">
                        © {new Date().getFullYear()} CryptAI. All rights reserved.
                    </p>
                    <div className="body-xs flex items-center gap-2">
                        <span className="h-2 w-2 rounded-full bg-profit animate-pulse-subtle" />
                        All systems operational
                    </div>
                </div>
            </div>

            <LiveTicker />
        </footer>
    );
}
