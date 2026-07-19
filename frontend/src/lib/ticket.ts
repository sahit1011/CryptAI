/**
 * Trade-ticket domain logic — pure and unit-tested.
 *
 * The ticket is honestly a BRACKET ticket: the only placement route is
 * POST /api/execute-setup, and SIZING BELONGS TO THE RISK GATE — there is no
 * quantity field, ever. These helpers validate the bracket's geometry and
 * compute the preview numbers the ticket shows.
 */

export interface TicketDraft {
    direction: "LONG" | "SHORT"
    entry: number
    stopLoss: number
    takeProfits: number[]
}

export function validateTicket(d: TicketDraft): string[] {
    const errors: string[] = []
    const tps = d.takeProfits.filter((n) => Number.isFinite(n) && n > 0)

    if (!Number.isFinite(d.entry) || d.entry <= 0) errors.push("Entry must be a positive price.")
    if (!Number.isFinite(d.stopLoss) || d.stopLoss <= 0) errors.push("Stop loss must be a positive price.")
    if (tps.length === 0) errors.push("At least one take-profit level is required.")

    if (errors.length > 0) return errors

    if (d.direction === "LONG") {
        if (d.stopLoss >= d.entry) errors.push("LONG: stop loss must sit below entry.")
        for (const tp of tps) if (tp <= d.entry) errors.push("LONG: every take-profit must sit above entry.")
    } else {
        if (d.stopLoss <= d.entry) errors.push("SHORT: stop loss must sit above entry.")
        for (const tp of tps) if (tp >= d.entry) errors.push("SHORT: every take-profit must sit below entry.")
    }
    return [...new Set(errors)]
}

/** Risk:reward against TP1 (the bracket's first scale-out). NaN when invalid. */
export function riskReward(d: TicketDraft): number {
    const tp1 = d.takeProfits.find((n) => Number.isFinite(n) && n > 0)
    if (tp1 == null || !Number.isFinite(d.entry) || !Number.isFinite(d.stopLoss)) return NaN
    const risk = d.direction === "LONG" ? d.entry - d.stopLoss : d.stopLoss - d.entry
    const reward = d.direction === "LONG" ? tp1 - d.entry : d.entry - tp1
    if (risk <= 0) return NaN
    return reward / risk
}

/** Stop distance as a % of entry (what the trader is risking per unit). */
export function stopDistancePct(d: TicketDraft): number {
    if (!Number.isFinite(d.entry) || d.entry <= 0 || !Number.isFinite(d.stopLoss)) return NaN
    return (Math.abs(d.entry - d.stopLoss) / d.entry) * 100
}

/** The POST /api/execute-setup body for a valid draft.
 *
 * `confidence` is only present when the draft came from an AI setup — machine
 * scores stay gated by the risk calculator's confidence floor; a hand-built
 * bracket omits it (the backend treats the human's confirmation as confidence).
 */
export function toExecutePayload(symbol: string, d: TicketDraft, confidence?: number): Record<string, unknown> {
    return {
        symbol,
        direction: d.direction,
        entry_price: d.entry,
        stop_loss: d.stopLoss,
        take_profit_levels: d.takeProfits.filter((n) => Number.isFinite(n) && n > 0),
        ...(confidence != null && Number.isFinite(confidence) ? { confidence_score: confidence } : {}),
    }
}
