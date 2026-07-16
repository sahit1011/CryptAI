import { NextResponse } from "next/server";

// USD -> INR rate for display. Crypto is quoted in USD/USDT everywhere (Binance,
// BingX, Delta perpetuals), so we keep values in USD internally and convert to ₹ at
// render time. Cached ~1h; falls back to a sensible constant if the source is down.
export const revalidate = 3600;
const FALLBACK = 87.5;

export async function GET() {
    try {
        const res = await fetch("https://open.er-api.com/v6/latest/USD", {
            next: { revalidate: 3600 },
            signal: AbortSignal.timeout(6000),
        });
        const data = await res.json();
        const rate = data?.rates?.INR;
        if (typeof rate === "number" && rate > 0) {
            return NextResponse.json({ rate, source: "open.er-api.com" });
        }
    } catch {
        /* fall through to fallback */
    }
    return NextResponse.json({ rate: FALLBACK, source: "fallback" });
}
