from typing import Dict, Any
from core.portfolio import Portfolio

class Broker:
    def __init__(self, portfolio: Portfolio, commission_rate: float = 0.001):
        self.portfolio = portfolio
        self.commission_rate = commission_rate
        self.trades = []  # List to store executed trades
        
    def execute_order(self, symbol: str, side: str, qty: float, price: float, timestamp: Any = None, slippage: float = 0.0, strategy_id: str = "Manual") -> Dict:
        """
        Execute an order.
        side: 'buy', 'sell' (reduce long), 'short', 'cover' (reduce short)
        qty: always positive
        price: execution price (base price)
        timestamp: time of execution
        slippage: percentage slippage (e.g., 0.0005 for 0.05%)
        strategy_id: ID of the strategy initiating the order
        """
        if qty <= 0:
            return {'status': 'rejected', 'reason': 'Quantity must be positive'}
            
        # Apply slippage
        # Buy/Cover: Price increases
        # Sell/Short: Price decreases
        if side in ['buy', 'cover']:
            exec_price = price * (1 + slippage)
        else:
            exec_price = price * (1 - slippage)
            
        # Calculate Commission
        value = qty * exec_price
        commission = value * self.commission_rate
        
        # Determine qty_delta
        if side == 'buy':
            qty_delta = qty
        elif side == 'sell':
            qty_delta = -qty
        elif side == 'short':
            qty_delta = -qty
        elif side == 'cover':
            qty_delta = qty
        else:
             return {'status': 'rejected', 'reason': f'Invalid side: {side}'}
             
        # Check sufficient funds (for opening long) or margin (not fully implemented yet)
        # For simple spot 'sell', check if we have enough qty
        current_pos = self.portfolio.get_position(symbol)
        if side == 'sell':
            if current_pos['qty'] < qty:
                 # Adjust to close remaining? Or reject?
                 # Let's reject for now to be safe
                 return {'status': 'rejected', 'reason': 'Insufficient long position'}
        
        if side == 'cover':
             if current_pos['qty'] > -qty: # Short position is negative. e.g. -10. Cover 5. -10 < -5 is True. Wait.
                 # Pos: -10. Cover 12. New: +2. Flip?
                 # Pos: -10. Cover 5. New: -5.
                 # Logic: abs(current_pos['qty']) < qty
                 pass 
                 # We allow flipping in general, but for now let's assume strategy handles logic.
                 # Broker just executes.
        
        # Update Portfolio
        self.portfolio.update_position(symbol, qty_delta, exec_price, commission)
        
        trade_record = {
            'timestamp': timestamp,
            'status': 'filled',
            'symbol': symbol,
            'side': side,
            'qty': qty,
            'price': exec_price,
            'commission': commission,
            'strategy_id': strategy_id
        }
        self.trades.append(trade_record)
        
        return trade_record
