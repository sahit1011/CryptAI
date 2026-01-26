"""
Data Sanitization Utilities
Ensures type safety between agent boundaries
"""
from typing import Dict, Any, List, Optional
from src.utils.pipeline_logger import PipelineLogger

plog = PipelineLogger()


class DataSanitizer:
    """Sanitize data to ensure type consistency across agent boundaries"""
    
    @staticmethod
    def sanitize_key_levels(levels: Dict[str, Any]) -> Dict[str, List[float]]:
        """
        Ensure all key level values are floats
        
        Args:
            levels: Dictionary with 'resistance' and 'support' keys
            
        Returns:
            Sanitized dictionary with float lists
        """
        sanitized = {'resistance': [], 'support': []}
        
        for key in ['resistance', 'support']:
            level_list = levels.get(key, [])
            
            if not isinstance(level_list, list):
                plog.warning(
                    f"key_levels['{key}'] is not a list (type: {type(level_list)}), converting to empty list",
                    agent="data_sanitizer"
                )
                level_list = []
            
            for level in level_list:
                try:
                    sanitized[key].append(float(level))
                except (ValueError, TypeError) as e:
                    plog.warning(
                        f"Skipping invalid {key} level: {level} (type: {type(level)}), error: {e}",
                        agent="data_sanitizer"
                    )
        
        plog.debug(
            f"Sanitized key_levels: {len(sanitized['resistance'])} resistance, {len(sanitized['support'])} support",
            agent="data_sanitizer"
        )
        
        return sanitized
    
    @staticmethod
    def sanitize_trade_opportunities(opportunities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Ensure trade opportunities have correct types
        
        Args:
            opportunities: List of opportunity dictionaries
            
        Returns:
            Sanitized list with proper types
        """
        sanitized = []
        
        for idx, opp in enumerate(opportunities):
            try:
                # Ensure direction is uppercase string
                direction = str(opp.get('direction', 'LONG')).upper()
                if direction not in ['LONG', 'SHORT']:
                    plog.warning(
                        f"Invalid direction '{direction}' in opportunity {idx}, defaulting to LONG",
                        agent="data_sanitizer"
                    )
                    direction = 'LONG'
                
                # Ensure confluence_count is int
                try:
                    confluence_count = int(opp.get('confluence_count', 0))
                except (ValueError, TypeError):
                    plog.warning(
                        f"Invalid confluence_count in opportunity {idx}, defaulting to 0",
                        agent="data_sanitizer"
                    )
                    confluence_count = 0
                
                # Ensure confidence is float between 0 and 1
                try:
                    confidence = float(opp.get('confidence', 0))
                    confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
                except (ValueError, TypeError):
                    plog.warning(
                        f"Invalid confidence in opportunity {idx}, defaulting to 0.0",
                        agent="data_sanitizer"
                    )
                    confidence = 0.0
                
                # Ensure entry_zone is list of 2 floats
                entry_zone_raw = opp.get('entry_zone', [0, 0])
                if not isinstance(entry_zone_raw, list) or len(entry_zone_raw) < 2:
                    plog.warning(
                        f"Invalid entry_zone in opportunity {idx}, using default [0, 0]",
                        agent="data_sanitizer"
                    )
                    entry_zone = [0.0, 0.0]
                else:
                    try:
                        entry_zone = [
                            float(entry_zone_raw[0]),
                            float(entry_zone_raw[1])
                        ]
                    except (ValueError, TypeError, IndexError) as e:
                        plog.warning(
                            f"Error converting entry_zone in opportunity {idx}: {e}, using default",
                            agent="data_sanitizer"
                        )
                        entry_zone = [0.0, 0.0]
                
                # Ensure key_factors is list of strings
                key_factors = opp.get('key_factors', [])
                if not isinstance(key_factors, list):
                    key_factors = []
                key_factors = [str(f) for f in key_factors]
                
                sanitized.append({
                    'direction': direction,
                    'confluence_count': confluence_count,
                    'confidence': confidence,
                    'entry_zone': entry_zone,
                    'key_factors': key_factors
                })
                
            except Exception as e:
                plog.error(
                    f"Error sanitizing opportunity {idx}: {e}, skipping",
                    exception=e,
                    agent="data_sanitizer"
                )
        
        plog.debug(
            f"Sanitized {len(sanitized)}/{len(opportunities)} trade opportunities",
            agent="data_sanitizer"
        )
        
        return sanitized
    
    @staticmethod
    def sanitize_order_blocks(order_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Ensure order blocks have correct types
        
        Args:
            order_blocks: List of order block dictionaries
            
        Returns:
            Sanitized list with proper types
        """
        sanitized = []
        
        for idx, ob in enumerate(order_blocks):
            try:
                # Ensure type is valid
                ob_type = str(ob.get('type', 'bullish')).lower()
                if ob_type not in ['bullish', 'bearish']:
                    plog.warning(
                        f"Invalid order block type '{ob_type}' at index {idx}, defaulting to 'bullish'",
                        agent="data_sanitizer"
                    )
                    ob_type = 'bullish'
                
                # Ensure zone has 'low' and 'high' as floats
                zone = ob.get('zone', {})
                if isinstance(zone, dict):
                    try:
                        zone_sanitized = {
                            'low': float(zone.get('low', 0)),
                            'high': float(zone.get('high', 0))
                        }
                    except (ValueError, TypeError) as e:
                        plog.warning(
                            f"Invalid zone in order block {idx}: {e}, using default",
                            agent="data_sanitizer"
                        )
                        zone_sanitized = {'low': 0.0, 'high': 0.0}
                elif isinstance(zone, (list, tuple)) and len(zone) >= 2:
                    try:
                        zone_sanitized = {
                            'low': float(zone[0]),
                            'high': float(zone[1])
                        }
                    except (ValueError, TypeError, IndexError) as e:
                        plog.warning(
                            f"Invalid zone list in order block {idx}: {e}, using default",
                            agent="data_sanitizer"
                        )
                        zone_sanitized = {'low': 0.0, 'high': 0.0}
                else:
                    plog.warning(
                        f"Invalid zone format in order block {idx}, using default",
                        agent="data_sanitizer"
                    )
                    zone_sanitized = {'low': 0.0, 'high': 0.0}
                
                # Ensure strength is float between 0 and 1
                try:
                    strength = float(ob.get('strength', 0))
                    strength = max(0.0, min(1.0, strength))
                except (ValueError, TypeError):
                    plog.warning(
                        f"Invalid strength in order block {idx}, defaulting to 0.0",
                        agent="data_sanitizer"
                    )
                    strength = 0.0
                
                # Ensure timeframe is string
                timeframe = str(ob.get('timeframe', 'unknown'))
                
                sanitized.append({
                    'type': ob_type,
                    'zone': zone_sanitized,
                    'strength': strength,
                    'timeframe': timeframe
                })
                
            except Exception as e:
                plog.error(
                    f"Error sanitizing order block {idx}: {e}, skipping",
                    exception=e,
                    agent="data_sanitizer"
                )
        
        plog.debug(
            f"Sanitized {len(sanitized)}/{len(order_blocks)} order blocks",
            agent="data_sanitizer"
        )
        
        return sanitized
    
    @staticmethod
    def sanitize_fair_value_gaps(fvgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Ensure FVGs have correct types
        
        Args:
            fvgs: List of FVG dictionaries
            
        Returns:
            Sanitized list with proper types
        """
        sanitized = []
        
        for idx, fvg in enumerate(fvgs):
            try:
                # Ensure top and bottom are floats
                try:
                    top = float(fvg.get('top', 0))
                    bottom = float(fvg.get('bottom', 0))
                except (ValueError, TypeError) as e:
                    plog.warning(
                        f"Invalid top/bottom in FVG {idx}: {e}, skipping",
                        agent="data_sanitizer"
                    )
                    continue
                
                # Calculate midpoint if not provided
                midpoint = fvg.get('midpoint')
                if midpoint is None:
                    midpoint = (top + bottom) / 2
                else:
                    try:
                        midpoint = float(midpoint)
                    except (ValueError, TypeError):
                        midpoint = (top + bottom) / 2
                
                # Ensure filled is boolean
                filled = bool(fvg.get('filled', False))
                
                # Ensure probability is float between 0 and 1
                try:
                    probability = float(fvg.get('probability', 0.5))
                    probability = max(0.0, min(1.0, probability))
                except (ValueError, TypeError):
                    probability = 0.5
                
                sanitized.append({
                    'top': top,
                    'bottom': bottom,
                    'midpoint': midpoint,
                    'filled': filled,
                    'probability': probability
                })
                
            except Exception as e:
                plog.error(
                    f"Error sanitizing FVG {idx}: {e}, skipping",
                    exception=e,
                    agent="data_sanitizer"
                )
        
        plog.debug(
            f"Sanitized {len(sanitized)}/{len(fvgs)} FVGs",
            agent="data_sanitizer"
        )
        
        return sanitized
    
    @staticmethod
    def sanitize_analysis_for_strategy(analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Comprehensive sanitization of analysis data before sending to strategy agent
        
        Args:
            analysis: Raw analysis dictionary from analysis agent
            
        Returns:
            Sanitized analysis dictionary with guaranteed types
        """
        plog.info("Sanitizing analysis data for strategy agent", agent="data_sanitizer")
        
        sanitized = {}
        
        # Basic fields
        sanitized['symbol'] = str(analysis.get('symbol', 'UNKNOWN'))
        sanitized['timestamp'] = analysis.get('timestamp')
        
        # Sanitize key_levels
        sanitized['key_levels'] = DataSanitizer.sanitize_key_levels(
            analysis.get('key_levels', {})
        )
        
        # Sanitize trade_opportunities
        sanitized['trade_opportunities'] = DataSanitizer.sanitize_trade_opportunities(
            analysis.get('trade_opportunities', [])
        )
        
        # Sanitize SMC analysis
        smc_analysis = analysis.get('smc_analysis', {})
        if isinstance(smc_analysis, dict):
            computational = smc_analysis.get('computational', {})
            
            # Sanitize order blocks
            if 'order_blocks' in computational:
                computational['order_blocks'] = DataSanitizer.sanitize_order_blocks(
                    computational.get('order_blocks', [])
                )
            
            # Sanitize FVGs
            if 'fair_value_gaps' in computational:
                computational['fair_value_gaps'] = DataSanitizer.sanitize_fair_value_gaps(
                    computational.get('fair_value_gaps', [])
                )
            
            smc_analysis['computational'] = computational
        
        sanitized['smc_analysis'] = smc_analysis
        
        # Pass through other fields as-is (ICT, MTF, etc.)
        sanitized['ict_analysis'] = analysis.get('ict_analysis', {})
        sanitized['mtf_analysis'] = analysis.get('mtf_analysis', {})
        sanitized['_raw_computational'] = analysis.get('_raw_computational', {})
        
        plog.success("Analysis data sanitization complete", agent="data_sanitizer")
        
        return sanitized
