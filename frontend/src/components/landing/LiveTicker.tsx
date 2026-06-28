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

// Format a USD price with sensible precision (sub-$1 coins need more decimals).
function formatPrice(value: number): string {
    if (!isFinite(value)) return "--";
    const decimals = value >= 1 ? 2 : 4;
    return `$${value.toLocaleString("en-US", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    })}`;
}

export function LiveTicker() {
    // Real prices fetched from Binance's public 24h ticker endpoint (the same
    // public API the dashboard chart already uses). Falls back to nothing on
    // error rather than displaying fabricated prices.
    const [ticks, setTicks] = useState<TickerEntry[]>([]);

    useEffect(() => {
        let cancelled = false;

        const fetchPrices = async () => {
            try {
                const results = await Promise.all(
                    SYMBOLS.map(async (coin) => {
                        const res = await fetch(
                            `https://api.binance.com/api/v3/ticker/24hr?symbol=${coin.pair}`,
                            { cache: "no-store" }
                        );
                        if (!res.ok) throw new Error(`HTTP ${res.status}`);
                        const data = await res.json();
                        const pct = parseFloat(data.priceChangePercent);
                        return {
                            symbol: coin.symbol,
                            price: formatPrice(parseFloat(data.lastPrice)),
                            change: `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`,
                        };
                    })
                );
                if (!cancelled) setTicks(results);
            } catch (e) {
                console.error("LiveTicker: failed to fetch prices", e);
            }
        };

        fetchPrices();
        const interval = setInterval(fetchPrices, 30000); // refresh every 30s
        return () => {
            cancelled = true;
            clearInterval(interval);
        };
    }, []);

    // Until real data arrives, render nothing rather than fabricated prices.
    if (ticks.length === 0) return null;

    return (
        <div className="fixed bottom-0 left-0 right-0 z-50 w-full bg-[#0A0A0A]/80 backdrop-blur-md border-t border-white/10 py-3 overflow-hidden">
            <div className="absolute inset-y-0 left-0 w-32 bg-gradient-to-r from-[#0A0A0A] to-transparent z-10" />
            <div className="absolute inset-y-0 right-0 w-32 bg-gradient-to-l from-[#0A0A0A] to-transparent z-10" />

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
                        <span className="font-bold text-white">{coin.symbol}</span>
                        <span className="text-muted-foreground">{coin.price}</span>
                        <span className={coin.change.startsWith('+') ? "text-emerald-400" : "text-red-400"}>
                            {coin.change}
                        </span>
                    </div>
                ))}
            </motion.div>
        </div>
    );
}
