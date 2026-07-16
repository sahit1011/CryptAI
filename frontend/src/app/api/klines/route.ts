import { NextRequest, NextResponse } from "next/server";

// Server-side klines (candlestick) proxy. The browser can't call Binance directly —
// its public API sends no CORS headers, so a client fetch is blocked (and region/ad
// blockers make it worse). We fetch server-side and return Binance's raw kline array
// unchanged: [openTime, open, high, low, close, volume, ...].
//
// Tries Binance USDⓈ-M futures first (matches the trading venue), then spot, then the
// data-only vision host, so a single region block doesn't break the chart.

export const dynamic = "force-dynamic";

const VALID_INTERVALS = new Set([
  "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w",
]);

const HOSTS = [
  { base: "https://fapi.binance.com", path: "/fapi/v1/klines" }, // USD-M futures
  { base: "https://api.binance.com", path: "/api/v3/klines" },   // spot
  { base: "https://data-api.binance.vision", path: "/api/v3/klines" }, // data mirror
];

// CoinGecko fallback (widely reachable where Binance is region-blocked). Its OHLC
// granularity is fixed by the `days` window, not the requested interval, so this is a
// best-effort degraded chart — no volume. Symbol -> CoinGecko id.
const CG_IDS: Record<string, string> = {
  BTCUSDT: "bitcoin", ETHUSDT: "ethereum", SOLUSDT: "solana", ADAUSDT: "cardano",
  XRPUSDT: "ripple", DOTUSDT: "polkadot", LINKUSDT: "chainlink", AVAXUSDT: "avalanche-2",
  PAXGUSDT: "pax-gold", XAUTUSDT: "tether-gold",   // tokenized gold (~1oz XAU)
};

function daysForInterval(interval: string): number {
  if (["1m", "3m", "5m", "15m", "30m"].includes(interval)) return 1;
  if (["1h", "2h", "4h"].includes(interval)) return 7;
  if (["6h", "8h", "12h"].includes(interval)) return 30;
  return 90; // 1d / 3d / 1w
}

async function fromCoinGecko(symbol: string, interval: string): Promise<unknown[] | null> {
  const id = CG_IDS[symbol];
  if (!id) return null;
  try {
    const url = `https://api.coingecko.com/api/v3/coins/${id}/ohlc?vs_currency=usd&days=${daysForInterval(interval)}`;
    const res = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(7000) });
    if (!res.ok) return null;
    const data = await res.json();
    if (!Array.isArray(data) || data.length === 0) return null;
    // CoinGecko: [ts_ms, o, h, l, c] -> Binance kline shape [openTime, o, h, l, c, volume].
    return data.map((r: number[]) => [r[0], String(r[1]), String(r[2]), String(r[3]), String(r[4]), "0"]);
  } catch {
    return null;
  }
}

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const symbol = (params.get("symbol") || "BTCUSDT").toUpperCase().replace(/[^A-Z0-9]/g, "");
  const interval = params.get("interval") || "1m";
  const limitRaw = parseInt(params.get("limit") || "500", 10);
  const limit = Math.max(1, Math.min(Number.isFinite(limitRaw) ? limitRaw : 500, 1000));

  if (!VALID_INTERVALS.has(interval)) {
    return NextResponse.json({ error: "invalid interval" }, { status: 400 });
  }

  for (const host of HOSTS) {
    try {
      const url = `${host.base}${host.path}?symbol=${symbol}&interval=${interval}&limit=${limit}`;
      const res = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(6000) });
      if (!res.ok) continue;
      const data = await res.json();
      if (!Array.isArray(data) || data.length === 0) continue;
      return NextResponse.json(data, {
        headers: { "Cache-Control": "public, max-age=10, stale-while-revalidate=30" },
      });
    } catch {
      /* try next host */
    }
  }

  // Binance unreachable (region block, etc.) — best-effort CoinGecko fallback.
  const cg = await fromCoinGecko(symbol, interval);
  if (cg) {
    return NextResponse.json(cg, {
      headers: { "Cache-Control": "public, max-age=30, stale-while-revalidate=60" },
    });
  }

  return NextResponse.json({ error: "klines upstream unavailable" }, { status: 502 });
}
