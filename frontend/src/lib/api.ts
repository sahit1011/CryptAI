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
 * Build the WebSocket URL, appending `?token=` when a read-only token is set.
 * The backend accepts `?token=` on the /ws handshake because browsers cannot
 * attach an Authorization header to a WS upgrade. Without this, enabling the
 * backend's API_AUTH_TOKEN silently rejects the browser's WS connection.
 */
export function buildWsUrl(base: string = WS_URL): string {
    if (!API_TOKEN) return base;
    try {
        const url = new URL(base);
        url.searchParams.set("token", API_TOKEN);
        return url.toString();
    } catch {
        // Fallback for non-absolute/edge inputs: manual append.
        const sep = base.includes("?") ? "&" : "?";
        return `${base}${sep}token=${encodeURIComponent(API_TOKEN)}`;
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
