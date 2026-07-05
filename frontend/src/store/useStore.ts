
import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export interface AgentLog {
    id: string
    timestamp: string
    agent: 'DATA' | 'ANALYSIS' | 'STRATEGY' | 'RISK' | 'EXECUTION'
    message: string
    severity: 'info' | 'success' | 'warning' | 'error'
}

export interface Trade {
    id: string
    symbol: string
    side: 'LONG' | 'SHORT'
    entry: number
    current: number
    pnl: number
    pnlPercent: number
    status: 'OPEN' | 'CLOSED'
    entryTime?: string
    exitTime?: string
    exitReason?: string
    // New fields for historical data
    strategy?: string
    leverage?: number
    confidence?: number
    isWinner?: boolean
    stopLoss?: number
    takeProfit?: number
}

export interface PortfolioMetrics {
    totalValue: number
    totalInvested: number
    totalPnl: number
    totalPnlPercent: number
    balance: number
    unrealizedPnl: number
    realizedPnl: number
    winRate: number
    totalTrades: number
}

interface AppState {
    agentLogs: AgentLog[]
    addLog: (log: AgentLog) => void
    clearLogs: () => void

    activeTrades: Trade[]
    tradeHistory: Trade[]
    setTrades: (trades: Trade[]) => void
    updateTrade: (trade: Trade) => void
    closeTrade: (tradeId: string, exitPrice: number, exitReason: string) => void
    addToHistory: (trade: Trade) => void
    setTradeHistory: (trades: Trade[]) => void

    portfolio: PortfolioMetrics
    setPortfolio: (metrics: PortfolioMetrics) => void

    isSidebarOpen: boolean
    toggleSidebar: () => void
}

export const useStore = create<AppState>()(
    persist(
        (set) => ({
            agentLogs: [],
            addLog: (log) => set((state) => ({
                agentLogs: [log, ...state.agentLogs].slice(0, 100)
            })),
            clearLogs: () => set({ agentLogs: [] }),

            activeTrades: [],
            tradeHistory: [],

            setTrades: (trades) => set({ activeTrades: trades }),

            updateTrade: (trade) => set((state) => {
                const exists = state.activeTrades.find(t => t.id === trade.id);
                if (exists) {
                    return {
                        activeTrades: state.activeTrades.map(t => t.id === trade.id ? trade : t)
                    };
                }
                return { activeTrades: [trade, ...state.activeTrades] };
            }),

            closeTrade: (tradeId, exitPrice, exitReason) => set((state) => {
                const trade = state.activeTrades.find(t => t.id === tradeId);
                if (trade) {
                    const closedTrade: Trade = {
                        ...trade,
                        status: 'CLOSED',
                        current: exitPrice,
                        exitTime: new Date().toISOString(),
                        exitReason: exitReason
                    };
                    return {
                        activeTrades: state.activeTrades.filter(t => t.id !== tradeId),
                        tradeHistory: [closedTrade, ...state.tradeHistory].slice(0, 50)
                    };
                }
                return state;
            }),

            addToHistory: (trade) => set((state) => ({
                tradeHistory: [trade, ...state.tradeHistory].slice(0, 50)
            })),

            setTradeHistory: (trades) => set({ tradeHistory: trades }),

            portfolio: {
                totalValue: 0,
                totalInvested: 0,
                totalPnl: 0,
                totalPnlPercent: 0,
                balance: 0,
                unrealizedPnl: 0,
                realizedPnl: 0,
                winRate: 0,
                totalTrades: 0
            },
            setPortfolio: (metrics) => set({ portfolio: metrics }),

            isSidebarOpen: true,
            toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
        }),
        {
            name: 'trading-dashboard-storage',
            storage: createJSONStorage(() => localStorage),
            partialize: (state) => ({
                portfolio: state.portfolio,
                tradeHistory: state.tradeHistory,
                // Don't persist activeTrades as they come from backend
                // Don't persist logs as they're real-time only
            })
        }
    )
)
