"""
Memory & Analytics Module
"""
from src.memory.trade_history_manager import TradeHistoryManager, TradeRecord, TradeStats
from src.memory.vector_memory import VectorMemoryStore, SimilarTrade
from src.memory.performance_analytics import PerformanceAnalyticsEngine, PerformanceMetrics
from src.memory.market_regime_detector import MarketRegimeDetector, MarketRegime, RegimeDetection

__all__ = [
    'TradeHistoryManager',
    'TradeRecord',
    'TradeStats',
    'VectorMemoryStore',
    'SimilarTrade',
    'PerformanceAnalyticsEngine',
    'PerformanceMetrics',
    'MarketRegimeDetector',
    'MarketRegime',
    'RegimeDetection'
]
