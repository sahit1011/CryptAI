"use client"

import { useEffect, useRef } from 'react'
import { create } from 'zustand'
import { useStore } from '@/store/useStore'

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
    isConnected: boolean
    setTicker: (data: TickerData) => void
    setOrderBook: (data: OrderBookData) => void
    setConnected: (status: boolean) => void
}

export const useMarketStore = create<MarketStore>((set) => ({
    ticker: null,
    orderBook: null,
    isConnected: false,
    setTicker: (data) => set({ ticker: data }),
    setOrderBook: (data) => set({ orderBook: data }),
    setConnected: (status) => set({ isConnected: status }),
}))

export function useMarketData() {
    const { setTicker, setOrderBook, setConnected } = useMarketStore()
    const { addLog } = useStore()
    const wsRef = useRef<WebSocket | null>(null)

    useEffect(() => {
        let connectTimeout: NodeJS.Timeout;
        let isUnmounting = false;

        const connect = () => {
            if (isUnmounting) return;

            // Prevent multiple connections
            if (wsRef.current?.readyState === WebSocket.OPEN || wsRef.current?.readyState === WebSocket.CONNECTING) {
                return
            }

            // Try localhost as it might resolve better in some environments
            const url = 'ws://localhost:8000/ws'
            console.log('Attempting to connect to WebSocket:', url)

            try {
                const ws = new WebSocket(url)
                wsRef.current = ws

                ws.onopen = () => {
                    if (isUnmounting) {
                        ws.close();
                        return;
                    }
                    console.log('✅ Connected to backend WebSocket')
                    setConnected(true)
                }

                ws.onclose = (event) => {
                    if (isUnmounting) return;

                    console.log('❌ Disconnected from backend WebSocket', {
                        code: event.code,
                        reason: event.reason,
                        wasClean: event.wasClean
                    })
                    setConnected(false)
                    // Reconnect after 3s
                    connectTimeout = setTimeout(connect, 3000)
                }

                ws.onerror = (error) => {
                    if (isUnmounting) return;

                    console.error('WebSocket error occurred:', {
                        readyState: ws.readyState,
                        url: ws.url,
                        error: error
                    })

                    // Check if backend is reachable
                    if (ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
                        console.error('❌ Cannot connect to backend. Please ensure:')
                        console.error('   1. Backend server is running on port 8000')
                        console.error('   2. Run: cd crypto-trading-agent && .\\start_system.ps1')
                        console.error('   3. Or manually: python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload')
                    }
                }

                ws.onmessage = (event) => {
                    if (isUnmounting) return;
                    try {
                        const payload = JSON.parse(event.data)
                        const { type, data } = payload

                        // ... rest of message handling ...
                        handleMessage(type, data);
                    } catch (e) {
                        console.error('❌ Error parsing WebSocket message:', e)
                    }
                }
            } catch (e) {
                console.error('Failed to create WebSocket:', e);
                // Retry
                connectTimeout = setTimeout(connect, 3000);
            }
        }

        // Initial connection delay to handle Strict Mode
        connectTimeout = setTimeout(connect, 100);

        return () => {
            isUnmounting = true;
            clearTimeout(connectTimeout);
            if (wsRef.current) {
                wsRef.current.close()
                wsRef.current = null;
            }
        }
    }, [setTicker, setOrderBook, setConnected, addLog])

    // Helper to handle messages (moved out of effect for clarity)
    const handleMessage = (type: string, data: any) => {
        if (type === '24hrTicker') {
            setTicker(data)
        } else if (type === 'depthUpdate') {
            setOrderBook(data)
        } else if (type === 'agent_activity') {
            // Handle agent_activity messages
            console.log('🤖 Agent activity received:', JSON.stringify(data, null, 2));

            let agentType: 'DATA' | 'ANALYSIS' | 'STRATEGY' | 'RISK' | 'EXECUTION' = 'DATA';
            const sender = data.sender?.toLowerCase() || '';

            if (sender.includes('analysis')) agentType = 'ANALYSIS';
            else if (sender.includes('strategy')) agentType = 'STRATEGY';
            else if (sender.includes('risk')) agentType = 'RISK';
            else if (sender.includes('execution')) agentType = 'EXECUTION';
            else if (sender.includes('memory')) agentType = 'DATA';

            // Use the message field directly from backend
            const message = data.message || data.action || 'Activity update';
            console.log('🤖 Extracted message:', message);

            // Map severity from backend to frontend format
            const severityMap: Record<string, 'info' | 'success' | 'warning' | 'error'> = {
                'info': 'info',
                'success': 'success',
                'warning': 'warning',
                'error': 'error'
            };
            const severity = severityMap[data.severity] || 'info';

            addLog({
                id: Math.random().toString(),
                timestamp: new Date().toLocaleTimeString(),
                agent: agentType,
                message: message,
                severity: severity
            });
        } else if (type === 'agent_update') {
            // Handle legacy agent messages
            let agentType: 'DATA' | 'ANALYSIS' | 'STRATEGY' | 'RISK' | 'EXECUTION' = 'DATA';
            const sender = data.sender?.toLowerCase() || '';

            if (sender.includes('analysis')) agentType = 'ANALYSIS';
            else if (sender.includes('strategy')) agentType = 'STRATEGY';
            else if (sender.includes('risk')) agentType = 'RISK';
            else if (sender.includes('execution')) agentType = 'EXECUTION';

            let message = data.type;
            if (data.payload) {
                if (data.payload.summary) message = data.payload.summary;
                else if (data.payload.signal) message = `Signal: ${data.payload.signal} ${data.payload.symbol}`;
                else if (data.payload.decision) message = `Decision: ${data.payload.decision}`;
                else if (data.payload.status) message = `Status: ${data.payload.status}`;
                else message = `${data.type} - ${JSON.stringify(data.payload).substring(0, 50)}...`;
            }

            addLog({
                id: data.id || Math.random().toString(),
                timestamp: new Date().toLocaleTimeString(),
                agent: agentType,
                message: message,
                severity: 'info'
            })
        } else if (type === 'execution_status') {
            // Handle execution updates
            const { type: updateType, payload: execPayload } = data;

            if (updateType === 'balance_update') {
                console.log('📊 Portfolio update received:', execPayload);
                useStore.getState().setPortfolio({
                    totalValue: execPayload.total_equity,
                    totalInvested: execPayload.total_equity - execPayload.current_balance,
                    totalPnl: execPayload.realized_pnl + execPayload.unrealized_pnl,
                    totalPnlPercent: ((execPayload.realized_pnl + execPayload.unrealized_pnl) / execPayload.initial_balance) * 100,
                    balance: execPayload.current_balance,
                    unrealizedPnl: execPayload.unrealized_pnl,
                    realizedPnl: execPayload.realized_pnl,
                    winRate: execPayload.win_rate,
                    totalTrades: execPayload.total_trades
                });
            } else if (updateType === 'position_update') {
                console.log('📈 Position update received:', execPayload);
                const trades = execPayload.map((pos: any) => ({
                    id: pos.position_id || `${pos.symbol}-${Date.now()}`,  // CRITICAL FIX: Use unique position_id
                    symbol: pos.symbol,
                    side: pos.positionSide,
                    entry: parseFloat(pos.entryPrice),
                    current: parseFloat(pos.markPrice),
                    pnl: parseFloat(pos.unRealizedProfit),
                    pnlPercent: (parseFloat(pos.unRealizedProfit) / (parseFloat(pos.entryPrice) * parseFloat(pos.positionAmt))) * 100,
                    status: 'OPEN',
                    stopLoss: pos.stopLoss ? parseFloat(pos.stopLoss) : undefined,
                    takeProfit: pos.takeProfit ? parseFloat(pos.takeProfit) : undefined
                }));
                useStore.getState().setTrades(trades);
            }
        } else if (type === 'initial_state') {
            // Handle initial state when connecting
            console.log('🔄 Initial state received from backend');
            if (data.portfolio) {
                const currentPortfolio = useStore.getState().portfolio;
                useStore.getState().setPortfolio({
                    ...currentPortfolio,
                    ...data.portfolio
                });
            }
            if (data.positions) {
                useStore.getState().setTrades(data.positions);
            }
            if (data.recentLogs) {
                data.recentLogs.forEach((log: any) => addLog(log));
            }
        }
    }
}
