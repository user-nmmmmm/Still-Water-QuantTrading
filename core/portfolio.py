from typing import Dict, Optional

class Portfolio:
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        # positions: symbol -> {'qty': float, 'avg_price': float}
        self.positions: Dict[str, Dict[str, float]] = {}
        
    def get_position(self, symbol: str) -> Dict[str, float]:
        return self.positions.get(symbol, {'qty': 0.0, 'avg_price': 0.0})
        
    def update_position(self, symbol: str, qty_delta: float, price: float, fee: float = 0.0):
        """
        Update position for a symbol.
        qty_delta: + for buy/cover, - for sell/short (technically 'buy' is +qty, 'sell' is -qty)
        But wait, if we distinguish buy/sell/short/cover:
        - Buy: qty_delta > 0
        - Sell: qty_delta < 0
        - Short: qty_delta < 0 (opening short)
        - Cover: qty_delta > 0 (closing short)
        
        It's simpler to just track signed quantity.
        Long: qty > 0. Short: qty < 0.
        """
        self.cash -= fee
        
        current_pos = self.get_position(symbol)
        old_qty = current_pos['qty']
        new_qty = old_qty + qty_delta
        
        # Calculate cost basis / cash flow
        # Cash change = - (qty_delta * price)
        cost = qty_delta * price
        self.cash -= cost
        
        # Update avg_price if opening/increasing position
        # If going from 0 to + (Long)
        # If going from + to ++ (Add Long)
        # If going from 0 to - (Short)
        # If going from - to -- (Add Short)
        
        is_opening = False
        if old_qty == 0 and new_qty != 0:
            is_opening = True
        elif old_qty > 0 and new_qty > old_qty: # Increasing Long
            is_opening = True
        elif old_qty < 0 and new_qty < old_qty: # Increasing Short
            is_opening = True
            
        if is_opening:
            # Weighted average price
            total_value = (abs(old_qty) * current_pos['avg_price']) + (abs(qty_delta) * price)
            new_avg_price = total_value / abs(new_qty)
            self.positions[symbol] = {'qty': new_qty, 'avg_price': new_avg_price}
        else:
            # Closing/Reducing: Avg price doesn't change, just realize PnL (implicitly via cash)
            if new_qty == 0:
                if symbol in self.positions:
                    del self.positions[symbol]
            else:
                self.positions[symbol]['qty'] = new_qty
                # avg_price remains same
                
    def get_equity(self, current_prices: Dict[str, float]) -> float:
        equity = self.cash
        for symbol, pos in self.positions.items():
            qty = pos['qty']
            price = current_prices.get(symbol, pos['avg_price']) # Fallback to avg_price if no current price
            equity += qty * price
        return equity

    def get_total_value(self, current_prices: Dict[str, float]) -> float:
        """Alias for get_equity"""
        return self.get_equity(current_prices)

    def get_total_exposure(self, current_prices: Dict[str, float]) -> float:
        exposure = 0.0
        for symbol, pos in self.positions.items():
            qty = abs(pos['qty'])
            price = current_prices.get(symbol, pos['avg_price'])
            exposure += qty * price
        return exposure
