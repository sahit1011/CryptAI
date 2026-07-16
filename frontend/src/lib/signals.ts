import type { Signal } from "@/store/useStore";

/**
 * Map a backend trade-setup payload (WS `trade_setup` message or GET /api/setups row)
 * to the UI's Signal shape. Single source of truth — used by both the WS handler and
 * the Signals panel hydration, and unit-tested.
 *
 * Accepts either the enveloped `{ payload: {...} }` shape or the bare payload. Returns
 * null for rows without a symbol. The id is content-derived so WS replays and re-fetches
 * dedupe instead of duplicating cards.
 */
export function payloadToSignal(raw: unknown): Signal | null {
    const outer = (raw ?? {}) as Record<string, unknown>;
    const p = (outer.payload ?? outer) as Record<string, unknown>;
    if (!p.symbol) return null;

    const tps = (Array.isArray(p.take_profit_levels) ? p.take_profit_levels : [])
        .map((tp) =>
            typeof tp === "object" && tp !== null
                ? Number((tp as Record<string, unknown>).price)
                : Number(tp),
        )
        .filter((n) => Number.isFinite(n));

    const entry = Number(p.entry_price) || 0;
    const stopLoss = Number(p.stop_loss) || 0;

    return {
        id: `${p.symbol}-${p.direction}-${entry}-${stopLoss}`,
        symbol: String(p.symbol),
        direction: String(p.direction) === "SHORT" ? "SHORT" : "LONG",
        entry,
        stopLoss,
        takeProfits: tps,
        confidence: p.confidence_score != null ? Number(p.confidence_score) : undefined,
        riskReward: p.risk_reward != null ? Number(p.risk_reward) : undefined,
        regime: p.market_regime ? String(p.market_regime) : undefined,
        strategy: p.strategy_type ? String(p.strategy_type) : undefined,
        reasoning: typeof p.reasoning === "string" ? p.reasoning : undefined,
        positionSize:
            p.recommended_position_size != null ? Number(p.recommended_position_size) : undefined,
        ts: new Date().toISOString(),
    };
}
