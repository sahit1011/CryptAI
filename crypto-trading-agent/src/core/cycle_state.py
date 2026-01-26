"""
Cycle State Tracking for Event-Driven Architecture
Tracks the state and progress of trading cycles in the event-driven system
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum


class CycleStatus(Enum):
    """Cycle status enumeration"""
    STARTED = "started"
    DATA_READY = "data_ready"
    REGIME_DETECTED = "regime_detected"
    ANALYSIS_COMPLETE = "analysis_complete"
    SETUP_GENERATED = "setup_generated"
    TRADE_APPROVED = "trade_approved"
    TRADE_REJECTED = "trade_rejected"
    TRADE_EXECUTED = "trade_executed"
    CYCLE_COMPLETE = "cycle_complete"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class CycleState:
    """
    Represents the state of a single trading cycle in the event-driven system
    
    Tracks:
    - Cycle identification (cycle_id, symbol)
    - Timing (start, completion, timeout)
    - Progress (status, events received)
    - Results (trade outcome, errors)
    """
    cycle_id: str
    symbol: str
    start_time: datetime
    status: CycleStatus = CycleStatus.STARTED
    
    # Event tracking
    events_received: List[str] = field(default_factory=list)
    event_timestamps: Dict[str, datetime] = field(default_factory=dict)
    
    # Timing
    timeout_at: datetime = field(default=None)
    completed_at: Optional[datetime] = None
    
    # Results
    trade_decision: Optional[str] = None  # 'approved', 'rejected', 'no_opportunity'
    trade_id: Optional[str] = None
    error: Optional[str] = None
    
    # Performance metrics
    data_fetch_duration: Optional[float] = None
    regime_detection_duration: Optional[float] = None
    analysis_duration: Optional[float] = None
    strategy_duration: Optional[float] = None
    risk_duration: Optional[float] = None
    execution_duration: Optional[float] = None
    total_duration: Optional[float] = None
    
    def __post_init__(self):
        """Set timeout if not provided"""
        if self.timeout_at is None:
            self.timeout_at = self.start_time + timedelta(seconds=300)  # 5 min timeout
    
    def add_event(self, event_name: str):
        """Record that an event was received"""
        if event_name not in self.events_received:
            self.events_received.append(event_name)
            self.event_timestamps[event_name] = datetime.now()
    
    def update_status(self, new_status: CycleStatus):
        """Update cycle status"""
        self.status = new_status
        
        # Auto-complete if terminal status
        if new_status in [CycleStatus.CYCLE_COMPLETE, CycleStatus.TIMEOUT, CycleStatus.ERROR]:
            if self.completed_at is None:
                self.completed_at = datetime.now()
                self.total_duration = (self.completed_at - self.start_time).total_seconds()
    
    def is_complete(self) -> bool:
        """Check if cycle is complete"""
        return self.status in [
            CycleStatus.CYCLE_COMPLETE,
            CycleStatus.TIMEOUT,
            CycleStatus.ERROR
        ]
    
    def is_timed_out(self) -> bool:
        """Check if cycle has timed out"""
        return datetime.now() > self.timeout_at and not self.is_complete()
    
    def get_elapsed_time(self) -> float:
        """Get elapsed time in seconds"""
        if self.completed_at:
            return (self.completed_at - self.start_time).total_seconds()
        return (datetime.now() - self.start_time).total_seconds()
    
    def get_remaining_time(self) -> float:
        """Get remaining time before timeout in seconds"""
        if self.is_complete():
            return 0.0
        remaining = (self.timeout_at - datetime.now()).total_seconds()
        return max(0.0, remaining)
    
    def has_event(self, event_name: str) -> bool:
        """Check if specific event was received"""
        return event_name in self.events_received
    
    def get_event_duration(self, event_name: str) -> Optional[float]:
        """Get time taken for a specific event"""
        if event_name not in self.event_timestamps:
            return None
        
        event_time = self.event_timestamps[event_name]
        
        # Find previous event
        event_index = self.events_received.index(event_name)
        if event_index == 0:
            # First event - measure from start
            return (event_time - self.start_time).total_seconds()
        
        # Measure from previous event
        prev_event = self.events_received[event_index - 1]
        prev_time = self.event_timestamps[prev_event]
        return (event_time - prev_time).total_seconds()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'cycle_id': self.cycle_id,
            'symbol': self.symbol,
            'status': self.status.value,
            'start_time': self.start_time.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'timeout_at': self.timeout_at.isoformat(),
            'elapsed_time': self.get_elapsed_time(),
            'remaining_time': self.get_remaining_time(),
            'events_received': self.events_received,
            'event_timestamps': {
                k: v.isoformat() for k, v in self.event_timestamps.items()
            },
            'trade_decision': self.trade_decision,
            'trade_id': self.trade_id,
            'error': self.error,
            'performance': {
                'data_fetch': self.data_fetch_duration,
                'regime_detection': self.regime_detection_duration,
                'analysis': self.analysis_duration,
                'strategy': self.strategy_duration,
                'risk': self.risk_duration,
                'execution': self.execution_duration,
                'total': self.total_duration
            }
        }
    
    def __repr__(self) -> str:
        """String representation"""
        return (
            f"CycleState(cycle_id={self.cycle_id}, symbol={self.symbol}, "
            f"status={self.status.value}, elapsed={self.get_elapsed_time():.1f}s)"
        )


@dataclass
class CycleStatistics:
    """
    Aggregated statistics across multiple cycles
    """
    total_cycles: int = 0
    completed_cycles: int = 0
    timed_out_cycles: int = 0
    error_cycles: int = 0
    
    # Trade outcomes
    trades_approved: int = 0
    trades_rejected: int = 0
    trades_executed: int = 0
    no_opportunities: int = 0
    
    # Performance metrics
    avg_cycle_time: float = 0.0
    min_cycle_time: float = float('inf')
    max_cycle_time: float = 0.0
    
    avg_data_fetch_time: float = 0.0
    avg_analysis_time: float = 0.0
    avg_strategy_time: float = 0.0
    
    # Parallel execution metrics
    avg_parallel_time: float = 0.0  # Data + Regime (should be ~30s)
    avg_sequential_time: float = 0.0  # Strategy → Risk → Execution
    
    def update(self, cycle: CycleState):
        """Update statistics with completed cycle"""
        self.total_cycles += 1
        
        if cycle.status == CycleStatus.CYCLE_COMPLETE:
            self.completed_cycles += 1
        elif cycle.status == CycleStatus.TIMEOUT:
            self.timed_out_cycles += 1
        elif cycle.status == CycleStatus.ERROR:
            self.error_cycles += 1
        
        # Trade outcomes
        if cycle.trade_decision == 'approved':
            self.trades_approved += 1
        elif cycle.trade_decision == 'rejected':
            self.trades_rejected += 1
        elif cycle.trade_decision == 'no_opportunity':
            self.no_opportunities += 1
        
        if cycle.trade_id:
            self.trades_executed += 1
        
        # Performance metrics
        if cycle.total_duration:
            self.avg_cycle_time = (
                (self.avg_cycle_time * (self.total_cycles - 1) + cycle.total_duration)
                / self.total_cycles
            )
            self.min_cycle_time = min(self.min_cycle_time, cycle.total_duration)
            self.max_cycle_time = max(self.max_cycle_time, cycle.total_duration)
        
        if cycle.data_fetch_duration:
            self.avg_data_fetch_time = (
                (self.avg_data_fetch_time * (self.total_cycles - 1) + cycle.data_fetch_duration)
                / self.total_cycles
            )
        
        if cycle.analysis_duration:
            self.avg_analysis_time = (
                (self.avg_analysis_time * (self.total_cycles - 1) + cycle.analysis_duration)
                / self.total_cycles
            )
        
        if cycle.strategy_duration:
            self.avg_strategy_time = (
                (self.avg_strategy_time * (self.total_cycles - 1) + cycle.strategy_duration)
                / self.total_cycles
            )
    
    def get_completion_rate(self) -> float:
        """Get cycle completion rate"""
        if self.total_cycles == 0:
            return 0.0
        return (self.completed_cycles / self.total_cycles) * 100
    
    def get_timeout_rate(self) -> float:
        """Get cycle timeout rate"""
        if self.total_cycles == 0:
            return 0.0
        return (self.timed_out_cycles / self.total_cycles) * 100
    
    def get_trade_approval_rate(self) -> float:
        """Get trade approval rate"""
        total_decisions = self.trades_approved + self.trades_rejected + self.no_opportunities
        if total_decisions == 0:
            return 0.0
        return (self.trades_approved / total_decisions) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'total_cycles': self.total_cycles,
            'completed_cycles': self.completed_cycles,
            'timed_out_cycles': self.timed_out_cycles,
            'error_cycles': self.error_cycles,
            'completion_rate': round(self.get_completion_rate(), 2),
            'timeout_rate': round(self.get_timeout_rate(), 2),
            'trades': {
                'approved': self.trades_approved,
                'rejected': self.trades_rejected,
                'executed': self.trades_executed,
                'no_opportunities': self.no_opportunities,
                'approval_rate': round(self.get_trade_approval_rate(), 2)
            },
            'performance': {
                'avg_cycle_time': round(self.avg_cycle_time, 2),
                'min_cycle_time': round(self.min_cycle_time, 2) if self.min_cycle_time != float('inf') else 0,
                'max_cycle_time': round(self.max_cycle_time, 2),
                'avg_data_fetch': round(self.avg_data_fetch_time, 2),
                'avg_analysis': round(self.avg_analysis_time, 2),
                'avg_strategy': round(self.avg_strategy_time, 2)
            }
        }
