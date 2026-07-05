import { NextResponse } from "next/server";

// Server-side price proxy. Fetching a price feed directly from the browser fails in
// many setups (CORS, ad/privacy blockers, region blocks). We do it server-side and
// normalize everything to { symbol: <PAIR>, lastPrice, priceChangePercent }.
//
// Binance is the first choice, but it's region-blocked in many networks, so we fall
// back to CoinGecko (widely reachable) — same normalized output either way.
const COINS = [
  { symbol: "BTCUSDT", cg: "bitcoin" },
  { symbol: "ETHUSDT", cg: "ethereum" },
  { symbol: "SOLUSDT", cg: "solana" },
  { symbol: "ADAUSDT", cg: "cardano" },
  { symbol: "XRPUSDT", cg: "ripple" },
  { symbol: "DOTUSDT", cg: "polkadot" },
  { symbol: "LINKUSDT", cg: "chainlink" },
  { symbol: "AVAXUSDT", cg: "avalanche-2" },
];

export const dynamic = "force-dynamic";

interface Tick { symbol: string; lastPrice: string; priceChangePercent: string; }

async function fromBinance(): Promise<Tick[] | null> {
  const symbolsParam = encodeURIComponent(JSON.stringify(COINS.map((c) => c.symbol)));
  for (const host of ["https://api.binance.com", "https://data-api.binance.vision"]) {
    try {
      const res = await fetch(`${host}/api/v3/ticker/24hr?symbols=${symbolsParam}`, {
        cache: "no-store",
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) continue;
      const data = await res.json();
      if (!Array.isArray(data) || data.length === 0) continue;
      return data.map((d: { symbol: string; lastPrice: string; priceChangePercent: string }) => ({
        symbol: d.symbol,
        lastPrice: d.lastPrice,
        priceChangePercent: d.priceChangePercent,
      }));
    } catch {
      /* try next host */
    }
  }
  return null;
}

async function fromCoinGecko(): Promise<Tick[] | null> {
  try {
    const ids = COINS.map((c) => c.cg).join(",");
    const url = `https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=usd&include_24hr_change=true`;
    const res = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(6000) });
    if (!res.ok) return null;
    const data = await res.json();
    const ticks: Tick[] = [];
    for (const c of COINS) {
      const row = data?.[c.cg];
      if (!row || typeof row.usd !== "number") continue;
      ticks.push({
        symbol: c.symbol,
        lastPrice: String(row.usd),
        priceChangePercent: String(row.usd_24h_change ?? 0),
      });
    }
    return ticks.length > 0 ? ticks : null;
  } catch {
    return null;
  }
}

export async function GET() {
  const ticks = (await fromBinance()) ?? (await fromCoinGecko());
  if (ticks && ticks.length > 0) {
    return NextResponse.json(
      { ticks },
      { headers: { "Cache-Control": "public, max-age=15, stale-while-revalidate=30" } }
    );
  }
  return NextResponse.json({ ticks: [], error: "ticker upstream unavailable" }, { status: 502 });
}
