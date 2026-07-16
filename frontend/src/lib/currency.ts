/**
 * Currency display — INR-first.
 *
 * Market data (prices, balances, P&L) is denominated in USD/USDT internally because
 * that's how the exchanges quote it. For our India-first users we convert to ₹ at
 * DISPLAY time only, using a live USD→INR rate (see /api/fx + useStore.inrRate) and
 * `en-IN` grouping (lakh/crore). Never mutate stored USD values — format on the way out.
 */
export const DEFAULT_USD_INR = 87.5;

/** Format a USD amount as ₹ using the given rate and Indian digit grouping. */
export function formatInr(usd: number | null | undefined, rate: number, decimals = 2): string {
    if (usd == null || !Number.isFinite(Number(usd))) return "—";
    const inr = Number(usd) * (rate || DEFAULT_USD_INR);
    return inr.toLocaleString("en-IN", {
        style: "currency",
        currency: "INR",
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    });
}

/** Plain ₹ number (no currency symbol styling) for compact contexts. */
export function toInr(usd: number, rate: number): number {
    return usd * (rate || DEFAULT_USD_INR);
}
