"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
    ApiError,
    approveProposal,
    CAPACITY_UNAVAILABLE,
    endSession,
    getPendingProposal,
    getSession,
    rejectProposal,
    startSession,
    type ApproveResult,
    type GoalHorizon,
    type Proposal,
    type SessionCapacity,
    type SessionOverview,
} from "@/lib/api";
import { sessionPhase, type SessionPhase } from "@/lib/session";

/*
 * useSession — the metered-session control loop for the UI.
 *
 * Polls GET /api/session every 5s (the server clock is authoritative; the panel
 * ticks locally between polls), and fetches the pending proposal whenever the
 * session is paused on one. All mutations refetch rather than guessing state:
 * the state machine lives server-side and 409s are normal, not exceptional.
 *
 * Capacity rides on the same poll. Nothing here calls GET /api/engine: two
 * independent switches reconciled in the client is the bug this replaces.
 */

const POLL_MS = 5000;

export interface SessionApi {
    overview: SessionOverview | null;
    /** Whether scans can be produced at all, from the session poll. null before first load. */
    capacity: SessionCapacity | null;
    /** Capacity-aware phase; "idle" until the first poll lands (pair it with `loading`). */
    phase: SessionPhase;
    proposal: Proposal | null;
    loading: boolean;
    error: string | null;
    /** Last mutation's user-facing message (409 reasons, retry hints). */
    notice: string | null;
    /** Machine-readable cause of the last mutation failure, when the backend sent one.
     * Branch on this, never on `notice`. */
    noticeCode: string | null;
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
    const [noticeCode, setNoticeCode] = useState<string | null>(null);
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
            setNoticeCode(null);
            try {
                return await fn();
            } catch (e) {
                // 409s carry the state machine's honest reason ("price moved — you can
                // retry or reject"); surface them as notices, not failures. The capacity
                // 503 is the exception — its body is a machine code, and the refresh
                // below flips the phase to "blocked", which owns that copy.
                if (alive.current) {
                    const code = e instanceof ApiError ? e.code : null;
                    setNoticeCode(code);
                    setNotice(
                        code === CAPACITY_UNAVAILABLE
                            ? null
                            : e instanceof Error
                              ? e.message
                              : String(e),
                    );
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

    return {
        overview,
        capacity: overview?.capacity ?? null,
        phase: overview ? sessionPhase(overview) : "idle",
        proposal,
        loading,
        error,
        notice,
        noticeCode,
        busy,
        start,
        end,
        approve,
        reject,
        refresh,
    };
}
