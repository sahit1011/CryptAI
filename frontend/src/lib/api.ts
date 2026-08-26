/**
 * Centralized backend connection config.
 *
 * The dashboard talks to a FastAPI backend (REST + WebSocket). Read-only URLs
 * and the OPTIONAL read-only bearer token are build-time public env vars so the
 * same bundle can point at localhost in dev and a real host in production.
 *
 * SECURITY:
 *   - `NEXT_PUBLIC_API_TOKEN` is a READ-ONLY token. It is fine to bundle it for
 *     GET requests and the WS handshake (browsers can't send Authorization on a
 *     WS upgrade, so it goes on the query string — see `buildWsUrl`).
 *   - DESTRUCTIVE / money-moving actions (close-positions) MUST NOT be gated by a
 *     bundled admin token. They go through the same-origin Next.js server route
 *     `/api/close-positions`, which reads a SERVER-only secret (no NEXT_PUBLIC_
 *     prefix) and forwards the call. The admin secret never reaches the browser.
 *
 * NOTE: ws:// / http:// are blocked as mixed content on an https deployment —
 * set NEXT_PUBLIC_WS_URL / NEXT_PUBLIC_API_URL to wss:// / https:// in prod.
 */

// Base REST URL, e.g. http://localhost:8000 (no trailing slash expected).
export const API_URL =
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

// Full WebSocket URL, e.g. ws://localhost:8000/ws.
export const WS_URL =
    process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws";

// Optional READ-ONLY bearer token (GET requests + WS handshake only). Legacy /
// service fallback — the primary credential for a logged-in user is their Supabase
// access token (see authHeaders), which the backend verifies to scope data per user.
export const API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN || "";

/**
 * Bearer token for authenticated API calls: the current user's Supabase access token
 * (a signed JWT the backend verifies to resolve the tenant). Falls back to the static
 * read-only token, then empty. Async because the session is read from the Supabase
 * client. This is what makes reads user-scoped instead of showing one global account.
 */
export async function getAccessToken(): Promise<string> {
    try {
        const { createClient } = await import("@/utils/supabase/client");
        const { data } = await createClient().auth.getSession();
        if (data.session?.access_token) return data.session.access_token;
    } catch {
        /* not signed in / client unavailable — fall back */
    }
    return API_TOKEN;
}

/** Async header builder that attaches the user's Supabase token (preferred over apiHeaders). */
export async function authHeaders(json = false): Promise<HeadersInit> {
    const headers: Record<string, string> = {};
    if (json) headers["Content-Type"] = "application/json";
    const token = await getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return headers;
}

/**
 * Build request headers for a READ-ONLY backend API call, adding the read-only
 * bearer token when configured. Pass `json: true` to set the JSON content type.
 * Do NOT use this for destructive actions — route those through the Next server.
 */
export function apiHeaders(json = false): HeadersInit {
    const headers: Record<string, string> = {};
    if (json) headers["Content-Type"] = "application/json";
    if (API_TOKEN) headers["Authorization"] = `Bearer ${API_TOKEN}`;
    return headers;
}

/**
 * Build the WebSocket URL, appending `?token=<jwt>` so the backend can authenticate
 * the handshake and scope the socket to this user (browsers can't set an Authorization
 * header on a WS upgrade). Uses the user's Supabase access token when signed in, else
 * the static read-only token. Async because the session is read from the Supabase client.
 */
export async function buildWsUrl(base: string = WS_URL): Promise<string> {
    const token = await getAccessToken();
    if (!token) return base;
    try {
        const url = new URL(base);
        url.searchParams.set("token", token);
        return url.toString();
    } catch {
        // Fallback for non-absolute/edge inputs: manual append.
        const sep = base.includes("?") ? "&" : "?";
        return `${base}${sep}token=${encodeURIComponent(token)}`;
    }
}

/**
 * DESTRUCTIVE: dispatch the backend's emergency "close all positions" control.
 *
 * Calls the SAME-ORIGIN Next.js route (`/api/close-positions`), which holds the
 * server-only admin secret and forwards to the backend. The browser never sees
 * that secret. Returns the parsed JSON on success; throws with a useful message
 * (including the server's detail) on failure.
 */
export async function closePositions(): Promise<unknown> {
    const res = await fetch("/api/close-positions", { method: "POST" });
    if (!res.ok) {
        let detail = "";
        try {
            const body = await res.json();
            detail = typeof body?.error === "string" ? body.error : JSON.stringify(body);
        } catch {
            detail = await res.text().catch(() => "");
        }
        throw new Error(`HTTP ${res.status}${detail ? `: ${detail}` : ""}`);
    }
    return res.json().catch(() => ({}));
}

// ---------------------------------------------------------------------------
// Exchange-key vault (per-user onboarding). These are AUTHENTICATED, user-scoped
// calls — they carry the signed-in user's Supabase JWT (authHeaders), so the
// backend stores/reads keys against that tenant only. Secrets go straight to the
// backend vault over the POST body; they are never persisted client-side.
// ---------------------------------------------------------------------------

/** Non-secret status of the caller's stored exchange keys (from GET /api/exchange-keys). */
export interface ExchangeKeyStatus {
    connected: boolean;
    exchange?: string;
    label?: string | null;
    is_testnet?: boolean;
    api_key_masked?: string;
    error?: string;
}

export interface SaveExchangeKeysBody {
    api_key: string;
    api_secret: string;
    exchange?: string;
    label?: string | null;
    is_testnet?: boolean;
}

/** Pull the backend's error `detail` (FastAPI shape) out of a failed response. */
async function backendError(res: Response): Promise<string> {
    try {
        const body = await res.json();
        if (typeof body?.detail === "string") return body.detail;
        if (typeof body?.error === "string") return body.error;
        return JSON.stringify(body);
    } catch {
        return (await res.text().catch(() => "")) || `HTTP ${res.status}`;
    }
}

/** Current user's stored-key status (masked). Requires a signed-in user. */
export async function getExchangeKeys(): Promise<ExchangeKeyStatus> {
    const res = await fetch(`${API_URL}/api/exchange-keys`, {
        headers: await authHeaders(),
        cache: "no-store",
    });
    if (!res.ok) throw new Error(await backendError(res));
    return res.json();
}

/** Store (encrypted, server-side) the user's own exchange keys. Testnet-only for now. */
export async function saveExchangeKeys(body: SaveExchangeKeysBody): Promise<ExchangeKeyStatus> {
    const res = await fetch(`${API_URL}/api/exchange-keys`, {
        method: "POST",
        headers: await authHeaders(true),
        body: JSON.stringify({ exchange: "bingx", is_testnet: true, ...body }),
    });
    if (!res.ok) throw new Error(await backendError(res));
    return res.json();
}

/** Remove the user's stored keys for an exchange. */
export async function deleteExchangeKeys(exchange = "bingx"): Promise<ExchangeKeyStatus> {
    const res = await fetch(
        `${API_URL}/api/exchange-keys?exchange=${encodeURIComponent(exchange)}`,
        { method: "DELETE", headers: await authHeaders() },
    );
    if (!res.ok) throw new Error(await backendError(res));
    return res.json();
}

// ---------------------------------------------------------------------------
// Trading settings (per-user mode + active exchange) and setup suggestions.
// ---------------------------------------------------------------------------

export type TradingMode = "off" | "paper" | "manual" | "auto";
export interface UserSettings {
    trading_mode: TradingMode;
    active_exchange: string;
    onboarded?: boolean;
}

/** The caller's trading mode + active exchange (safe defaults if unset). */
export async function getSettings(): Promise<UserSettings> {
    const res = await fetch(`${API_URL}/api/settings`, {
        headers: await authHeaders(),
        cache: "no-store",
    });
    if (!res.ok) throw new Error(await backendError(res));
    return res.json();
}

/** Update the caller's trading mode / active exchange. */
export async function saveSettings(body: Partial<UserSettings>): Promise<UserSettings> {
    const res = await fetch(`${API_URL}/api/settings`, {
        method: "POST",
        headers: await authHeaders(true),
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await backendError(res));
    return res.json();
}

export interface EngineStatus {
    enabled: boolean;
    expires_in_seconds: number | null;  // null = "always on" (or off)
    enabled_by: string | null;
    is_admin?: boolean;
}

/** AI-engine status (any logged-in user); is_admin gates the control UI. */
export async function getEngine(): Promise<EngineStatus> {
    const res = await fetch(`${API_URL}/api/engine`, {
        headers: await authHeaders(),
        cache: "no-store",
    });
    if (!res.ok) throw new Error(await backendError(res));
    return res.json();
}

/** Turn the AI engine on/off (owner only). durationSeconds null = always on. */
export async function setEngine(enabled: boolean, durationSeconds?: number | null): Promise<EngineStatus> {
    const res = await fetch(`${API_URL}/api/engine`, {
        method: "POST",
        headers: await authHeaders(true),
        body: JSON.stringify({ enabled, duration_seconds: durationSeconds ?? null }),
    });
    if (!res.ok) throw new Error(await backendError(res));
    return res.json();
}

export interface PortfolioPayload {
    mode?: "paper" | "live";
    pending?: boolean;
    initial_balance: number;
    current_balance: number;
    total_equity: number;
    unrealized_pnl: number;
    realized_pnl: number;
    win_rate: number;
    total_trades: number;
}

/** The caller's portfolio — persisted state, or a seeded paper account. */
export async function getPortfolio(): Promise<PortfolioPayload | null> {
    const res = await fetch(`${API_URL}/api/portfolio`, {
        headers: await authHeaders(),
        cache: "no-store",
    });
    if (!res.ok) return null;
    return res.json();
}

/** Recent trade-setup suggestions (shared across users) for load-time hydration. */
export async function getSetups(): Promise<{ setups: Record<string, unknown>[] }> {
    const res = await fetch(`${API_URL}/api/setups`, { cache: "no-store" });
    if (!res.ok) throw new Error(await backendError(res));
    return res.json();
}

/** Manually execute a setup as a full bracket on the caller's connected exchange. */
export async function executeSetup(setup: Record<string, unknown>): Promise<Record<string, unknown>> {
    const res = await fetch(`${API_URL}/api/execute-setup`, {
        method: "POST",
        headers: await authHeaders(true),
        body: JSON.stringify(setup),
    });
    if (!res.ok) throw new Error(await backendError(res));
    return res.json();
}

/** The caller's open (resting) orders — e.g. a bracket's SL/TP legs. */
export async function getOpenOrders(): Promise<{ orders: Record<string, unknown>[]; source?: string }> {
    const res = await fetch(`${API_URL}/api/orders`, {
        headers: await authHeaders(),
        cache: "no-store",
    });
    if (!res.ok) throw new Error(await backendError(res));
    return res.json();
}

/** Cancel ONE of the caller's resting orders. */
export async function cancelOrder(orderId: string, symbol: string): Promise<Record<string, unknown>> {
    const res = await fetch(
        `${API_URL}/api/orders/${encodeURIComponent(orderId)}?symbol=${encodeURIComponent(symbol)}`,
        { method: "DELETE", headers: await authHeaders() },
    );
    if (!res.ok) throw new Error(await backendError(res));
    return res.json();
}

// ---------------------------------------------------------------------------
// Metered trading sessions + proposals (the M2 control plane).
// ---------------------------------------------------------------------------

/** Error that keeps the HTTP status, so the UI can tell a 409 refusal (show the
 * backend's reason, refetch state) from a 504 (engine busy — safe to retry). */
export class ApiError extends Error {
    status: number;
    /** Machine-readable `detail.code` when the backend sent a structured body
     * (e.g. "capacity_unavailable" on the start gate's 503). Callers branch on this
     * instead of pattern-matching prose that copy edits will break. */
    code: string | null;
    constructor(status: number, message: string, code: string | null = null) {
        super(message);
        this.status = status;
        this.code = code;
    }
}

/** `detail.code` of the 503 from POST /api/session/start when analysis capacity is
 * down. That response creates no session row, no clock and no event. */
export const CAPACITY_UNAVAILABLE = "capacity_unavailable";

/** True for the capacity 503 above — the one start failure that is not the user's fault
 * and must not read as an error. */
export function isCapacityUnavailable(err: unknown): boolean {
    return err instanceof ApiError && err.code === CAPACITY_UNAVAILABLE;
}

/** Like `backendError`, but also lifts a structured `{detail: {code, ...}}` body.
 * FastAPI raises both shapes: a plain string detail for prose refusals, an object for
 * the gates the client has to handle by cause. */
async function backendFailure(res: Response): Promise<{ message: string; code: string | null }> {
    try {
        const body: unknown = await res.json();
        const detail = (body as { detail?: unknown } | null)?.detail;
        if (detail && typeof detail === "object") {
            const d = detail as Record<string, unknown>;
            const code = typeof d.code === "string" ? d.code : null;
            const message =
                typeof d.message === "string" ? d.message : code ?? JSON.stringify(detail);
            return { message, code };
        }
        if (typeof detail === "string") return { message: detail, code: null };
        const err = (body as { error?: unknown } | null)?.error;
        if (typeof err === "string") return { message: err, code: null };
        return { message: JSON.stringify(body), code: null };
    } catch {
        return {
            message: (await res.text().catch(() => "")) || `HTTP ${res.status}`,
            code: null,
        };
    }
}

export type SessionStatus = "scanning" | "setup_proposed" | "executing" | "ended";

export interface TradingSession {
    session_id: string;
    status: SessionStatus;
    channel: GoalHorizon | null;
    quota_seconds_granted: number;
    elapsed_seconds: number;
    remaining_seconds: number;
    clock_running: boolean;
    llm_tokens_used: number;
    llm_cost_micros: number;
    llm_cost_cap_micros: number;
    cycles_completed: number;
    /** When a scan cycle last reported. null = nothing has reported yet this session.
     * The UI may not claim the agents are working without a fresh one. */
    last_cycle_at: string | null;
    /** How long a cycle is expected to take, so the client can judge staleness against
     * the same number the server paces on instead of a hardcoded guess. */
    expected_cycle_seconds: number;
    /** Metered seconds handed back (mid-scan capacity loss). 0 unless time was returned;
     * the refund is already deducted from `elapsed_seconds`. */
    seconds_refunded: number;
    started_at: string | null;
    ended_at: string | null;
    end_reason: string | null;
}

/** Why analysis capacity is unavailable. Internal vocabulary — never rendered; the UI
 * maps it to the "Market analysis is offline" copy. */
export type CapacityReason = "paused" | "degraded" | "model_error";

/** Whether new scans can be produced at all, folded into the session poll so the UI
 * never reconciles two independent switches (that reconciliation WAS the bug). */
export interface SessionCapacity {
    available: boolean;
    reason: CapacityReason | null;
    eta_seconds: number | null;
}

export interface SessionOverview {
    session: TradingSession | null;
    capacity: SessionCapacity;
    daily_quota_seconds: number;
    used_today_seconds: number;
    remaining_today_seconds: number;
}

/** True only when the payload positively says capacity is down. A backend that predates
 * the `capacity` key reads as available: the client gate is UX, the 503 on start is the
 * correctness gate, so failing open here can cost a wasted tap but never a wrong scan. */
export function isCapacityDown(overview: SessionOverview | null | undefined): boolean {
    return overview?.capacity?.available === false;
}

export interface Proposal {
    proposal_id: string;
    session_id: string;
    symbol: string;
    direction: "LONG" | "SHORT";
    entry_price: number;
    stop_loss: number;
    take_profit_levels: { price: number }[];
    position_size: number;
    risk_amount: number;
    risk_currency: string;
    risk_reward_ratio: number;
    leverage: number;
    confidence_score: number | null;
    thesis: string | null;
    strategy_type: string | null;
    market_regime: string | null;
    status: string;
    expires_at: string | null;
    created_at: string | null;
}

export interface ApproveResult {
    session: TradingSession;
    execution: { approved: boolean; recovered?: boolean; execution_id?: string | null };
    proposal_id: string;
}

async function sessionFetch<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${API_URL}${path}`, {
        cache: "no-store",
        ...init,
        headers: await authHeaders(init?.method === "POST"),
    });
    if (!res.ok) {
        const { message, code } = await backendFailure(res);
        throw new ApiError(res.status, message, code);
    }
    return res.json();
}

/** The caller's active session plus today's quota. `session: null` = idle (normal). */
export async function getSession(): Promise<SessionOverview> {
    return sessionFetch("/api/session");
}

/** Begin a metered session. 429 = daily quota spent (resets at UTC midnight).
 * 503 with `code: "capacity_unavailable"` (see `isCapacityUnavailable`) = analysis is
 * down; the backend creates no row, no clock and no event, so nothing was charged.
 * `channel` (scalp|intraday|swing|position) overrides the persona for this session. */
export async function startSession(
    opts: { channel?: GoalHorizon; quotaSeconds?: number } = {},
): Promise<TradingSession> {
    const body: Record<string, unknown> = {};
    if (opts.quotaSeconds) body.quota_seconds = opts.quotaSeconds;
    if (opts.channel) body.channel = opts.channel;
    return sessionFetch("/api/session/start", {
        method: "POST",
        body: JSON.stringify(body),
    });
}

/** End the caller's session early. Open positions keep being monitored. */
export async function endSession(): Promise<TradingSession> {
    return sessionFetch("/api/session/end", { method: "POST" });
}

/** The caller's newest pending proposal; null renders as "no card", not an error. */
export async function getPendingProposal(): Promise<{ proposal: Proposal | null }> {
    return sessionFetch("/api/proposals/pending");
}

/** Approve the pending proposal. The backend re-validates at the live price; a 409
 * with "retry" in the detail means the proposal is still live (price drifted). */
export async function approveProposal(): Promise<ApproveResult> {
    return sessionFetch("/api/session/approve", { method: "POST" });
}

/** Decline the pending proposal and resume scanning. */
export async function rejectProposal(): Promise<TradingSession> {
    return sessionFetch("/api/session/reject", { method: "POST" });
}

// ---------------------------------------------------------------------------
// Position monitors (M4) — the unmetered per-position watchers.
// ---------------------------------------------------------------------------

export interface MonitorStatus {
    symbol: string;
    position_id: string | null;
    decision: "hold" | "exit";
    reason: string | null;
    checks: number;
    favorable_pct: number;
    peak_favorable_pct: number;
    adverse_streak: number;
    updated_at: string;
}

export interface MonitorEntry {
    symbol: string;
    monitored: boolean;
    status: MonitorStatus | null;
}

/** Live monitor status for each of the caller's open positions. A symbol with no fresh
 * status reads monitored:false — honest when the monitor is down or undeployed. */
export async function getMonitors(): Promise<{ monitors: MonitorEntry[] }> {
    const res = await fetch(`${API_URL}/api/monitors`, {
        headers: await authHeaders(),
        cache: "no-store",
    });
    if (!res.ok) throw new Error(await backendError(res));
    return res.json();
}

// ---------------------------------------------------------------------------
// Trading preferences (the per-user persona the session pipeline reads).
// ---------------------------------------------------------------------------

export type RiskAppetite = "conservative" | "moderate" | "aggressive";
export type GoalHorizon = "scalp" | "intraday" | "swing" | "position";

export interface TradingPreferences {
    trading_capital: number;
    capital_currency: string;
    risk_appetite: RiskAppetite;
    max_risk_per_trade_pct: number;
    max_concurrent_positions: number;
    max_daily_trades: number;
    max_leverage: number;
    monthly_pnl_target_pct: number | null;
    goal_horizon: GoalHorizon;
    goal_notes: string | null;
    symbol_universe: string[] | null;
    allowed_strategies: string[] | null;
    min_risk_reward: number;
    min_confidence: number;
    avoid_high_funding: boolean;
}

/** The caller's trading persona (conservative defaults when unset). */
export async function getPreferences(): Promise<TradingPreferences> {
    const res = await fetch(`${API_URL}/api/preferences`, {
        headers: await authHeaders(),
        cache: "no-store",
    });
    if (!res.ok) throw new Error(await backendError(res));
    return res.json();
}

/** Partial update — only send what changed. Risk fields are clamped server-side to the
 * caller's plan and an absolute hard cap (preferences may only tighten risk, never widen). */
export async function savePreferences(
    updates: Partial<TradingPreferences>,
): Promise<TradingPreferences> {
    const res = await fetch(`${API_URL}/api/preferences`, {
        method: "POST",
        headers: await authHeaders(true),
        body: JSON.stringify(updates),
    });
    if (!res.ok) throw new Error(await backendError(res));
    return res.json();
}
