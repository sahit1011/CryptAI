"use client"

import { useEffect, useRef } from 'react'
import { create } from 'zustand'
import { useStore } from '@/store/useStore'
import { buildWsUrl } from '@/lib/api'
import { safeNum, safeDiv } from '@/lib/utils'
import type { Trade } from '@/store/useStore'
import type { ConnState } from '@/components/ui/connection-status'

interface TickerData {
    s: string // Symbol
    c: string // Last Price
    p: string // Price Change
    P: string // Price Change Percent
    v: string // Volume
    q: string // Quote Volume
}

interface OrderBookData {
    b: [string, string][] // Bids [price, qty]
    a: [string, string][] // Asks [price, qty]
}

interface MarketStore {
    ticker: TickerData | null
    orderBook: OrderBookData | null
    /** WS connection status the UI can render (drives <ConnectionStatus>). */
    status: ConnState
    /** Back-compat boolean derived from status === 'open'. */
    isConnected: boolean
    /** Number of reconnect attempts since last clean open (for backoff/UI). */
    reconnectAttempts: number
    /** epoch ms of the last ticker update (WS or REST fallback) — used to decide
     *  whether the polling fallback should fill in for a silent WS. */
    lastTickerAt: number
    setTicker: (data: TickerData) => void
    setOrderBook: (data: OrderBookData) => void
    setStatus: (status: ConnState) => void
    /** Back-compat setter used by older callers. */
    setConnected: (status: boolean) => void
    setReconnectAttempts: (n: number) => void
}

export const useMarketStore = create<MarketStore>((set) => ({
    ticker: null,
    orderBook: null,
    status: 'closed',
    isConnected: false,
    reconnectAttempts: 0,
    lastTickerAt: 0,
    setTicker: (data) => set({ ticker: data, lastTickerAt: Date.now() }),
    setOrderBook: (data) => set({ orderBook: data }),
    setStatus: (status) => set({ status, isConnected: status === 'open' }),
    setConnected: (isConnected) =>
        set({ isConnected, status: isConnected ? 'open' : 'closed' }),
    setReconnectAttempts: (reconnectAttempts) => set({ reconnectAttempts }),
}))

// Reconnect backoff: exponential with jitter, capped.
const BASE_DELAY = 1000
const MAX_DELAY = 30000
function backoffDelay(attempt: number): number {
    const exp = Math.min(MAX_DELAY, BASE_DELAY * 2 ** attempt)
    return exp / 2 + Math.random() * (exp / 2) // 50–100% of exp
}

export function useMarketData() {
    const wsRef = useRef<WebSocket | null>(null)

    useEffect(() => {
        let reconnectTimer: ReturnType<typeof setTimeout> | undefined
        let attempt = 0
        let isUnmounting = false

        const { setTicker, setOrderBook, setStatus, setReconnectAttempts } =
            useMarketStore.getState()
        const { addLog } = useStore.getState()

        const scheduleReconnect = () => {
            if (isUnmounting) return
            const delay = backoffDelay(attempt)
            attempt += 1
            setReconnectAttempts(attempt)
            setStatus('reconnecting')
            reconnectTimer = setTimeout(connect, delay)
        }

        const connect = async () => {
            if (isUnmounting) return
            if (
                wsRef.current?.readyState === WebSocket.OPEN ||
                wsRef.current?.readyState === WebSocket.CONNECTING
            ) {
                return
            }

            // Append ?token=<jwt> so the backend authenticates the handshake and scopes
            // the socket to this user (browsers can't send Authorization on a WS upgrade).
            const url = await buildWsUrl()
            if (isUnmounting) return
            setStatus(attempt === 0 ? 'connecting' : 'reconnecting')

            let ws: WebSocket
            try {
                ws = new WebSocket(url)
            } catch (e) {
                console.error('Failed to create WebSocket:', e)
                scheduleReconnect()
                return
            }
            wsRef.current = ws

            ws.onopen = () => {
                if (isUnmounting) {
                    ws.close()
                    return
                }
                attempt = 0
                setReconnectAttempts(0)
                setStatus('open')
            }

            ws.onclose = () => {
                if (isUnmounting) return
                wsRef.current = null
                scheduleReconnect()
            }

            ws.onerror = () => {
                if (isUnmounting) return
                setStatus('error')
                // onclose fires after onerror and drives the reconnect.
            }

            ws.onmessage = (event) => {
                if (isUnmounting) return
                try {
                    const payload = JSON.parse(event.data)
                    handleMessage(payload)
                } catch (e) {
                    console.error('Error parsing WebSocket message:', e)
                }
            }
        }

        // --- Message routing ------------------------------------------------
        const handleMessage = (payload: { type?: string; data?: unknown }) => {
            const { type, data } = payload

            switch (type) {
                case '24hrTicker':
                    setTicker(data as TickerData)
                    break

                case 'depthUpdate':
                    setOrderBook(data as OrderBookData)
                    break

                case 'balance_update':
                    applyBalance(data)
                    break

                case 'position_update':
                    applyPositions(data)
                    break

                case 'update_trade':
                    applyTradeUpdate(data)
                    break

                case 'panic_close':
                    // Emergency close acknowledged: clear active positions; the
                    // authoritative empty set arrives on the next position_update.
                    useStore.getState().setTrades([])
                    addLog(makeLog('EXECUTION', 'Panic close dispatched — closing all positions', 'warning'))
                    break

                case 'execution_status':
                    applyExecutionStatus(data)
                    break

                case 'agent_activity':
                case 'agent_update':
                    applyAgentActivity(type, data)
                    break

                case 'initial_state':
                    applyInitialState(data)
                    break

                default:
                    // Unknown message types are ignored (forward-compatible).
                    break
            }
        }

        // --- Handlers -------------------------------------------------------
        const applyBalance = (raw: unknown) => {
            const p = (raw ?? {}) as Record<string, unknown>
            const totalPnl = safeNum(p.realized_pnl) + safeNum(p.unrealized_pnl)
            useStore.getState().setPortfolio({
                totalValue: safeNum(p.total_equity),
                totalInvested: safeNum(p.total_equity) - safeNum(p.current_balance),
                totalPnl,
                totalPnlPercent: safeDiv(totalPnl, p.initial_balance) * 100,
                balance: safeNum(p.current_balance),
                unrealizedPnl: safeNum(p.unrealized_pnl),
                realizedPnl: safeNum(p.realized_pnl),
                winRate: safeNum(p.win_rate),
                totalTrades: safeNum(p.total_trades),
            })
        }

        const applyPositions = (raw: unknown) => {
            const list = Array.isArray(raw) ? raw : []
            const trades: Trade[] = list.map((pos: Record<string, unknown>) => ({
                id: String(pos.position_id ?? `${pos.symbol}-${Date.now()}`),
                symbol: String(pos.symbol ?? ''),
                side: (pos.positionSide as Trade['side']) ?? 'LONG',
                entry: safeNum(pos.entryPrice),
                current: safeNum(pos.markPrice),
                qty: Math.abs(safeNum(pos.positionAmt)),
                pnl: safeNum(pos.unRealizedProfit),
                pnlPercent:
                    safeDiv(
                        safeNum(pos.unRealizedProfit),
                        safeNum(pos.entryPrice) * safeNum(pos.positionAmt),
                    ) * 100,
                status: 'OPEN',
                stopLoss: pos.stopLoss != null ? safeNum(pos.stopLoss) : undefined,
                takeProfit: pos.takeProfit != null ? safeNum(pos.takeProfit) : undefined,
            }))
            useStore.getState().setTrades(trades)
        }

        const applyTradeUpdate = (raw: unknown) => {
            const t = (raw ?? {}) as Record<string, unknown>
            if (!t.symbol && !t.id) return
            const trade: Trade = {
                id: String(t.id ?? t.position_id ?? `${t.symbol}-${Date.now()}`),
                symbol: String(t.symbol ?? ''),
                side: (t.side as Trade['side']) ?? (t.positionSide as Trade['side']) ?? 'LONG',
                entry: safeNum(t.entry ?? t.entryPrice),
                current: safeNum(t.current ?? t.markPrice),
                qty: t.qty != null || t.positionAmt != null ? Math.abs(safeNum(t.qty ?? t.positionAmt)) : undefined,
                pnl: safeNum(t.pnl ?? t.unRealizedProfit),
                pnlPercent: safeNum(t.pnlPercent),
                status: (t.status as Trade['status']) ?? 'OPEN',
                entryTime: t.entryTime as string | undefined,
                exitTime: t.exitTime as string | undefined,
                exitReason: t.exitReason as string | undefined,
                strategy: t.strategy as string | undefined,
                leverage: t.leverage != null ? safeNum(t.leverage) : undefined,
                confidence: t.confidence != null ? safeNum(t.confidence) : undefined,
                isWinner: t.isWinner as boolean | undefined,
            }
            if (trade.status === 'CLOSED') {
                useStore.getState().closeTrade(trade.id, trade.current, trade.exitReason ?? 'closed')
            } else {
                useStore.getState().updateTrade(trade)
            }
        }

        // Legacy nested shape: { type: 'execution_status', data: { type, payload } }
        const applyExecutionStatus = (raw: unknown) => {
            const d = (raw ?? {}) as { type?: string; payload?: unknown }
            if (d.type === 'balance_update') applyBalance(d.payload)
            else if (d.type === 'position_update') applyPositions(d.payload)
            else if (d.type === 'update_trade') applyTradeUpdate(d.payload)
            else if (d.type === 'panic_close') {
                useStore.getState().setTrades([])
            }
        }

        const applyAgentActivity = (type: string, raw: unknown) => {
            const d = (raw ?? {}) as Record<string, unknown>
            const sender = String(d.sender ?? '').toLowerCase()
            let agent: 'DATA' | 'ANALYSIS' | 'STRATEGY' | 'RISK' | 'EXECUTION' = 'DATA'
            if (sender.includes('analysis')) agent = 'ANALYSIS'
            else if (sender.includes('strategy')) agent = 'STRATEGY'
            else if (sender.includes('risk')) agent = 'RISK'
            else if (sender.includes('execution')) agent = 'EXECUTION'

            let message = String(d.message ?? d.action ?? d.type ?? 'Activity update')
            const payload = d.payload as Record<string, unknown> | undefined
            if (type === 'agent_update' && payload) {
                if (payload.summary) message = String(payload.summary)
                else if (payload.signal) message = `Signal: ${payload.signal} ${payload.symbol ?? ''}`.trim()
                else if (payload.decision) message = `Decision: ${payload.decision}`
                else if (payload.status) message = `Status: ${payload.status}`
            }

            const sevMap: Record<string, 'info' | 'success' | 'warning' | 'error'> = {
                info: 'info', success: 'success', warning: 'warning', error: 'error',
            }
            addLog(makeLog(agent, message, sevMap[String(d.severity)] ?? 'info', d.id as string | undefined))
        }

        const applyInitialState = (raw: unknown) => {
            const d = (raw ?? {}) as Record<string, unknown>
            if (d.portfolio) {
                const current = useStore.getState().portfolio
                useStore.getState().setPortfolio({ ...current, ...(d.portfolio as object) } as never)
            }
            if (Array.isArray(d.positions)) applyPositions(d.positions)
            if (Array.isArray(d.recentLogs)) {
                for (const log of d.recentLogs) addLog(log as never)
            }
        }

        // Small startup delay tames React StrictMode double-invoke in dev.
        reconnectTimer = setTimeout(connect, 100)

        return () => {
            isUnmounting = true
            if (reconnectTimer) clearTimeout(reconnectTimer)
            useMarketStore.getState().setStatus('closed')
            if (wsRef.current) {
                wsRef.current.onclose = null
                wsRef.current.close()
                wsRef.current = null
            }
        }
    }, [])

    // Ticker fallback: the backend's live ticker comes from Binance's WebSocket, which
    // is region-blocked in some markets (e.g. India) and unreachable on restricted
    // networks — leaving the dashboard price/chart empty. Poll the same-origin
    // /api/ticker proxy (Binance -> CoinGecko fallback) and fill the store ONLY when the
    // WS ticker is absent or stale, so a healthy WS always wins.
    useEffect(() => {
        let stopped = false
        const STALE_MS = 15000

        const poll = async () => {
            if (stopped) return
            const s = useMarketStore.getState()
            if (s.ticker && Date.now() - s.lastTickerAt < STALE_MS) return // WS is fresh
            try {
                const res = await fetch('/api/ticker', { cache: 'no-store' })
                if (!res.ok) return
                const { ticks } = (await res.json()) as {
                    ticks?: { symbol: string; lastPrice: string; priceChangePercent: string }[]
                }
                const btc = ticks?.find((t) => t.symbol === 'BTCUSDT')
                if (!btc) return
                // Don't clobber a WS ticker that arrived while we were fetching.
                const cur = useMarketStore.getState()
                if (cur.ticker && Date.now() - cur.lastTickerAt < STALE_MS) return
                const c = Number(btc.lastPrice)
                const P = Number(btc.priceChangePercent)
                useMarketStore.getState().setTicker({
                    s: 'BTCUSDT',
                    c: String(c),
                    p: String((c * P) / 100),
                    P: String(P),
                    v: '',
                    q: '',
                })
            } catch {
                /* proxy unavailable — leave the honest offline state */
            }
        }

        poll()
        const id = setInterval(poll, STALE_MS)
        return () => {
            stopped = true
            clearInterval(id)
        }
    }, [])
}

function makeLog(
    agent: 'DATA' | 'ANALYSIS' | 'STRATEGY' | 'RISK' | 'EXECUTION',
    message: string,
    severity: 'info' | 'success' | 'warning' | 'error',
    id?: string,
) {
    return {
        id: id ?? (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : String(Math.random())),
        timestamp: new Date().toLocaleTimeString(),
        agent,
        message,
        severity,
    }
}
