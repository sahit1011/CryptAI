import Link from "next/link";
import { Activity, Github, Twitter, Disc } from "lucide-react";

import { LiveTicker } from "./LiveTicker";
import { StatsSection } from "./StatsSection";

export function Footer() {
    return (
        <footer className="border-t border-white/10 bg-[#0A0A0A] pb-24 relative">
            <StatsSection />
            <div className="pt-16 container mx-auto px-4 md:px-6">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-12">
                    <div className="col-span-2 md:col-span-1">
                        <Link href="/" className="flex items-center gap-2 mb-4">
                            <div className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center border border-white/10">
                                <Activity className="w-5 h-5 text-white" />
                            </div>
                            <span className="text-lg font-bold text-white">CryptAI</span>
                        </Link>
                        <p className="text-sm text-muted-foreground leading-relaxed mb-6">
                            The next generation of algorithmic trading infrastructure. Built for performance, security, and scale.
                        </p>
                        <div className="flex gap-4">
                            <Link href="#" className="text-muted-foreground hover:text-white transition-colors">
                                <Github className="w-5 h-5" />
                            </Link>
                            <Link href="#" className="text-muted-foreground hover:text-white transition-colors">
                                <Twitter className="w-5 h-5" />
                            </Link>
                            <Link href="#" className="text-muted-foreground hover:text-white transition-colors">
                                <Disc className="w-5 h-5" />
                            </Link>
                        </div>
                    </div>

                    <div>
                        <h4 className="font-semibold text-white mb-4">Product</h4>
                        <ul className="space-y-2 text-sm text-muted-foreground">
                            <li><Link href="#" className="hover:text-white transition-colors">Features</Link></li>
                            <li><Link href="#" className="hover:text-white transition-colors">Integrations</Link></li>
                            <li><Link href="#" className="hover:text-white transition-colors">Pricing</Link></li>
                            <li><Link href="#" className="hover:text-white transition-colors">Changelog</Link></li>
                            <li><Link href="#" className="hover:text-white transition-colors">Docs</Link></li>
                        </ul>
                    </div>

                    <div>
                        <h4 className="font-semibold text-white mb-4">Company</h4>
                        <ul className="space-y-2 text-sm text-muted-foreground">
                            <li><Link href="#" className="hover:text-white transition-colors">About</Link></li>
                            <li><Link href="#" className="hover:text-white transition-colors">Blog</Link></li>
                            <li><Link href="#" className="hover:text-white transition-colors">Careers</Link></li>
                            <li><Link href="#" className="hover:text-white transition-colors">Contact</Link></li>
                        </ul>
                    </div>

                    <div>
                        <h4 className="font-semibold text-white mb-4">Legal</h4>
                        <ul className="space-y-2 text-sm text-muted-foreground">
                            <li><Link href="#" className="hover:text-white transition-colors">Privacy Policy</Link></li>
                            <li><Link href="#" className="hover:text-white transition-colors">Terms of Service</Link></li>
                            <li><Link href="#" className="hover:text-white transition-colors">Cookie Policy</Link></li>
                        </ul>
                    </div>
                </div>

                <div className="border-t border-white/5 pt-8 flex flex-col md:flex-row items-center justify-between gap-4">
                    <p className="text-xs text-muted-foreground">
                        © 2024 CryptAI. All rights reserved.
                    </p>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                        All Systems Operational
                    </div>
                </div>
            </div>
            <LiveTicker />
        </footer>
    );
}
