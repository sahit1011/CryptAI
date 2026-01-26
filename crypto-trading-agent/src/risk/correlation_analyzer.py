"""
Correlation Analyzer
Analyzes asset correlation to prevent over-exposure to correlated assets
"""
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from src.utils.pipeline_logger import PipelineLogger

plog = PipelineLogger()


@dataclass
class CorrelationResult:
    """Result of correlation analysis"""
    has_correlation: bool
    correlated_symbols: List[str] = field(default_factory=list)
    total_exposure: float = 0.0
    correlation_strength: float = 0.0  # 0-1
    recommended_size_multiplier: float = 1.0
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'has_correlation': self.has_correlation,
            'correlated_symbols': self.correlated_symbols,
            'total_exposure': round(self.total_exposure, 2),
            'correlation_strength': round(self.correlation_strength, 2),
            'recommended_size_multiplier': round(self.recommended_size_multiplier, 2),
            'warnings': self.warnings
        }


class CorrelationAnalyzer:
    """
    Analyzes correlation between assets to prevent over-exposure
    
    Responsibilities:
    - Define correlated asset pairs
    - Calculate total correlated exposure
    - Suggest position size adjustments
    - Track correlation strength dynamically
    - Provide correlation risk warnings
    """
    
    def __init__(
        self,
        correlation_pairs: Optional[List[List[str]]] = None,
        max_correlated_exposure: float = 0.04  # 4% max
    ):
        self.max_correlated_exposure = max_correlated_exposure
        
        # Default correlation pairs
        self.correlation_pairs = correlation_pairs or [
            ['BTCUSDT', 'ETHUSDT'],
            ['BTCUSDT', 'BNBUSDT'],
            ['ETHUSDT', 'BNBUSDT'],
            ['BTCUSDT', 'SOLUSDT'],
            ['ETHUSDT', 'AVAXUSDT'],
        ]
        
        # Build correlation matrix
        self.correlation_matrix = self._build_correlation_matrix()
        
        plog.info(
            f"Correlation analyzer initialized with {len(self.correlation_pairs)} pairs",
            agent="risk_agent",
            phase="initialization"
        )
    
    def _build_correlation_matrix(self) -> Dict[str, List[str]]:
        """Build correlation matrix from pairs"""
        matrix = {}
        
        for pair in self.correlation_pairs:
            for symbol in pair:
                if symbol not in matrix:
                    matrix[symbol] = []
                
                # Add all other symbols in the pair
                for other in pair:
                    if other != symbol and other not in matrix[symbol]:
                        matrix[symbol].append(other)
        
        return matrix
    
    def get_correlated_symbols(self, symbol: str) -> List[str]:
        """Get all symbols correlated with the given symbol"""
        return self.correlation_matrix.get(symbol, [])
    
    def are_correlated(self, symbol1: str, symbol2: str) -> bool:
        """Check if two symbols are correlated"""
        correlated = symbol2 in self.correlation_matrix.get(symbol1, [])
        return correlated
    
    def analyze_correlation(
        self,
        new_symbol: str,
        new_direction: str,
        existing_positions: List[Dict[str, Any]],
        total_equity: float
    ) -> CorrelationResult:
        """
        Analyze correlation risk for a new position
        
        Args:
            new_symbol: Symbol to trade
            new_direction: 'LONG' or 'SHORT'
            existing_positions: List of current positions
            total_equity: Total account equity
            
        Returns:
            CorrelationResult with analysis
        """
        correlated_symbols = []
        total_exposure = 0.0
        warnings = []
        
        # Get correlated symbols
        potential_correlations = self.get_correlated_symbols(new_symbol)
        
        if not potential_correlations:
            # No correlation
            return CorrelationResult(
                has_correlation=False,
                recommended_size_multiplier=1.0
            )
        
        # Check existing positions for correlations
        for position in existing_positions:
            pos_symbol = position.get('symbol')
            pos_direction = position.get('direction')
            pos_risk = position.get('risk_amount', 0)
            
            if self.are_correlated(new_symbol, pos_symbol):
                correlated_symbols.append(pos_symbol)
                
                # Weight same direction higher (stronger correlation risk)
                same_direction = pos_direction == new_direction
                weight = 1.0 if same_direction else 0.5
                
                total_exposure += pos_risk * weight
                
                if same_direction:
                    warnings.append(
                        f"Same direction as {pos_symbol} ({pos_direction}) - higher correlation risk"
                    )
        
        if not correlated_symbols:
            # No correlated positions found
            return CorrelationResult(
                has_correlation=False,
                recommended_size_multiplier=1.0
            )
        
        # Calculate correlation strength (0-1)
        exposure_pct = total_exposure / total_equity if total_equity > 0 else 0
        correlation_strength = min(exposure_pct / self.max_correlated_exposure, 1.0)
        
        # Calculate recommended size multiplier
        # 0% correlation = 1.0x, 4%+ correlation = 0.5x
        size_multiplier = max(1.0 - (correlation_strength * 0.5), 0.5)
        
        # Add warnings
        if exposure_pct > self.max_correlated_exposure * 0.75:
            warnings.append(
                f"High correlated exposure: ${total_exposure:.2f} ({exposure_pct*100:.1f}%)"
            )
        
        if len(correlated_symbols) > 2:
            warnings.append(
                f"Multiple correlated positions: {', '.join(correlated_symbols)}"
            )
        
        plog.debug(
            f"Correlation analysis for {new_symbol}: "
            f"{len(correlated_symbols)} correlated positions, "
            f"exposure=${total_exposure:.2f} ({exposure_pct*100:.1f}%), "
            f"strength={correlation_strength:.2f}, "
            f"multiplier={size_multiplier:.2f}",
            agent="risk_agent",
            phase="correlation_analysis"
        )
        
        return CorrelationResult(
            has_correlation=True,
            correlated_symbols=correlated_symbols,
            total_exposure=total_exposure,
            correlation_strength=correlation_strength,
            recommended_size_multiplier=size_multiplier,
            warnings=warnings
        )
    
    def calculate_correlated_exposure(
        self,
        positions: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """
        Calculate total correlated exposure for each symbol group
        
        Returns:
            Dict mapping symbol to total correlated exposure
        """
        exposure_by_symbol = {}
        
        for position in positions:
            symbol = position.get('symbol')
            risk = position.get('risk_amount', 0)
            
            if symbol not in exposure_by_symbol:
                exposure_by_symbol[symbol] = 0.0
            
            exposure_by_symbol[symbol] += risk
            
            # Add to correlated symbols
            correlated = self.get_correlated_symbols(symbol)
            for corr_symbol in correlated:
                if corr_symbol not in exposure_by_symbol:
                    exposure_by_symbol[corr_symbol] = 0.0
                exposure_by_symbol[corr_symbol] += risk * 0.5  # Partial weight
        
        return exposure_by_symbol
    
    def suggest_size_adjustment(
        self,
        base_size: float,
        correlation_risk: float
    ) -> float:
        """
        Suggest adjusted position size based on correlation risk
        
        Args:
            base_size: Original position size
            correlation_risk: Correlation risk score (0-1)
            
        Returns:
            Adjusted position size
        """
        # Reduce size linearly with correlation risk
        # 0 risk = 100%, 1.0 risk = 50%
        multiplier = max(1.0 - (correlation_risk * 0.5), 0.5)
        adjusted_size = base_size * multiplier
        
        plog.debug(
            f"Size adjustment: {base_size:.6f} -> {adjusted_size:.6f} "
            f"(multiplier={multiplier:.2f}, risk={correlation_risk:.2f})",
            agent="risk_agent",
            phase="correlation_analysis"
        )
        
        return adjusted_size
    
    def get_correlation_matrix(self) -> Dict[str, List[str]]:
        """Get the full correlation matrix"""
        return self.correlation_matrix.copy()
    
    def add_correlation_pair(self, symbol1: str, symbol2: str):
        """Add a new correlation pair"""
        # Add to pairs
        pair = [symbol1, symbol2]
        if pair not in self.correlation_pairs and [symbol2, symbol1] not in self.correlation_pairs:
            self.correlation_pairs.append(pair)
            
            # Update matrix
            if symbol1 not in self.correlation_matrix:
                self.correlation_matrix[symbol1] = []
            if symbol2 not in self.correlation_matrix[symbol1]:
                self.correlation_matrix[symbol1].append(symbol2)
            
            if symbol2 not in self.correlation_matrix:
                self.correlation_matrix[symbol2] = []
            if symbol1 not in self.correlation_matrix[symbol2]:
                self.correlation_matrix[symbol2].append(symbol1)
            
            plog.info(
                f"Added correlation pair: {symbol1} <-> {symbol2}",
                agent="risk_agent",
                phase="correlation_analysis"
            )
    
    def remove_correlation_pair(self, symbol1: str, symbol2: str):
        """Remove a correlation pair"""
        # Remove from pairs
        pair1 = [symbol1, symbol2]
        pair2 = [symbol2, symbol1]
        
        if pair1 in self.correlation_pairs:
            self.correlation_pairs.remove(pair1)
        if pair2 in self.correlation_pairs:
            self.correlation_pairs.remove(pair2)
        
        # Rebuild matrix
        self.correlation_matrix = self._build_correlation_matrix()
        
        plog.info(
            f"Removed correlation pair: {symbol1} <-> {symbol2}",
            agent="risk_agent",
            phase="correlation_analysis"
        )
    
    def get_summary(self) -> Dict[str, Any]:
        """Get correlation analyzer summary"""
        return {
            'total_pairs': len(self.correlation_pairs),
            'total_symbols': len(self.correlation_matrix),
            'max_correlated_exposure': f"{self.max_correlated_exposure*100}%",
            'correlation_pairs': self.correlation_pairs,
            'correlation_matrix': self.correlation_matrix
        }
