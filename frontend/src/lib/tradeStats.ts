import type { Trade } from "@/store/useStore";

/*
 * Derived performance stats from settled (closed) trade history. These are the
 * REAL numbers from /api/trades — the same record the "Recent Closed Trades"
 * list renders — surfaced honestly so the dashboard reflects what happened,
 * instead of showing "no data" while a full trade log sits right below.
 *
 * Everything here is realized (locked-in) performance. Live account equity /
 * balances still come only from the WS feed; these never invent a balance.
 */

export type PerSymbol = { symbol: string; pnl: number; trades: number; wins: number };

export type TradeStats = {
    closedCount: number;
    realizedPnl: number;
    wins: number;
    losses: number;
    winRate: number; // 0–100
    best: number; // largest single-trade P&L
    worst: number; // most negative single-trade P&L
    avgWin: number;
    avgLoss: number; // negative or 0
    profitFactor: number; // gross profit / gross loss (Infinity if no losses)
    perSymbol: PerSymbol[]; // sorted by |pnl| desc
    /** Cumulative realized P&L, oldest → newest close. Starts at 0. */
    equityCurve: number[];
};

export function isClosed(t: Trade): boolean {
    return (t.status && t.status.toUpperCase() === "CLOSED") || Boolean(t.exitTime);
}

export function closedTrades(trades: Trade[]): Trade[] {
    return trades.filter(isClosed);
}

const EMPTY: TradeStats = {
    closedCount: 0,
    realizedPnl: 0,
    wins: 0,
    losses: 0,
    winRate: 0,
    best: 0,
    worst: 0,
    avgWin: 0,
    avgLoss: 0,
    profitFactor: 0,
    perSymbol: [],
    equityCurve: [],
};

export function computeTradeStats(trades: Trade[]): TradeStats {
    const closed = closedTrades(trades);
    if (closed.length === 0) return EMPTY;

    // Oldest → newest by exit time, so the equity curve reads left-to-right.
    const chrono = [...closed].sort((a, b) => {
        const ta = a.exitTime ? Date.parse(a.exitTime) : 0;
        const tb = b.exitTime ? Date.parse(b.exitTime) : 0;
        return ta - tb;
    });

    let realizedPnl = 0;
    let wins = 0;
    let losses = 0;
    let grossProfit = 0;
    let grossLoss = 0;
    let best = -Infinity;
    let worst = Infinity;
    const equityCurve: number[] = [0];
    const bySymbol = new Map<string, PerSymbol>();

    for (const t of chrono) {
        const pnl = t.pnl ?? 0;
        realizedPnl += pnl;
        equityCurve.push(realizedPnl);
        if (pnl >= 0) {
            wins += 1;
            grossProfit += pnl;
        } else {
            losses += 1;
            grossLoss += Math.abs(pnl);
        }
        best = Math.max(best, pnl);
        worst = Math.min(worst, pnl);

        const row = bySymbol.get(t.symbol) ?? { symbol: t.symbol, pnl: 0, trades: 0, wins: 0 };
        row.pnl += pnl;
        row.trades += 1;
        if (pnl >= 0) row.wins += 1;
        bySymbol.set(t.symbol, row);
    }

    const perSymbol = [...bySymbol.values()].sort((a, b) => Math.abs(b.pnl) - Math.abs(a.pnl));

    return {
        closedCount: closed.length,
        realizedPnl,
        wins,
        losses,
        winRate: (wins / closed.length) * 100,
        best: best === -Infinity ? 0 : best,
        worst: worst === Infinity ? 0 : worst,
        avgWin: wins > 0 ? grossProfit / wins : 0,
        avgLoss: losses > 0 ? -(grossLoss / losses) : 0,
        profitFactor: grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0,
        perSymbol,
        equityCurve,
    };
}
