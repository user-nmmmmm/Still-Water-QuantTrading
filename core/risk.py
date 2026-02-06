class RiskManager:
    def __init__(self, risk_per_trade: float = 0.01):
        self.risk_per_trade = risk_per_trade

    def calculate_position_size(self, equity: float, entry_price: float, stop_loss_price: float) -> float:
        """
        Calculate position size based on fixed risk percentage.
        Qty = (Equity * Risk%) / |Entry - Stop|
        """
        if entry_price <= 0 or stop_loss_price <= 0:
            return 0.0
            
        risk_amount = equity * self.risk_per_trade
        price_diff = abs(entry_price - stop_loss_price)
        
        if price_diff == 0:
            return 0.0
            
        qty = risk_amount / price_diff
        return qty
