"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";

// Symbols to display, mapped to their Binance USDT pairs.
const SYMBOLS = [
    { name: "Bitcoin", symbol: "BTC", pair: "BTCUSDT" },
    { name: "Ethereum", symbol: "ETH", pair: "ETHUSDT" },
    { name: "Solana", symbol: "SOL", pair: "SOLUSDT" },
    { name: "Cardano", symbol: "ADA", pair: "ADAUSDT" },
    { name: "Ripple", symbol: "XRP", pair: "XRPUSDT" },
    { name: "Polkadot", symbol: "DOT", pair: "DOTUSDT" },
    { name: "Chainlink", symbol: "LINK", pair: "LINKUSDT" },
    { name: "Avalanche", symbol: "AVAX", pair: "AVAXUSDT" },
];

interface TickerEntry {
    symbol: string;
    price: string;
    change: string;
}

// Format a USD price as ₹ (India-first) at the given USD→INR rate.
function formatPrice(usd: number, rate: number): string {
    if (!isFinite(usd)) return "--";
    const inr = usd * rate;
    const decimals = inr >= 1000 ? 0 : 2;
    return `₹${inr.toLocaleString("en-IN", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    })}`;
}

export function LiveTicker() {
    // Live prices via our same-origin proxy (/api/ticker), which fetches Binance
    // server-side — avoids the browser CORS/ad-blocker/region failures of calling
    // api.binance.com directly. Renders nothing until real data arrives.
    const [ticks, setTicks] = useState<TickerEntry[]>([]);
    const [rate, setRate] = useState(87.5); // USD→INR; refined from /api/fx

    // Load the live USD→INR rate (landing page doesn't mount the dashboard store).
    useEffect(() => {
        fetch("/api/fx", { cache: "no-store" })
            .then((r) => r.json())
            .then((d) => { if (d?.rate) setRate(Number(d.rate)); })
            .catch(() => { /* keep default */ });
    }, []);

    useEffect(() => {
        let cancelled = false;

        const fetchPrices = async () => {
            try {
                const res = await fetch("/api/ticker", { cache: "no-store" });
                if (!res.ok) return;
                const json = await res.json();
                const bySymbol = new Map<string, { lastPrice: string; priceChangePercent: string }>(
                    (json.ticks || []).map((t: { symbol: string; lastPrice: string; priceChangePercent: string }) => [t.symbol, t])
                );
                const live: TickerEntry[] = [];
                for (const coin of SYMBOLS) {
                    const d = bySymbol.get(coin.pair);
                    if (!d) continue;
                    const pct = parseFloat(d.priceChangePercent);
                    live.push({
                        symbol: coin.symbol,
                        price: formatPrice(parseFloat(d.lastPrice), rate),
                        change: `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`,
                    });
                }
                if (!cancelled && live.length > 0) setTicks(live);
            } catch {
                // Contained: proxy/feed unavailable — leave the ticker hidden, no overlay.
            }
        };

        void fetchPrices();
        const interval = setInterval(() => void fetchPrices(), 30000); // refresh every 30s
        return () => {
            cancelled = true;
            clearInterval(interval);
        };
    }, [rate]);

    // Until real data arrives, render nothing rather than fabricated prices.
    if (ticks.length === 0) return null;

    return (
        <div className="fixed bottom-0 left-0 right-0 z-50 w-full bg-background/80 backdrop-blur-md border-t border-border py-3 overflow-hidden">
            <div className="absolute inset-y-0 left-0 w-32 bg-gradient-to-r from-background to-transparent z-10" />
            <div className="absolute inset-y-0 right-0 w-32 bg-gradient-to-l from-background to-transparent z-10" />

            <motion.div
                className="flex gap-12 whitespace-nowrap"
                animate={{ x: [0, -1000] }}
                transition={{
                    repeat: Infinity,
                    ease: "linear",
                    duration: 30
                }}
            >
                {[...ticks, ...ticks, ...ticks].map((coin, i) => (
                    <div key={i} className="flex items-center gap-3 text-sm">
                        <span className="font-mono font-bold text-foreground">{coin.symbol}</span>
                        <span className="font-mono text-muted-foreground">{coin.price}</span>
                        <span className={`font-mono ${coin.change.startsWith('+') ? "text-profit" : "text-loss"}`}>
                            {coin.change}
                        </span>
                    </div>
                ))}
            </motion.div>
        </div>
    );
}
