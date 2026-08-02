"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
    ApiError,
    approveProposal,
    endSession,
    getPendingProposal,
    getSession,
    rejectProposal,
    startSession,
    type ApproveResult,
    type GoalHorizon,
    type Proposal,
    type SessionOverview,
} from "@/lib/api";

/*
 * useSession — the metered-session control loop for the UI.
 *
 * Polls GET /api/session every 5s (the server clock is authoritative; the panel
 * ticks locally between polls), and fetches the pending proposal whenever the
 * session is paused on one. All mutations refetch rather than guessing state:
 * the state machine lives server-side and 409s are normal, not exceptional.
 */

const POLL_MS = 5000;

export interface SessionApi {
    overview: SessionOverview | null;
    proposal: Proposal | null;
    loading: boolean;
    error: string | null;
    /** Last mutation's user-facing message (409 reasons, retry hints). */
    notice: string | null;
    busy: boolean;
    start: (channel?: GoalHorizon) => Promise<void>;
    end: () => Promise<void>;
    approve: () => Promise<ApproveResult | null>;
    reject: () => Promise<void>;
    refresh: () => Promise<void>;
}

export function useSession(): SessionApi {
    const [overview, setOverview] = useState<SessionOverview | null>(null);
    const [proposal, setProposal] = useState<Proposal | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const alive = useRef(true);

    const refresh = useCallback(async () => {
        try {
            const data = await getSession();
            if (!alive.current) return;
            setOverview(data);
            setError(null);
            if (data.session?.status === "setup_proposed") {
                const p = await getPendingProposal();
                if (alive.current) setProposal(p.proposal);
            } else {
                setProposal(null);
            }
        } catch (e) {
            if (alive.current) setError(e instanceof Error ? e.message : String(e));
        } finally {
            if (alive.current) setLoading(false);
        }
    }, []);

    useEffect(() => {
        alive.current = true;
        refresh();
        const timer = setInterval(refresh, POLL_MS);
        return () => {
            alive.current = false;
            clearInterval(timer);
        };
    }, [refresh]);

    const mutate = useCallback(
        async <T>(fn: () => Promise<T>): Promise<T | null> => {
            setBusy(true);
            setNotice(null);
            try {
                return await fn();
            } catch (e) {
                // 409s carry the state machine's honest reason ("price moved — you can
                // retry or reject"); surface them as notices, not failures.
                if (alive.current) {
                    setNotice(e instanceof ApiError || e instanceof Error ? e.message : String(e));
                }
                return null;
            } finally {
                if (alive.current) setBusy(false);
                await refresh();
            }
        },
        [refresh],
    );

    const start = useCallback(
        async (channel?: GoalHorizon) => {
            await mutate(() => startSession({ channel }));
        },
        [mutate],
    );

    const end = useCallback(async () => {
        await mutate(() => endSession());
    }, [mutate]);

    const approve = useCallback(async () => {
        return mutate(() => approveProposal());
    }, [mutate]);

    const reject = useCallback(async () => {
        await mutate(() => rejectProposal());
    }, [mutate]);

    return { overview, proposal, loading, error, notice, busy, start, end, approve, reject, refresh };
}
