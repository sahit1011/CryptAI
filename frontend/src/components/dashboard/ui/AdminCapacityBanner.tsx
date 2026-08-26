"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ServerCog } from "lucide-react";

import { getEngine, type EngineStatus } from "@/lib/api";
import { useSession } from "@/hooks/useSession";

/**
 * Tells the operator — and only the operator — that nobody can scan right now.
 *
 * The bug that started this redesign was invisible to the one person who could fix it:
 * analysis was paused, every user's scan produced nothing, and the owner's own dashboard
 * looked completely normal. Capacity being down is loud for admins by construction now.
 *
 * Admin status still comes from GET /api/engine (the backend decides who is an owner).
 * Capacity itself comes from the session poll — that is the single source the UI acts
 * on, since reconciling two independent switches in the client was the original bug.
 */
export function AdminCapacityBanner() {
    const { capacity } = useSession();
    const [engine, setEngine] = useState<EngineStatus | null>(null);

    useEffect(() => {
        let cancelled = false;
        getEngine()
            .then((e) => !cancelled && setEngine(e))
            .catch(() => { /* not an admin, or the endpoint is down — stay silent */ });
        return () => {
            cancelled = true;
        };
    }, []);

    if (!engine?.is_admin) return null;
    if (!capacity || capacity.available) return null;

    return (
        <div className="flex items-center gap-2 border-b border-loss/40 bg-loss-muted px-4 py-2 text-xs text-loss">
            <ServerCog className="size-3.5 shrink-0" />
            <span className="font-medium">Capacity paused — nobody can scan right now.</span>
            <span className="text-loss/80">
                Users see &ldquo;analysis is offline&rdquo;; their scan time is not being spent.
            </span>
            <Link
                href="/admin/ops"
                className="ml-auto rounded-md border border-loss/40 px-2 py-0.5 font-medium hover:bg-loss/10"
            >
                Ops →
            </Link>
        </div>
    );
}
