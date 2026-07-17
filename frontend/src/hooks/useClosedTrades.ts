"use client";

import { useEffect, useState } from "react";
import { API_URL, authHeaders } from "@/lib/api";
import type { Trade } from "@/store/useStore";
import { closedTrades } from "@/lib/tradeStats";

/*
 * useClosedTrades — the settled-trade record from /api/trades, polled every
 * 30s. Shared by Overview and Portfolio so both derive realized performance
 * from the same source (see lib/tradeStats).
 */
export function useClosedTrades(limit = 200) {
    const [trades, setTrades] = useState<Trade[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;
        const fetchTrades = async () => {
            try {
                const res = await fetch(`${API_URL}/api/trades?limit=${limit}`, {
                    cache: "no-store",
                    headers: await authHeaders(),
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                if (cancelled) return;
                if (Array.isArray(data.trades)) {
                    setTrades(data.trades);
                    setError(null);
                } else {
                    throw new Error("Invalid trades payload");
                }
            } catch (e) {
                if (!cancelled) setError(e instanceof Error ? e.message : String(e));
            } finally {
                if (!cancelled) setLoading(false);
            }
        };
        fetchTrades();
        const id = setInterval(fetchTrades, 30_000);
        return () => {
            cancelled = true;
            clearInterval(id);
        };
    }, [limit]);

    return { trades, closed: closedTrades(trades), loading, error };
}
