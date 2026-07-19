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
