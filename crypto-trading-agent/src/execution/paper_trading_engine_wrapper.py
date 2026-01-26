
    # ============================================================================
    # Exchange Client Interface Compatibility Methods
    # These methods make PaperTradingEngine compatible with OrderManager
    # ============================================================================
    
    async def place_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float
    ):
        """Place market order (OrderManager interface)"""
        result = await self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity
        )
        
        # Convert to Order object for compatibility
        from src.execution.exchange_client import Order, OrderStatus as ExchangeOrderStatus
        
        return Order(
            order_id=result['orderId'],
            symbol=result['symbol'],
            side=result['side'],
            type=result['type'],
            quantity=float(result['origQty']),
            price=float(result['price']) if result['price'] != '0' else None,
            status=ExchangeOrderStatus.FILLED if result['status'] == 'FILLED' else ExchangeOrderStatus.OPEN,
            filled_quantity=float(result['executedQty']),
            average_price=float(result['avgPrice']) if result['avgPrice'] != '0' else None,
            timestamp=datetime.now()
        )
    
    async def place_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float
    ):
        """Place limit order (OrderManager interface)"""
        result = await self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=price
        )
        
        from src.execution.exchange_client import Order, OrderStatus as ExchangeOrderStatus
        
        return Order(
            order_id=result['orderId'],
            symbol=result['symbol'],
            side=result['side'],
            type=result['type'],
            quantity=float(result['origQty']),
            price=float(result['price']),
            status=ExchangeOrderStatus.FILLED if result['status'] == 'FILLED' else ExchangeOrderStatus.OPEN,
            filled_quantity=float(result['executedQty']),
            average_price=float(result['avgPrice']) if result['avgPrice'] != '0' else None,
            timestamp=datetime.now()
        )
    
    async def place_stop_loss_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        stop_price: float
    ):
        """Place stop-loss order (OrderManager interface)"""
        result = await self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.STOP_MARKET,
            quantity=quantity,
            stop_price=stop_price,
            reduce_only=True
        )
        
        from src.execution.exchange_client import Order, OrderStatus as ExchangeOrderStatus
        
        return Order(
            order_id=result['orderId'],
            symbol=result['symbol'],
            side=result['side'],
            type=result['type'],
            quantity=float(result['origQty']),
            price=None,
            status=ExchangeOrderStatus.OPEN,
            filled_quantity=float(result['executedQty']),
            average_price=float(result['avgPrice']) if result['avgPrice'] != '0' else None,
            timestamp=datetime.now(),
            stop_price=stop_price
        )
    
    async def get_order_status(self, symbol: str, order_id: str):
        """Get order status (OrderManager interface)"""
        order_dict = self.get_order(order_id)
        if not order_dict:
            return None
        
        from src.execution.exchange_client import Order, OrderStatus as ExchangeOrderStatus
        
        status_map = {
            'PENDING': ExchangeOrderStatus.PENDING,
            'OPEN': ExchangeOrderStatus.OPEN,
            'FILLED': ExchangeOrderStatus.FILLED,
            'CANCELED': ExchangeOrderStatus.CANCELED,
            'REJECTED': ExchangeOrderStatus.REJECTED
        }
        
        return Order(
            order_id=order_dict['orderId'],
            symbol=order_dict['symbol'],
            side=order_dict['side'],
            type=order_dict['type'],
            quantity=float(order_dict['origQty']),
            price=float(order_dict['price']) if order_dict['price'] != '0' else None,
            status=status_map.get(order_dict['status'], ExchangeOrderStatus.OPEN),
            filled_quantity=float(order_dict['executedQty']),
            average_price=float(order_dict['avgPrice']) if order_dict['avgPrice'] != '0' else None,
            timestamp=datetime.fromtimestamp(order_dict['updateTime'] / 1000)
        )
