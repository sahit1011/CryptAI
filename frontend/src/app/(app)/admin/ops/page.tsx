"use client";

import Link from "next/link";
import { ArrowLeft, ServerCog } from "lucide-react";

import { EngineControl } from "@/components/dashboard/ui/EngineControl";

/**
 * /admin/ops — operator controls. Deliberately absent from the nav rail.
 *
 * The analysis-capacity switch lives here rather than in user Settings because it is
 * OUR cost throttle, not a user preference. Sitting in Settings it read as a feature the
 * user was supposed to operate — and when it was off, their scans silently produced
 * nothing ("what exactly is my start engine?"). Users now see the consequence
 * ("Market analysis is offline — your scan time is safe") and never the control.
 *
 * EngineControl renders null for non-admins, so this page is harmless if reached
 * directly; the real gate is the backend's require_admin on POST /api/engine.
 */
export default function AdminOpsPage() {
    return (
        <div className="mx-auto max-w-3xl">
            <Link
                href="/desk"
                className="mb-6 inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
            >
                <ArrowLeft className="size-3.5" />
                Back to desk
            </Link>

            <div className="mb-6 flex items-center gap-2">
                <ServerCog className="size-5 text-accent" />
                <div>
                    <h1 className="text-lg font-semibold text-foreground">Operations</h1>
                    <p className="text-xs text-muted-foreground">
                        Platform controls. Not visible to users — they see the effect, not the switch.
                    </p>
                </div>
            </div>

            <EngineControl />

            <p className="mt-6 rounded-lg border border-border/60 bg-elevated/30 p-3 text-xs leading-relaxed text-muted-foreground">
                While analysis capacity is off, nobody can start a scan: the start endpoint
                refuses with no session created, and any scan already running is ended with
                its dead time refunded. Open positions keep being watched regardless —
                monitoring never depends on this switch.
            </p>
        </div>
    );
}
