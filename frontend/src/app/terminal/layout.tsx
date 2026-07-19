import type { Metadata } from "next"

/**
 * Terminal layout — deliberately bare. The DESK owns the full viewport:
 * no dashboard sidebar, no max-width container, no page padding. Auth is
 * enforced server-side by the middleware (see PROTECTED_PREFIXES).
 */

export const metadata: Metadata = {
    title: "Terminal | CryptAI",
    description: "The CryptAI trading desk — live chart, order book, AI setups, and execution in one workspace.",
}

export default function TerminalLayout({ children }: { children: React.ReactNode }) {
    return <div className="h-dvh overflow-hidden bg-background text-foreground">{children}</div>
}
