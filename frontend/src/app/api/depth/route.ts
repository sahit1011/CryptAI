import { NextRequest, NextResponse } from "next/server";

// Server-side order-book snapshot proxy. The backend WS only streams a 5-level
// BTCUSDT diff — a terminal book needs depth for every desk symbol. The browser
// can't hit Binance directly (no CORS), so this route fetches server-side:
// USDⓈ-M futures first (the trading venue), then spot, then the data mirror.
// Response: { lastUpdateId, bids: [[price, qty]...], asks: [[...]], ts }.

export const dynamic = "force-dynamic";

const VALID_LIMITS = new Set([5, 10, 20, 50, 100]);

const HOSTS = [
  { base: "https://fapi.binance.com", path: "/fapi/v1/depth" },   // USD-M futures
  { base: "https://api.binance.com", path: "/api/v3/depth" },     // spot
  { base: "https://data-api.binance.vision", path: "/api/v3/depth" }, // data mirror
];

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const symbol = (params.get("symbol") || "BTCUSDT").toUpperCase().replace(/[^A-Z0-9]/g, "");
  const limitRaw = parseInt(params.get("limit") || "50", 10);
  const limit = VALID_LIMITS.has(limitRaw) ? limitRaw : 50;

  for (const host of HOSTS) {
    try {
      const url = `${host.base}${host.path}?symbol=${symbol}&limit=${limit}`;
      const res = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(5000) });
      if (!res.ok) continue;
      const data = await res.json();
      if (!Array.isArray(data?.bids) || !Array.isArray(data?.asks)) continue;
      return NextResponse.json(
        { lastUpdateId: data.lastUpdateId ?? null, bids: data.bids, asks: data.asks, ts: Date.now() },
        { headers: { "Cache-Control": "public, max-age=2, stale-while-revalidate=5" } },
      );
    } catch {
      /* try next host */
    }
  }

  return NextResponse.json({ error: "depth upstream unavailable" }, { status: 502 });
}
