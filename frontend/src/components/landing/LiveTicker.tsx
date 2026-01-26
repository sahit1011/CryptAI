"use client";

import { motion } from "framer-motion";
import { Bitcoin, Activity, DollarSign, TrendingUp } from "lucide-react";

const coins = [
    { name: "Bitcoin", symbol: "BTC", price: "$64,230", change: "+2.4%" },
    { name: "Ethereum", symbol: "ETH", price: "$3,450", change: "+1.8%" },
    { name: "Solana", symbol: "SOL", price: "$145", change: "+5.2%" },
    { name: "Cardano", symbol: "ADA", price: "$0.45", change: "-0.5%" },
    { name: "Ripple", symbol: "XRP", price: "$0.62", change: "+0.2%" },
    { name: "Polkadot", symbol: "DOT", price: "$7.20", change: "+1.1%" },
    { name: "Chainlink", symbol: "LINK", price: "$18.50", change: "+3.4%" },
    { name: "Avalanche", symbol: "AVAX", price: "$45.20", change: "+4.1%" },
];

export function LiveTicker() {
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
                {[...coins, ...coins, ...coins].map((coin, i) => (
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
