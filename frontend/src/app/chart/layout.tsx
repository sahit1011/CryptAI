import type { Metadata } from "next"

/**
 * Chart layout — deliberately bare. The chart owns the full viewport: no sidebar, no
 * max-width container, no page padding. Auth is enforced server-side by the middleware
 * (see PROTECTED_PREFIXES).
 *
 * Outside the (app) route group for exactly that reason: it is the one signed-in screen
 * that does not wear the shell.
 */

export const metadata: Metadata = {
    title: "Chart | CryptAI",
    description: "Live chart, order book, and market notes.",
}

export default function ChartLayout({ children }: { children: React.ReactNode }) {
    return <div className="h-dvh overflow-hidden bg-background text-foreground">{children}</div>
}
