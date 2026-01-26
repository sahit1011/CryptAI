
"""
Enhanced Trade Setup Builder
Professional entry logic with lower timeframe confirmation
"""
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from src.utils.pipeline_logger import PipelineLogger

plog = PipelineLogger()

@dataclass
class TradeSetup:
    """Enhanced trade setup with entry confirmation"""
    # Existing fields...
    setup_id: str
    symbol: str
    timestamp: str
    direction: str
    strategy_type: str
    entry_type: str
    entry_price: float
    entry_zone_low: float
    entry_zone_high: float
    stop_loss: float
    stop_loss_type: str
    risk_amount: float
    risk_percentage: float
    take_profit_levels: List[Dict[str, float]]
    final_target: float
    risk_reward_ratio: float
    expected_duration_hours: float
    confidence_score: float
    confluences: List[str]
    key_levels: Dict[str, List[float]]
    invalidation_conditions: List[str]
    setup_reasoning: str

    # NEW FIELDS for professional entry
    entry_trigger: str  # Description of entry trigger
    entry_confirmation: 'EntryConfirmation'  # Full confirmation analysis
    recommended_position_size: Optional[float] = None
    max_position_size: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with flat keys for display and nested for analysis"""
        return {
            # Flat keys for easy access/display
            'setup_id': self.setup_id,
            'symbol': self.symbol,
            'timestamp': self.timestamp,
            'direction': self.direction,
            'strategy_type': self.strategy_type,
            'entry_type': self.entry_type,
            'entry_price': self.entry_price,
            'entry_zone_low': self.entry_zone_low,
            'entry_zone_high': self.entry_zone_high,
            'entry_trigger': self.entry_trigger,
            'stop_loss': self.stop_loss,
            'stop_loss_type': self.stop_loss_type,
            'risk_amount': self.risk_amount,
            'risk_percentage': self.risk_percentage,
            'final_target': self.final_target,
            'risk_reward_ratio': self.risk_reward_ratio,
            'confidence_score': self.confidence_score,
            'expected_duration_hours': self.expected_duration_hours,
            'take_profit_levels': self.take_profit_levels,
            'confluences': self.confluences,
            'key_levels': self.key_levels,
            'invalidation_conditions': self.invalidation_conditions,
            'setup_reasoning': self.setup_reasoning,
            'recommended_position_size': self.recommended_position_size,
            'max_position_size': self.max_position_size,
            
            # Nested structure for detailed analysis
            'entry': {
                'type': self.entry_type,
                'price': self.entry_price,
                'zone': [self.entry_zone_low, self.entry_zone_high],
                'trigger': self.entry_trigger,
                'confirmation': {
                    'confirmed': self.entry_confirmation.confirmed,
                    'pattern': self.entry_confirmation.candle_pattern.pattern_type
                              if self.entry_confirmation.candle_pattern else None,
                    'signal': self.entry_confirmation.price_action_signal,
                    'confidence': self.entry_confirmation.confidence,
                    'reasoning': self.entry_confirmation.reasoning
                }
            },
            'risk_management': {
                'stop_loss': self.stop_loss,
                'stop_loss_type': self.stop_loss_type,
                'risk_amount': self.risk_amount,
                'risk_percentage': self.risk_percentage
            },
            'targets': {
                'take_profit_levels': self.take_profit_levels,
                'final_target': self.final_target
            },
            'metrics': {
                'risk_reward_ratio': self.risk_reward_ratio,
                'confidence_score': self.confidence_score,
                'expected_duration_hours': self.expected_duration_hours
            },
            'context': {
                'confluences': self.confluences,
                'key_levels': self.key_levels,
                'invalidation_conditions': self.invalidation_conditions,
                'reasoning': self.setup_reasoning
            },
            'position_sizing': {
                'recommended_size': self.recommended_position_size,
                'max_size': self.max_position_size
            }
        }

    def is_valid(self) -> bool:
        """Validate setup"""
        if self.risk_reward_ratio < 1.5:
            return False

        if self.direction == 'LONG':
            if self.entry_price <= self.stop_loss:
                return False
        else:
            if self.entry_price >= self.stop_loss:
                return False

        for tp in self.take_profit_levels:
            if self.direction == 'LONG':
                if tp['price'] <= self.entry_price:
                    return False
            else:
                if tp['price'] >= self.entry_price:
                    return False

        if self.confidence_score < 0.5:
            return False

        return True

@dataclass
class CandlePattern:
    """Candlestick pattern detection result"""
    pattern_type: str
    strength: float
    direction: str
    candles_involved: int
    description: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'pattern_type': self.pattern_type,
            'strength': self.strength,
            'direction': self.direction,
            'candles_involved': self.candles_involved,
            'description': self.description
        }

@dataclass
class EntryConfirmation:
    """Entry confirmation analysis"""
    confirmed: bool
    candle_pattern: Optional[CandlePattern]
    price_action_signal: str
    entry_trigger_met: bool
    confidence: float
    reasoning: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'confirmed': self.confirmed,
            'candle_pattern': self.candle_pattern.to_dict() if self.candle_pattern else None,
            'price_action_signal': self.price_action_signal,
            'entry_trigger_met': self.entry_trigger_met,
            'confidence': self.confidence,
            'reasoning': self.reasoning
        }

class EnhancedTradeSetupBuilder:
    """
    Professional trade setup builder with lower timeframe entry confirmation
    
    New Features:
    1. Lower timeframe (5M) candle analysis
    2. Price action pattern recognition
    3. Entry trigger validation
    4. Volume confirmation
    5. Multi-candle structure analysis
    """
    
    def __init__(self):
        self.setup_counter = 0
        
    def build_setup_with_confirmation(
        self,
        symbol: str,
        analysis: Dict[str, Any],
        current_price: float,
        atr: float,
        candles_5m: List[Dict[str, Any]],  # NEW: 5M candles
        candles_15m: List[Dict[str, Any]],  # For context
        candles_1h: List[Dict[str, Any]]   # For trend
    ) -> Optional[TradeSetup]:
        """
        Build trade setup WITH lower timeframe entry confirmation
        
        Professional Flow:
        1. Identify higher timeframe setup (1H/4H - OB, FVG, structure)
        2. Wait for price to reach entry zone
        3. Analyze 5M candles for entry trigger
        4. Confirm with price action patterns
        5. Enter on confirmation candle close
        """
        try:
            # Sanitize inputs immediately
            candles_5m = self._sanitize_candles(candles_5m)
            candles_15m = self._sanitize_candles(candles_15m)
            candles_1h = self._sanitize_candles(candles_1h)
            
            plog.info(f"Building professional trade setup for {symbol}...", agent="strategy", phase="strategy_generation")
            
            # Ensure current_price is a float
            try:
                current_price = float(current_price)
            except (ValueError, TypeError):
                plog.error(f"Invalid current_price: {current_price}", agent="strategy", phase="strategy_generation")
                return None
            
            # Ensure atr is a float
            try:
                atr = float(atr)
            except (ValueError, TypeError):
                plog.warning(f"Invalid ATR: {atr}, using default", agent="strategy", phase="strategy_generation")
                atr = current_price * 0.01

            # Extract opportunities
            opportunities = analysis.get('trade_opportunities', [])
            plog.info(f"Setup Builder: Found {len(opportunities)} trade opportunities", agent="strategy", phase="strategy_generation")
            if not opportunities:
                plog.warning("Setup Builder: No trade opportunities found", agent="strategy", phase="strategy_generation")
                return None

            plog.info("Setup Builder: Selecting best opportunity...", agent="strategy", phase="strategy_generation")
            best_opportunity = self._select_best_opportunity(opportunities)
            if not best_opportunity:
                plog.warning("Setup Builder: No valid opportunity selected (failed confluence/confidence check)", agent="strategy", phase="strategy_generation")
                return None
            # Safely extract values for logging
            try:
                log_confluence = int(best_opportunity.get('confluence_count', 0))
            except (ValueError, TypeError):
                log_confluence = 0
            try:
                log_confidence = float(best_opportunity.get('confidence', 0))
            except (ValueError, TypeError):
                log_confidence = 0.0
            plog.info(f"Setup Builder: Selected {best_opportunity.get('direction')} opportunity with {log_confluence} confluences, {log_confidence:.1%} confidence", agent="strategy", phase="strategy_generation")
            
            direction = best_opportunity['direction']
            
            # Step 1: Calculate Entry Zone (Higher Timeframe)
            entry_zone = self._calculate_htf_entry_zone(
                direction=direction,
                opportunity=best_opportunity,
                smc_data=analysis.get('smc_analysis', {}),
                ict_data=analysis.get('ict_analysis', {}),
                current_price=current_price
            )
            
            # Step 2: Analyze Lower Timeframe for Entry Confirmation
            entry_confirmation = self._analyze_ltf_entry_confirmation(
                direction=direction,
                entry_zone=entry_zone,
                candles_5m=candles_5m,
                candles_15m=candles_15m,
                current_price=current_price,
                volume_threshold=self._calculate_volume_threshold(candles_5m)
            )
            
            # Step 3: Determine Precise Entry Price
            if entry_confirmation.confirmed:
                # Entry is confirmed - use precise entry calculation
                precise_entry = self._calculate_precise_entry(
                    direction=direction,
                    entry_zone=entry_zone,
                    candles_5m=candles_5m,
                    confirmation=entry_confirmation
                )
            else:
                # Entry not yet confirmed - use pending entry
                precise_entry = self._calculate_pending_entry(
                    direction=direction,
                    entry_zone=entry_zone,
                    candles_5m=candles_5m
                )
            
            # Force price to be float
            try:
                precise_entry['price'] = float(precise_entry['price'])
            except (ValueError, TypeError) as e:
                plog.error(f"Failed to cast entry price to float: {precise_entry.get('price')} - {e}", agent="strategy", phase="strategy_generation")
                return None
            
            # Step 4: Calculate Stop Loss (based on structure, not arbitrary)
            stop_loss = self._calculate_professional_sl(
                direction=direction,
                entry_price=precise_entry['price'],
                entry_zone=entry_zone,
                candles_5m=candles_5m,
                candles_15m=candles_15m,
                atr=atr,
                smc_data=analysis.get('smc_analysis', {})
            )
            
            # Step 5: Generate Take Profits
            tp_levels = self._generate_professional_tps(
                direction=direction,
                entry_price=precise_entry['price'],
                stop_loss=stop_loss,
                analysis=analysis,
                candles_1h=candles_1h
            )
            
            # Validate and convert all numeric values before building setup
            plog.debug(f"Validating setup values before TradeSetup construction", agent="strategy", phase="strategy_generation")
            
            # Ensure precise_entry['price'] is float
            try:
                entry_price_value = float(precise_entry['price'])
                plog.debug(f"Entry price validated: {entry_price_value}", agent="strategy")
            except (ValueError, TypeError) as e:
                plog.error(f"Failed to convert entry price to float: {precise_entry.get('price')} (type: {type(precise_entry.get('price'))})", agent="strategy")
                raise
            
            # Ensure stop_loss is float
            try:
                stop_loss_value = float(stop_loss)
                plog.debug(f"Stop loss validated: {stop_loss_value}", agent="strategy")
            except (ValueError, TypeError) as e:
                plog.error(f"Failed to convert stop_loss to float: {stop_loss} (type: {type(stop_loss)})", agent="strategy")
                raise
            
            # Ensure all TP prices are floats
            try:
                for i, tp in enumerate(tp_levels):
                    tp['price'] = float(tp['price'])
                    plog.debug(f"TP{i+1} price validated: {tp['price']}", agent="strategy")
            except (ValueError, TypeError) as e:
                plog.error(f"Failed to convert TP price to float: {tp.get('price')} (type: {type(tp.get('price'))})", agent="strategy")
                raise
            
            # Calculate tp_distance for strategy classification
            try:
                # Debug: Check types before calculation
                plog.debug(f"Type check - entry_price_value: {type(entry_price_value)} = {entry_price_value}", agent="strategy")
                plog.debug(f"Type check - tp_levels[-1]['price']: {type(tp_levels[-1]['price'])} = {tp_levels[-1]['price']}", agent="strategy")
                plog.debug(f"Type check - direction: {direction}", agent="strategy")
                
                tp_final_price = float(tp_levels[-1]['price'])
                plog.debug(f"TP final price converted to float: {tp_final_price}", agent="strategy")
                
                if direction == 'LONG':
                    tp_distance = tp_final_price - entry_price_value
                    plog.debug(f"LONG: tp_distance = {tp_final_price} - {entry_price_value} = {tp_distance}", agent="strategy")
                else:
                    tp_distance = entry_price_value - tp_final_price
                    plog.debug(f"SHORT: tp_distance = {entry_price_value} - {tp_final_price} = {tp_distance}", agent="strategy")
                    
                plog.debug(f"TP distance calculated successfully: {tp_distance}", agent="strategy")
            except (ValueError, TypeError) as e:
                plog.error(f"Failed to calculate TP distance - Entry: {entry_price_value} (type: {type(entry_price_value)}), TP: {tp_levels[-1]['price']} (type: {type(tp_levels[-1]['price'])})", agent="strategy")
                plog.error(f"Exception: {e}", agent="strategy")
                raise
            
            # Build final setup
            setup = TradeSetup(
                setup_id=self._generate_setup_id(symbol),
                symbol=symbol,
                timestamp=datetime.utcnow().isoformat(),
                direction=direction,
                strategy_type=self._classify_strategy_type(
                    analysis.get('ict_analysis', {}),
                    tp_distance
                ),
                
                # Entry details
                entry_type=precise_entry['type'],
                entry_price=entry_price_value,
                entry_zone_low=entry_zone['zone_low'],
                entry_zone_high=entry_zone['zone_high'],
                entry_trigger=precise_entry['trigger'],
                entry_confirmation=entry_confirmation,
                
                # Risk management
                stop_loss=stop_loss_value,
                stop_loss_type='HARD',
                take_profit_levels=tp_levels,
                final_target=tp_levels[-1]['price'],
                
                # Metrics
                risk_reward_ratio=self._calculate_rr(
                    entry_price_value, stop_loss_value, tp_levels
                ),
                confidence_score=self._calculate_confidence(
                    best_opportunity, entry_confirmation
                ),
                
                # Context
                confluences=best_opportunity.get('key_factors', []),
                setup_reasoning=self._build_professional_reasoning(
                    best_opportunity, entry_confirmation, precise_entry
                ),
                
                # Metadata
                risk_amount=0.0,
                risk_percentage=2.0,
                expected_duration_hours=self._estimate_duration(
                    self._classify_strategy_type(
                        analysis.get('ict_analysis', {}),
                        tp_distance
                    )
                ),
                key_levels=analysis.get('key_levels', {}),
                invalidation_conditions=self._build_invalidation_conditions(
                    direction, stop_loss, candles_5m
                )
            )

            # Log setup details before validation
            plog.info(f"Built setup details:", agent="strategy", phase="strategy_generation")
            plog.info(f"Direction: {setup.direction}", agent="strategy", phase="strategy_generation")
            plog.info(f"Entry: ${setup.entry_price:.2f} (zone: ${setup.entry_zone_low:.2f} - ${setup.entry_zone_high:.2f})", agent="strategy", phase="strategy_generation")
            plog.info(f"Stop Loss: ${setup.stop_loss:.2f}", agent="strategy", phase="strategy_generation")
            plog.info(f"Risk-Reward: {setup.risk_reward_ratio:.2f}", agent="strategy", phase="strategy_generation")
            plog.info(f"Confidence: {setup.confidence_score:.2f}", agent="strategy", phase="strategy_generation")
            tp_prices = [f"${tp['price']:.2f}" for tp in setup.take_profit_levels]
            plog.info(f"Take Profits: {tp_prices}", agent="strategy", phase="strategy_generation")
            plog.info(f"Confluences: {len(setup.confluences)}", agent="strategy", phase="strategy_generation")

            if not setup.is_valid():
                plog.warning("Setup failed validation - checking criteria:", agent="strategy", phase="strategy_generation")
                plog.warning(f"RR >= 2.0: {setup.risk_reward_ratio:.2f} >= 2.0 = {setup.risk_reward_ratio >= 2.0}", agent="strategy", phase="strategy_generation")
                plog.warning(f"Confidence >= 0.5: {setup.confidence_score:.2f} >= 0.5 = {setup.confidence_score >= 0.5}", agent="strategy", phase="strategy_generation")
                entry_in_zone = setup.entry_zone_low <= setup.entry_price <= setup.entry_zone_high
                plog.warning(f"Entry in zone: {entry_in_zone} ({setup.entry_zone_low:.2f} <= {setup.entry_price:.2f} <= {setup.entry_zone_high:.2f})", agent="strategy", phase="strategy_generation")

                # Check entry vs SL direction
                if setup.direction == 'LONG':
                    entry_above_sl = setup.entry_price > setup.stop_loss
                    plog.warning(f"LONG entry > SL: {setup.entry_price:.2f} > {setup.stop_loss:.2f} = {entry_above_sl}", agent="strategy", phase="strategy_generation")
                else:
                    entry_below_sl = setup.entry_price < setup.stop_loss
                    plog.warning(f"SHORT entry < SL: {setup.entry_price:.2f} < {setup.stop_loss:.2f} = {entry_below_sl}", agent="strategy", phase="strategy_generation")

                # Check TPs
                tp_valid = True
                for i, tp in enumerate(setup.take_profit_levels):
                    if setup.direction == 'LONG' and tp['price'] <= setup.entry_price:
                        plog.warning(f"TP{i+1} > entry for LONG: {tp['price']:.2f} > {setup.entry_price:.2f} = {tp['price'] > setup.entry_price}", agent="strategy", phase="strategy_generation")
                        tp_valid = False
                    elif setup.direction == 'SHORT' and tp['price'] >= setup.entry_price:
                        plog.warning(f"TP{i+1} < entry for SHORT: {tp['price']:.2f} < {setup.entry_price:.2f} = {tp['price'] < setup.entry_price}", agent="strategy", phase="strategy_generation")
                        tp_valid = False
                plog.warning(f"All TPs valid: {tp_valid}", agent="strategy", phase="strategy_generation")

                return None
            
            plog.success(f"Professional setup built: {direction} @ {setup.entry_price:.2f}, Confirmation: {entry_confirmation.confirmed}, Pattern: {entry_confirmation.candle_pattern.pattern_type if entry_confirmation.candle_pattern else 'None'}", agent="strategy", phase="strategy_generation")
            
            return setup
            
        except Exception as e:
            import traceback
            plog.error(f"Error building setup: {e}", exception=e, agent="strategy", phase="strategy_generation")
            plog.error(f"Full traceback:\n{traceback.format_exc()}", agent="strategy", phase="strategy_generation")
            return None
    
    def _analyze_ltf_entry_confirmation(
        self,
        direction: str,
        entry_zone: Dict[str, float],
        candles_5m: List[Dict[str, Any]],
        candles_15m: List[Dict[str, Any]],
        current_price: float,
        volume_threshold: float
    ) -> EntryConfirmation:
        """
        Analyze lower timeframe (5M) for entry confirmation
        
        Professional Entry Rules:
        - LONG: Look for bullish rejection/engulfing at entry zone
        - SHORT: Look for bearish rejection/engulfing at entry zone
        """
        
        reasoning = []
        
        # Check if price is in entry zone
        in_entry_zone = (
            entry_zone['zone_low'] <= current_price <= entry_zone['zone_high']
        )
        
        if not in_entry_zone:
            return EntryConfirmation(
                confirmed=False,
                candle_pattern=None,
                price_action_signal='WAITING_FOR_ZONE',
                entry_trigger_met=False,
                confidence=0.0,
                reasoning=['Price not yet in entry zone']
            )
        
        reasoning.append('Price is in entry zone')
        
        # Analyze last 5 candles for patterns
        last_5_candles = candles_5m[-5:]

        # Check if we have sufficient candle data
        if not last_5_candles:
            return EntryConfirmation(
                confirmed=False,
                candle_pattern=None,
                price_action_signal='NO_CANDLE_DATA',
                entry_trigger_met=False,
                confidence=0.0,
                reasoning=['No 5M candle data available for entry confirmation']
            )

        # Detect candlestick patterns
        candle_pattern = self._detect_entry_patterns(
            direction=direction,
            candles=last_5_candles,
            entry_zone=entry_zone
        )
        
        if candle_pattern:
            reasoning.append(f"Pattern detected: {candle_pattern.pattern_type}")
        
        # Check momentum shift
        momentum_shifted = self._check_momentum_shift(
            direction=direction,
            candles_5m=last_5_candles,
            candles_15m=candles_15m[-3:]
        )
        
        if momentum_shifted:
            reasoning.append('Momentum shift confirmed on 5M')
        
        # Check volume confirmation
        volume_confirmed = self._check_volume_confirmation(
            last_5_candles, volume_threshold
        )
        
        if volume_confirmed:
            reasoning.append('Volume above average')
        
        # Check previous candle rejection
        rejection_present = self._check_rejection_at_zone(
            direction=direction,
            last_candle=last_5_candles[-1],
            entry_zone=entry_zone
        )
        
        if rejection_present:
            reasoning.append(f"Rejection wick at {entry_zone['zone_low' if direction == 'LONG' else 'zone_high']:.2f}")
        
        # Determine if entry trigger is met
        entry_trigger_met = self._evaluate_entry_trigger(
            direction=direction,
            candle_pattern=candle_pattern,
            momentum_shifted=momentum_shifted,
            volume_confirmed=volume_confirmed,
            rejection_present=rejection_present
        )
        
        # Calculate confirmation confidence
        confidence = self._calculate_entry_confidence(
            candle_pattern=candle_pattern,
            momentum_shifted=momentum_shifted,
            volume_confirmed=volume_confirmed,
            rejection_present=rejection_present
        )
        
        # Determine price action signal
        if entry_trigger_met:
            price_action_signal = 'ENTER_NOW'
        elif candle_pattern and not momentum_shifted:
            price_action_signal = 'WAIT_MOMENTUM'
        elif in_entry_zone and not candle_pattern:
            price_action_signal = 'WAIT_PATTERN'
        else:
            price_action_signal = 'WAIT'
        
        confirmed = entry_trigger_met and confidence >= 0.7
        
        return EntryConfirmation(
            confirmed=confirmed,
            candle_pattern=candle_pattern,
            price_action_signal=price_action_signal,
            entry_trigger_met=entry_trigger_met,
            confidence=confidence,
            reasoning=reasoning
        )
    
    def _detect_entry_patterns(
        self,
        direction: str,
        candles: List[Dict[str, Any]],
        entry_zone: Dict[str, float]
    ) -> Optional[CandlePattern]:
        """
        Detect professional candlestick entry patterns
        
        Patterns for LONG:
        1. Bullish Engulfing
        2. Hammer (rejection wick)
        3. Morning Star
        4. Bullish Pin Bar
        5. Three White Soldiers
        
        Patterns for SHORT:
        1. Bearish Engulfing
        2. Shooting Star
        3. Evening Star
        4. Bearish Pin Bar
        5. Three Black Crows
        """
        
        if len(candles) < 3:
            return None
        
        # Most recent 3 candles
        c1, c2, c3 = candles[-3], candles[-2], candles[-1]
        
        if direction == 'LONG':
            # Bullish Engulfing
            if (c2['close'] < c2['open'] and  # Previous bearish
                c3['close'] > c3['open'] and  # Current bullish
                c3['open'] < c2['close'] and  # Opens below previous close
                c3['close'] > c2['open'] and  # Closes above previous open
                c3['low'] <= entry_zone['zone_low'] * 1.005):  # Near entry zone
                
                body_ratio = (c3['close'] - c3['open']) / (c2['open'] - c2['close'])
                strength = min(body_ratio / 2, 1.0)
                
                return CandlePattern(
                    pattern_type='BULLISH_ENGULFING',
                    strength=strength,
                    direction='LONG',
                    candles_involved=2,
                    description=f"Bullish engulfing at entry zone {entry_zone['zone_low']:.2f}"
                )
            
            # Hammer (Rejection Pin Bar)
            if self._is_hammer(c3, entry_zone['zone_low']):
                lower_wick = c3['open'] - c3['low'] if c3['close'] > c3['open'] else c3['close'] - c3['low']
                body = abs(c3['close'] - c3['open'])
                
                if lower_wick > body * 2:  # Long lower wick
                    strength = min(lower_wick / body / 3, 1.0)
                    
                    return CandlePattern(
                        pattern_type='HAMMER_REJECTION',
                        strength=strength,
                        direction='LONG',
                        candles_involved=1,
                        description=f"Hammer rejection at {c3['low']:.2f}"
                    )
            
            # Three White Soldiers
            if len(candles) >= 3:
                if all(c['close'] > c['open'] for c in candles[-3:]):
                    if candles[-1]['close'] > candles[-2]['close'] > candles[-3]['close']:
                        return CandlePattern(
                            pattern_type='THREE_WHITE_SOLDIERS',
                            strength=0.85,
                            direction='LONG',
                            candles_involved=3,
                            description="Strong bullish momentum (3 green candles)"
                        )
        
        else:  # SHORT
            # Bearish Engulfing
            if (c2['close'] > c2['open'] and  # Previous bullish
                c3['close'] < c3['open'] and  # Current bearish
                c3['open'] > c2['close'] and  # Opens above previous close
                c3['close'] < c2['open'] and  # Closes below previous open
                c3['high'] >= entry_zone['zone_high'] * 0.995):  # Near entry zone
                
                body_ratio = (c3['open'] - c3['close']) / (c2['close'] - c2['open'])
                strength = min(body_ratio / 2, 1.0)
                
                return CandlePattern(
                    pattern_type='BEARISH_ENGULFING',
                    strength=strength,
                    direction='SHORT',
                    candles_involved=2,
                    description=f"Bearish engulfing at entry zone {entry_zone['zone_high']:.2f}"
                )
            
            # Shooting Star
            if self._is_shooting_star(c3, entry_zone['zone_high']):
                upper_wick = c3['high'] - max(c3['open'], c3['close'])
                body = abs(c3['close'] - c3['open'])
                
                if upper_wick > body * 2:  # Long upper wick
                    strength = min(upper_wick / body / 3, 1.0)
                    
                    return CandlePattern(
                        pattern_type='SHOOTING_STAR',
                        strength=strength,
                        direction='SHORT',
                        candles_involved=1,
                        description=f"Shooting star rejection at {c3['high']:.2f}"
                    )
            
            # Three Black Crows
            if len(candles) >= 3:
                if all(c['close'] < c['open'] for c in candles[-3:]):
                    if candles[-1]['close'] < candles[-2]['close'] < candles[-3]['close']:
                        return CandlePattern(
                            pattern_type='THREE_BLACK_CROWS',
                            strength=0.85,
                            direction='SHORT',
                            candles_involved=3,
                            description="Strong bearish momentum (3 red candles)"
                        )
        
        return None
    
    def _is_hammer(self, candle: Dict[str, Any], support_level: float) -> bool:
        """Check if candle is a hammer"""
        body = abs(candle['close'] - candle['open'])
        lower_wick = min(candle['open'], candle['close']) - candle['low']
        upper_wick = candle['high'] - max(candle['open'], candle['close'])
        
        # Hammer criteria
        return (
            lower_wick > body * 2 and  # Long lower wick
            upper_wick < body * 0.5 and  # Small upper wick
            candle['low'] <= support_level * 1.005  # Touched support
        )
    
    def _is_shooting_star(self, candle: Dict[str, Any], resistance_level: float) -> bool:
        """Check if candle is a shooting star"""
        body = abs(candle['close'] - candle['open'])
        upper_wick = candle['high'] - max(candle['open'], candle['close'])
        lower_wick = min(candle['open'], candle['close']) - candle['low']
        
        # Shooting star criteria
        return (
            upper_wick > body * 2 and  # Long upper wick
            lower_wick < body * 0.5 and  # Small lower wick
            candle['high'] >= resistance_level * 0.995  # Touched resistance
        )
    
    def _check_momentum_shift(
        self,
        direction: str,
        candles_5m: List[Dict[str, Any]],
        candles_15m: List[Dict[str, Any]]
    ) -> bool:
        """
        Check if momentum has shifted in favor of the trade
        
        For LONG: Previous candles bearish → Latest candles bullish
        For SHORT: Previous candles bullish → Latest candles bearish
        """
        
        if len(candles_5m) < 5 or len(candles_15m) < 3:
            return False
        
        # Analyze 5M candles
        prev_3_candles = candles_5m[-5:-2]  # Candles 3-5 ago
        recent_2_candles = candles_5m[-2:]   # Last 2 candles
        
        if direction == 'LONG':
            # Check if previous were bearish, recent are bullish
            prev_bearish = sum(1 for c in prev_3_candles if c['close'] < c['open']) >= 2
            recent_bullish = all(c['close'] > c['open'] for c in recent_2_candles)
            
            # Also check 15M for confirmation
            last_15m_bullish = candles_15m[-1]['close'] > candles_15m[-1]['open']
            
            return prev_bearish and recent_bullish and last_15m_bullish
        
        else:  # SHORT
            prev_bullish = sum(1 for c in prev_3_candles if c['close'] > c['open']) >= 2
            recent_bearish = all(c['close'] < c['open'] for c in recent_2_candles)
            last_15m_bearish = candles_15m[-1]['close'] < candles_15m[-1]['open']
            
            return prev_bullish and recent_bearish and last_15m_bearish
    
    def _check_volume_confirmation(
        self,
        candles: List[Dict[str, Any]],
        volume_threshold: float
    ) -> bool:
        """Check if recent volume is above average"""
        
        if len(candles) < 2:
            return False
        
        last_candle_volume = candles[-1]['volume']
        return last_candle_volume > volume_threshold
    
    def _calculate_volume_threshold(
        self,
        candles: List[Dict[str, Any]]
    ) -> float:
        """Calculate average volume threshold"""
        
        if len(candles) < 20:
            return 0.0
        
        volumes = [c['volume'] for c in candles[-20:]]
        return np.mean(volumes) * 1.3  # 30% above average
    
    def _check_rejection_at_zone(
        self,
        direction: str,
        last_candle: Dict[str, Any],
        entry_zone: Dict[str, float]
    ) -> bool:
        """Check if candle shows rejection at entry zone"""
        
        body = abs(last_candle['close'] - last_candle['open'])
        
        if direction == 'LONG':
            # Check for rejection wick at zone low
            lower_wick = min(last_candle['open'], last_candle['close']) - last_candle['low']
            
            return (
                last_candle['low'] <= entry_zone['zone_low'] * 1.005 and
                lower_wick > body * 1.5 and
                last_candle['close'] > last_candle['open']  # Closed bullish
            )
        
        else:  # SHORT
            # Check for rejection wick at zone high
            upper_wick = last_candle['high'] - max(last_candle['open'], last_candle['close'])
            
            return (
                last_candle['high'] >= entry_zone['zone_high'] * 0.995 and
                upper_wick > body * 1.5 and
                last_candle['close'] < last_candle['open']  # Closed bearish
            )
    
    def _evaluate_entry_trigger(
        self,
        direction: str,
        candle_pattern: Optional[CandlePattern],
        momentum_shifted: bool,
        volume_confirmed: bool,
        rejection_present: bool
    ) -> bool:
        """
        Evaluate if all entry triggers are met
        
        Required for Entry:
        1. Candle pattern present (strength > 0.6)
        2. Momentum shifted OR rejection present
        3. Volume confirmed (optional but preferred)
        """
        
        # Must have candle pattern
        if not candle_pattern or candle_pattern.strength < 0.6:
            return False
        
        # Must have momentum shift OR strong rejection
        if not (momentum_shifted or rejection_present):
            return False
        
        # Volume is a plus but not required
        return True
    
    def _calculate_entry_confidence(
        self,
        candle_pattern: Optional[CandlePattern],
        momentum_shifted: bool,
        volume_confirmed: bool,
        rejection_present: bool
    ) -> float:
        """Calculate entry confirmation confidence"""
        
        confidence = 0.0
        
        # Pattern contribution (40%)
        if candle_pattern:
            confidence += candle_pattern.strength * 0.4
        
        # Momentum contribution (30%)
        if momentum_shifted:
            confidence += 0.3
        
        # Volume contribution (15%)
        if volume_confirmed:
            confidence += 0.15
        
        # Rejection contribution (15%)
        if rejection_present:
            confidence += 0.15
        
        return min(confidence, 1.0)
    
    def _calculate_precise_entry(
        self,
        direction: str,
        entry_zone: Dict[str, float],
        candles_5m: List[Dict[str, Any]],
        confirmation: EntryConfirmation
    ) -> Dict[str, Any]:
        """
        Calculate precise entry price based on confirmation
        
        Entry Types:
        1. MARKET - Enter immediately (strong confirmation)
        2. LIMIT - Enter at specific price (wait for better fill)
        3. STOP_LIMIT - Enter on break above/below level
        """
        
        last_candle = candles_5m[-1]
        
        if confirmation.candle_pattern:
            pattern_type = confirmation.candle_pattern.pattern_type
            
            # Strong patterns - enter at market
            if pattern_type in ['BULLISH_ENGULFING', 'BEARISH_ENGULFING', 
                               'THREE_WHITE_SOLDIERS', 'THREE_BLACK_CROWS']:
                return {
                    'type': 'MARKET',
                    'price': float(last_candle['close']),
                    'trigger': f"Enter at market on {pattern_type}"
                }
            
            # Rejection patterns - enter at better price
            if pattern_type in ['HAMMER_REJECTION', 'SHOOTING_STAR']:
                if direction == 'LONG':
                    # Enter slightly above hammer low
                    entry_price = float(last_candle['low']) * 1.002
                else:
                    # Enter slightly below shooting star high
                    entry_price = float(last_candle['high']) * 0.998
                
                return {
                    'type': 'LIMIT',
                    'price': entry_price,
                    'trigger': f"Limit order at rejection level + buffer"
                }
        
        # Default - enter at optimal zone
        try:
            z_low = float(entry_zone['zone_low'])
            z_high = float(entry_zone['zone_high'])
        except (ValueError, TypeError):
            z_low = 0.0
            z_high = 0.0
            
        if direction == 'LONG':
            entry_price = z_low + (z_high - z_low) * 0.3
        else:
            entry_price = z_low + (z_high - z_low) * 0.7
        
        return {
            'type': 'LIMIT',
            'price': float(entry_price),
            'trigger': 'Enter at optimal zone level'
        }
    
    def _calculate_pending_entry(
        self,
        direction: str,
        entry_zone: Dict[str, float],
        candles_5m: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate pending entry (not yet confirmed)"""
        
        try:
            z_low = float(entry_zone['zone_low'])
            z_high = float(entry_zone['zone_high'])
        except (ValueError, TypeError):
            z_low = 0.0
            z_high = 0.0
            
        if direction == 'LONG':
            entry_price = z_low
        else:
            entry_price = z_high
        
        return {
            'type': 'PENDING_LIMIT',
            'price': float(entry_price),
            'trigger': f"Wait for price to reach {entry_price:.2f} and confirm with candle pattern"
        }
    
    def _calculate_professional_sl(
        self,
        direction: str,
        entry_price: float,
        entry_zone: Dict[str, float],
        candles_5m: List[Dict[str, Any]],
        candles_15m: List[Dict[str, Any]],
        atr: float,
        smc_data: Dict[str, Any]
    ) -> float:
        """
        Calculate professional stop-loss

        SL Placement Rules:
        1. Below/above recent swing low/high
        2. Beyond order block invalidation
        3. Consider ATR for volatility buffer
        4. Never more than 2% account risk
        """
        
        # Ensure all numeric inputs are floats
        try:
            entry_price = float(entry_price)
        except (ValueError, TypeError):
            plog.error(f"Invalid entry_price in SL calculation: {entry_price}", agent="strategy")
            entry_price = 0.0
        
        try:
            atr = float(atr)
        except (ValueError, TypeError):
            plog.warning(f"Invalid ATR in SL calculation: {atr}, using default", agent="strategy")
            atr = entry_price * 0.01 if entry_price > 0 else 100.0
        
        # Ensure entry_zone values are floats
        try:
            zone_low = float(entry_zone.get('zone_low', entry_price * 0.99))
            zone_high = float(entry_zone.get('zone_high', entry_price * 1.01))
        except (ValueError, TypeError):
            zone_low = entry_price * 0.99
            zone_high = entry_price * 1.01

        # Check if we have sufficient candle data
        if not candles_5m or len(candles_5m) < 10:
            # Fallback to ATR-based SL when no candle data
            if direction == 'LONG':
                sl = entry_price - (atr * 1.5)
            else:
                sl = entry_price + (atr * 1.5)
            return float(round(sl, 2))

        if direction == 'LONG':
            # Find recent swing low on 5M
            recent_lows = [c['low'] for c in candles_5m[-10:]]
            swing_low = min(recent_lows)

            # Check 15M for structure if available
            if candles_15m and len(candles_15m) >= 3:
                recent_15m_low = min(c['low'] for c in candles_15m[-3:])
                # Use lower of the two
                structure_low = min(swing_low, recent_15m_low)
            else:
                structure_low = swing_low

            # Add ATR buffer (10% of ATR)
            sl = structure_low - (atr * 0.1)

            # Ensure SL is below entry zone
            if sl >= zone_low:
                sl = zone_low * 0.995

        else:  # SHORT
            recent_highs = [c['high'] for c in candles_5m[-10:]]
            swing_high = max(recent_highs)

            # Check 15M for structure if available
            if candles_15m and len(candles_15m) >= 3:
                recent_15m_high = max(c['high'] for c in candles_15m[-3:])
                structure_high = max(swing_high, recent_15m_high)
            else:
                structure_high = swing_high

            sl = structure_high + (atr * 0.1)

            if sl <= zone_high:
                sl = zone_high * 1.005

        return float(round(sl, 2))
    
    def _build_professional_reasoning(
        self,
        opportunity: Dict[str, Any],
        confirmation: EntryConfirmation,
        precise_entry: Dict[str, Any]
    ) -> str:
        """Build detailed reasoning for the setup"""
        
        reasoning_parts = [
            f"=== Professional Trade Setup ===",
            "",
            f"Direction: {opportunity.get('direction')}",
            f"Confluence Count: {opportunity.get('confluence_count', 0)}",
            "",
            "Higher Timeframe Setup:",
        ]
        
        for factor in opportunity.get('key_factors', []):
            reasoning_parts.append(f"  ✓ {factor}")
        
        reasoning_parts.append("")
        reasoning_parts.append("Lower Timeframe Entry Confirmation:")
        
        if confirmation.confirmed:
            reasoning_parts.append(f"  ✅ CONFIRMED - {confirmation.price_action_signal}")
            
            if confirmation.candle_pattern:
                pattern = confirmation.candle_pattern
                reasoning_parts.append(f"  📊 Pattern: {pattern.pattern_type} (strength: {pattern.strength:.2f})")
                reasoning_parts.append(f"     {pattern.description}")
            
            for reason in confirmation.reasoning:
                reasoning_parts.append(f"  ✓ {reason}")
            
            reasoning_parts.append("")
            reasoning_parts.append(f"Entry Execution: {precise_entry['type']}")
            reasoning_parts.append(f"  {precise_entry['trigger']}")
            reasoning_parts.append(f"  Price: ${precise_entry['price']:.2f}")
        
        else:
            reasoning_parts.append(f"  ⏳ WAITING - {confirmation.price_action_signal}")
            reasoning_parts.append(f"  Confirmation Confidence: {confirmation.confidence:.2f}")
            
            for reason in confirmation.reasoning:
                reasoning_parts.append(f"  • {reason}")
            
            reasoning_parts.append("")
            reasoning_parts.append("Waiting for:")
            if not confirmation.candle_pattern:
                reasoning_parts.append("  • Bullish/Bearish candle pattern")
            if confirmation.confidence < 0.7:
                reasoning_parts.append("  • Higher confidence signal")
        
        return "\n".join(reasoning_parts)
    
    def _calculate_htf_entry_zone(
        self,
        direction: str,
        opportunity: Dict[str, Any],
        smc_data: Dict[str, Any],
        ict_data: Dict[str, Any],
        current_price: float
    ) -> Dict[str, float]:
        """
        Calculate higher timeframe entry zone (same as before but clearer)
        """
        
        # Ensure current_price is valid
        if not current_price or current_price == 0:
            plog.warning(f"Invalid current_price: {current_price}, using fallback 43000", agent="strategy")
            current_price = 43000.0
        
        entry_zone_raw = opportunity.get('entry_zone', [current_price, current_price])
        
        # Validate entry_zone_raw
        if not entry_zone_raw or entry_zone_raw[0] == 0:
            entry_zone_raw = [current_price * 0.99, current_price * 1.01]
        
        # Safely convert entry zone values to float
        try:
            zone_low_raw = float(entry_zone_raw[0]) if len(entry_zone_raw) >= 2 else current_price * 0.995
            zone_low = zone_low_raw if zone_low_raw > 0 else current_price * 0.995
        except (ValueError, TypeError, IndexError):
            zone_low = current_price * 0.995
        
        try:
            zone_high_raw = float(entry_zone_raw[1]) if len(entry_zone_raw) >= 2 else current_price * 1.005
            zone_high = zone_high_raw if zone_high_raw > 0 else current_price * 1.005
        except (ValueError, TypeError, IndexError):
            zone_high = current_price * 1.005
        
        # Refine with Order Blocks
        computational = smc_data.get('computational', {})
        order_blocks = computational.get('order_blocks', [])
        
        if order_blocks:
            relevant_obs = [
                ob for ob in order_blocks
                if ob['type'] == ('bullish' if direction == 'LONG' else 'bearish')
            ]
            
            if relevant_obs:
                # Safely get strength for comparison
                def get_strength(ob):
                    try:
                        return float(ob.get('strength', 0))
                    except (ValueError, TypeError):
                        return 0.0
                
                best_ob = max(relevant_obs, key=get_strength)
                # Order block zone is a dict with 'high' and 'low' keys
                zone_dict = best_ob.get('zone', {})
                if isinstance(zone_dict, dict):
                    try:
                        zone_low = float(zone_dict.get('low', zone_low))
                        zone_high = float(zone_dict.get('high', zone_high))
                    except (ValueError, TypeError):
                        pass  # Keep existing values
                elif isinstance(zone_dict, (list, tuple)) and len(zone_dict) >= 2:
                    try:
                        zone_low = float(zone_dict[0])
                        zone_high = float(zone_dict[1])
                    except (ValueError, TypeError):
                        pass  # Keep existing values
        
        # Check OTE zone
        ict_computational = ict_data.get('computational', {})
        ote_zones = ict_computational.get('ote_zones', {})
        
        if ote_zones and ote_zones.get('in_ote_zone'):
            try:
                zone_low = float(ote_zones['ote_low'])
                zone_high = float(ote_zones['ote_high'])
            except (ValueError, TypeError, KeyError):
                pass  # Keep existing values
        
        # Calculate optimal entry within zone
        if direction == 'LONG':
            optimal_entry = zone_low + (zone_high - zone_low) * 0.3
        else:
            optimal_entry = zone_low + (zone_high - zone_low) * 0.7
        
        return {
            'optimal_entry': float(round(optimal_entry, 2)),
            'zone_low': float(round(zone_low, 2)),
            'zone_high': float(round(zone_high, 2))
        }
    
    def _generate_professional_tps(
        self,
        direction: str,
        entry_price: float,
        stop_loss: float,
        analysis: Dict[str, Any],
        candles_1h: List[Dict[str, Any]]
    ) -> List[Dict[str, float]]:
        """Generate professional take-profit levels"""
        
        # Ensure entry_price and stop_loss are floats
        try:
            entry_price = float(entry_price)
        except (ValueError, TypeError):
            plog.error(f"Invalid entry_price in TP generation: {entry_price}", agent="strategy")
            entry_price = 0.0
        
        try:
            stop_loss = float(stop_loss)
        except (ValueError, TypeError):
            plog.error(f"Invalid stop_loss in TP generation: {stop_loss}", agent="strategy")
            stop_loss = 0.0
        
        risk = abs(entry_price - stop_loss)
        
        # Base TP levels (RR multiples)
        if direction == 'LONG':
            tp1_base = entry_price + (risk * 1.5)
            tp2_base = entry_price + (risk * 2.5)
            tp3_base = entry_price + (risk * 4.0)
        else:
            tp1_base = entry_price - (risk * 1.5)
            tp2_base = entry_price - (risk * 2.5)
            tp3_base = entry_price - (risk * 4.0)
        
        # Refine with key levels
        key_levels = analysis.get('key_levels', {})
        
        tp1 = self._refine_tp_with_levels(
            tp1_base, direction, key_levels, analysis.get('smc_analysis', {}), 0.02
        )
        tp2 = self._refine_tp_with_levels(
            tp2_base, direction, key_levels, analysis.get('smc_analysis', {}), 0.02
        )
        tp3 = self._refine_tp_with_levels(
            tp3_base, direction, key_levels, analysis.get('smc_analysis', {}), 0.03
        )
        
        return [
            {'level': 1, 'price': float(round(tp1, 2)), 'size': 0.33},
            {'level': 2, 'price': float(round(tp2, 2)), 'size': 0.33},
            {'level': 3, 'price': float(round(tp3, 2)), 'size': 0.34}
        ]
    
    def _refine_tp_with_levels(
        self,
        tp_price: float,
        direction: str,
        key_levels: Dict[str, List[float]],
        smc_data: Dict[str, Any],
        tolerance: float
    ) -> float:
        """Refine TP by snapping to nearby key levels"""
        
        # Ensure tp_price is float
        try:
            tp_price = float(tp_price)
        except (ValueError, TypeError):
            plog.error(f"Invalid tp_price: {tp_price}, using as-is", agent="strategy")
            return tp_price
        
        target_levels = key_levels.get(
            'resistance' if direction == 'LONG' else 'support',
            []
        )
        
        # CRITICAL FIX: Convert all levels to float before comparison
        for level_raw in target_levels:
            try:
                level = float(level_raw)
            except (ValueError, TypeError):
                plog.warning(f"Skipping invalid level: {level_raw} (type: {type(level_raw)})", agent="strategy")
                continue
            
            try:
                if abs(level - tp_price) / tp_price < tolerance:
                    if direction == 'LONG':
                        return float(level * 0.999)
                    else:
                        return float(level * 1.001)
            except (ZeroDivisionError, TypeError) as e:
                plog.warning(f"Error comparing level {level} with tp_price {tp_price}: {e}", agent="strategy")
                continue
        
        # Check FVG levels
        computational = smc_data.get('computational', {})
        fvgs = computational.get('fair_value_gaps', [])
        
        for fvg in fvgs:
            if not fvg.get('filled', False):
                # FVG structure: has 'top' and 'bottom' keys (or 'midpoint')
                fvg_mid = fvg.get('midpoint')
                if not fvg_mid:
                    try:
                        top = float(fvg.get('top', 0))
                        bottom = float(fvg.get('bottom', 0))
                        fvg_mid = (top + bottom) / 2
                    except (ValueError, TypeError) as e:
                        plog.warning(f"Invalid FVG data: {fvg}, error: {e}", agent="strategy")
                        continue
                
                try:
                    fvg_mid = float(fvg_mid)
                    if fvg_mid and abs(fvg_mid - tp_price) / tp_price < tolerance:
                        return float(fvg_mid)
                except (ValueError, TypeError, ZeroDivisionError) as e:
                    plog.warning(f"Error processing FVG midpoint {fvg_mid}: {e}", agent="strategy")
                    continue
        
        return float(tp_price)
    
    def _calculate_rr(
        self,
        entry: float,
        sl: float,
        tps: List[Dict[str, float]]
    ) -> float:
        """Calculate risk-reward ratio"""
        risk = abs(entry - sl)
        total_reward = sum(abs(tp['price'] - entry) * tp['size'] for tp in tps)
        rr_ratio = total_reward / risk if risk > 0 else 0.0
        plog.debug(f"RR Calculation: Entry={entry:.2f}, SL={sl:.2f}, Risk={risk:.2f}, Total Reward={total_reward:.2f}, RR={rr_ratio:.2f}", agent="strategy", phase="strategy_generation")
        return round(rr_ratio, 2)
    
    def _calculate_confidence(
        self,
        opportunity: Dict[str, Any],
        confirmation: EntryConfirmation
    ) -> float:
        """Calculate overall confidence score"""
        
        # Base confidence from opportunity
        base_conf = opportunity.get('confidence', 0.75)
        
        # Adjust with entry confirmation
        if confirmation.confirmed:
            # Boost confidence if entry is confirmed
            conf_boost = confirmation.confidence * 0.15
            final_conf = min(base_conf + conf_boost, 0.95)
        else:
            # Reduce confidence if entry not confirmed
            final_conf = base_conf * 0.85
        
        return round(final_conf, 2)
    
    def _classify_strategy_type(
        self,
        ict_data: Dict[str, Any],
        tp_distance: float
    ) -> str:
        """Classify strategy type"""
        
        computational = ict_data.get('computational', {})
        killzone = computational.get('killzone', {})
        
        if killzone.get('current_killzone') in ['london', 'new_york']:
            if tp_distance < 200:
                return 'SCALP'
            else:
                return 'DAY_TRADE'
        
        if tp_distance > 500:
            return 'SWING'
        elif tp_distance > 300:
            return 'DAY_TRADE'
        else:
            return 'SCALP'
    
    def _estimate_duration(self, strategy_type: str) -> float:
        """Estimate holding time"""
        duration_map = {
            'SCALP': 1.5,
            'DAY_TRADE': 6.0,
            'SWING': 48.0
        }
        return duration_map.get(strategy_type, 6.0)
    
    def _build_invalidation_conditions(
        self,
        direction: str,
        stop_loss: float,
        candles_5m: List[Dict[str, Any]]
    ) -> List[str]:
        """Build invalidation conditions"""
        
        conditions = [
            f"Price breaks {stop_loss:.2f} ({direction} setup invalidated)"
        ]
        
        if direction == 'LONG':
            conditions.append("Break of bullish structure on higher timeframe")
            conditions.append("5M closes below entry zone after 3+ attempts")
        else:
            conditions.append("Break of bearish structure on higher timeframe")
            conditions.append("5M closes above entry zone after 3+ attempts")
        
        return conditions
    
    def _select_best_opportunity(
        self,
        opportunities: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Select best opportunity"""

        if not opportunities:
            plog.warning("_select_best_opportunity: No opportunities provided", agent="strategy", phase="strategy_generation")
            return None

        plog.info(f"_select_best_opportunity: Evaluating {len(opportunities)} opportunities", agent="strategy", phase="strategy_generation")

        # Helper function to safely extract numeric values
        def get_numeric_key(opp):
            try:
                confluence = int(opp.get('confluence_count', 0))
            except (ValueError, TypeError):
                confluence = 0
            
            try:
                confidence = float(opp.get('confidence', 0))
            except (ValueError, TypeError):
                confidence = 0.0
            
            return (confluence, confidence)

        sorted_opps = sorted(
            opportunities,
            key=get_numeric_key,
            reverse=True
        )

        best = sorted_opps[0]
        
        # Ensure numeric types for validation
        try:
            confluence_count = int(best.get('confluence_count', 0))
        except (ValueError, TypeError):
            confluence_count = 0
            
        try:
            confidence = float(best.get('confidence', 0))
        except (ValueError, TypeError):
            confidence = 0.0

        plog.info(f"_select_best_opportunity: Best opportunity - {best.get('direction')} with {confluence_count} confluences, {confidence:.1%} confidence", agent="strategy", phase="strategy_generation")

        plog.info(f"_select_best_opportunity: Checking confluence >= 3: {confluence_count} >= 3 = {confluence_count >= 3}", agent="strategy", phase="strategy_generation")
        if confluence_count < 3:
            plog.warning(f"_select_best_opportunity: FAILED - Insufficient confluences: {confluence_count} < 3 required", agent="strategy", phase="strategy_generation")
            return None

        plog.info(f"_select_best_opportunity: Checking confidence >= 60%: {confidence:.1%} >= 60% = {confidence >= 0.60}", agent="strategy", phase="strategy_generation")
        if confidence < 0.60:
            plog.warning(f"_select_best_opportunity: FAILED - Insufficient confidence: {confidence:.1%} < 60% required", agent="strategy", phase="strategy_generation")
            return None

        plog.info("_select_best_opportunity: PASSED - Opportunity selected", agent="strategy", phase="strategy_generation")
        return best
    
    def _generate_setup_id(self, symbol: str) -> str:
        """Generate unique setup ID"""
        self.setup_counter += 1
        timestamp = int(datetime.utcnow().timestamp())
        return f"{symbol}_{timestamp}_{self.setup_counter}"

    def _sanitize_candles(self, candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sanitize candle data by converting numeric fields to floats.
        Handles both dictionary and object access if needed.
        """
        sanitized = []
        for c in candles:
            new_c = c.copy()
            # Fields to convert
            for field in ['open', 'high', 'low', 'close', 'volume']:
                if field in new_c:
                    try:
                        new_c[field] = float(new_c[field])
                    except (ValueError, TypeError):
                        # Use default value if conversion fails
                        plog.warning(f"Failed to convert {field} to float: {new_c[field]}, using 0.0", agent="strategy")
                        new_c[field] = 0.0
            sanitized.append(new_c)
        return sanitized

