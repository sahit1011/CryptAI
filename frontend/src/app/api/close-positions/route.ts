import { NextResponse } from "next/server";

/*
 * Secure server-side proxy for the DESTRUCTIVE "close all positions" control.
 *
 * The browser calls this SAME-ORIGIN route (POST /api/close-positions). We read
 * a SERVER-ONLY admin secret (no NEXT_PUBLIC_ prefix, so it is never bundled into
 * client JS) and forward the POST to the FastAPI backend's /api/close-positions,
 * attaching the secret as a bearer. This keeps the money-moving credential off
 * the client entirely.
 *
 * Env:
 *   - CRYPTAI_ADMIN_TOKEN (server-only) : admin bearer for destructive backend ops.
 *   - API_URL or NEXT_PUBLIC_API_URL    : backend base URL (server can read either).
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BACKEND_URL = (
  process.env.API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000"
).replace(/\/$/, "");

const ADMIN_TOKEN = process.env.CRYPTAI_ADMIN_TOKEN || "";

export async function POST() {
  if (!ADMIN_TOKEN) {
    // Fail closed: without a configured server secret we refuse to dispatch a
    // destructive action rather than silently sending an unauthenticated call.
    return NextResponse.json(
      {
        error:
          "close-positions is disabled: server admin token (CRYPTAI_ADMIN_TOKEN) is not configured.",
      },
      { status: 503 },
    );
  }

  try {
    const upstream = await fetch(`${BACKEND_URL}/api/close-positions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${ADMIN_TOKEN}`,
      },
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });

    const text = await upstream.text();
    // Pass through the backend's status + body (JSON when possible).
    let data: unknown;
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { message: text };
    }

    if (!upstream.ok) {
      return NextResponse.json(
        { error: `backend responded ${upstream.status}`, detail: data },
        { status: upstream.status },
      );
    }

    return NextResponse.json(data, { status: 200 });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    return NextResponse.json(
      { error: `failed to reach backend: ${message}` },
      { status: 502 },
    );
  }
}
