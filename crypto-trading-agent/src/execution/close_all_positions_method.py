    async def close_all_positions(self, reason: str = "System Shutdown") -> Dict[str, Any]:
        """
        Close all open positions immediately.
        Used for emergency shutdown or system reset.
        
        Returns:
            Dict with success status, closed positions, failures, and total P&L
        """
        result = {
            'success': True,
            'closed_positions': [],
            'failed_positions': [],
            'total_realized_pnl': 0.0,
            'errors': []
        }
        
        positions_to_close = list(self.positions.values())
        
        if not positions_to_close:
            logger.info("No open positions to close.")
            return result
            
        logger.warning(f"🚨 Closing {len(positions_to_close)} positions due to: {reason}")
        
        # Initialize DB manager for persistence
        db_manager = None
        try:
            from src.utils.config import get_config
            from src.memory.trade_history_manager import TradeHistoryManager
            config = get_config()
            db_manager = TradeHistoryManager(config.database.postgres_url)
            logger.info("✅ Database manager initialized for shutdown")
        except Exception as e:
            logger.error(f"Failed to initialize DB manager for shutdown: {e}")
            result['errors'].append(f"DB init failed: {str(e)}")
        
        for position in positions_to_close:
            try:
                # Determine close side
                close_side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY
                
                # Place market close order
                logger.info(f"Closing {position.symbol} ({position.side}) position...")
                
                # Ensure we have a price
                if position.symbol not in self.current_prices:
                    # Use current price from position if available, otherwise fallback
                    self.current_prices[position.symbol] = position.current_price
                
                order_result = await self.place_order(
                    symbol=position.symbol,
                    side=close_side,
                    order_type=OrderType.MARKET,
                    quantity=position.quantity,
                    reduce_only=True
                )
                
                if order_result['status'] == 'FILLED':
                    exit_price = float(order_result.get('avgPrice', 0))
                    
                    # Calculate P&L
                    if position.side == "LONG":
                        pnl = (exit_price - position.entry_price) * position.quantity
                    else:
                        pnl = (position.entry_price - exit_price) * position.quantity
                    
                    result['closed_positions'].append({
                        'symbol': position.symbol,
                        'side': position.side,
                        'pnl': pnl,
                        'exit_price': exit_price,
                        'position_id': position.position_id
                    })
                    result['total_realized_pnl'] += pnl
                    
                    logger.success(f"✅ Closed {position.symbol} at ${exit_price:.2f}, P&L: ${pnl:+.2f}")
                    
                    # CRITICAL FIX: Update database with exit details
                    if db_manager and position.position_id:
                        try:
                            # CRITICAL: Strip "POS_" prefix to get actual trade_id
                            # position_id format: "POS_PT_123456"
                            # trade_id format: "PT_123456"
                            trade_id = position.position_id.replace("POS_", "") if position.position_id.startswith("POS_") else position.position_id
                            
                            db_manager.update_trade_exit(
                                trade_id=trade_id,
                                exit_price=exit_price,
                                exit_time=datetime.now(),
                                exit_reason=reason,
                                notes=f"Force closed due to {reason}"
                            )
                            logger.info(f"💾 Updated trade {trade_id} in database")
                        except Exception as db_e:
                            logger.error(f"Failed to update DB for {position.position_id}: {db_e}")
                            result['errors'].append(f"DB update failed for {position.position_id}: {str(db_e)}")
                    
                else:
                    logger.error(f"❌ Failed to close {position.symbol}: {order_result}")
                    result['failed_positions'].append({
                        'symbol': position.symbol,
                        'error': f"Order status: {order_result.get('status')}"
                    })
                    result['success'] = False
                    
            except Exception as e:
                logger.error(f"Error closing position {position.symbol}: {e}")
                result['failed_positions'].append({
                    'symbol': position.symbol,
                    'error': str(e)
                })
                result['errors'].append(f"Error closing {position.symbol}: {str(e)}")
                result['success'] = False
        
        # CRITICAL FIX: Clear Redis positions after all closes
        if self.state_manager:
            try:
                await self.state_manager.redis.delete("state:positions")
                logger.info("💾 Cleared positions from Redis StateManager")
            except Exception as e:
                logger.error(f"Failed to clear Redis positions: {e}")
                result['errors'].append(f"Redis clear failed: {str(e)}")
        
        # CRITICAL FIX: Broadcast empty positions to frontend
        await self._publish_update("execution_status", "position_update", [])
        logger.info("📡 Broadcast empty positions to frontend")
        
        # Publish final portfolio update
        await self.publish_portfolio_update()
        
        logger.info(
            f"🏁 Shutdown complete: {len(result['closed_positions'])} closed, "
            f"{len(result['failed_positions'])} failed, "
            f"Total P&L: ${result['total_realized_pnl']:+.2f}"
        )
        
        return result
