import logging
from typing import Optional, Dict
from core.portfolio import Portfolio

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(
        self, 
        risk_per_trade: float = 0.01,
        max_leverage: float = 3.0,
        max_drawdown_limit: float = 0.20,
        liquidity_limit_pct: float = 0.01, # Max 1% of bar volume
        max_pos_size_pct: float = 0.20 # Max 20% equity per position
    ):
        self.risk_per_trade = risk_per_trade
        self.max_leverage = max_leverage
        self.max_drawdown_limit = max_drawdown_limit
        self.liquidity_limit_pct = liquidity_limit_pct
        self.max_pos_size_pct = max_pos_size_pct
        
        self.circuit_breaker_triggered = False

    def calculate_position_size(self, equity: float, entry_price: float, stop_loss_price: float) -> float:
        """
        Calculate position size based on fixed risk percentage of equity.
        Qty = (Equity * Risk%) / |Entry - Stop|
        """
        if self.circuit_breaker_triggered:
            return 0.0

        if entry_price <= 0 or stop_loss_price <= 0:
            return 0.0
            
        risk_amount = equity * self.risk_per_trade
        price_diff = abs(entry_price - stop_loss_price)
        
        if price_diff == 0:
            return 0.0
            
        qty = risk_amount / price_diff
        return qty

    def calculate_position_size_fixed_pct(self, equity: float, entry_price: float, pct: float = 0.10) -> float:
        """
        Calculate position size based on fixed percentage of equity.
        Qty = (Equity * Pct) / Entry
        """
        if self.circuit_breaker_triggered:
            return 0.0
            
        if entry_price <= 0:
            return 0.0
            
        allocation = equity * pct
        return allocation / entry_price

    def check_entry_risk(
        self, 
        portfolio: Portfolio, 
        symbol: str, 
        qty: float, 
        price: float,
        current_volume: float = 0,
        current_prices: Optional[Dict[str, float]] = None
    ) -> bool:
        """
        Check if the proposed trade violates any risk limits.
        Returns True if safe, False if rejected.
        """
        if self.circuit_breaker_triggered:
            logger.warning("Trade Rejected: Circuit Breaker Active")
            return False

        if qty <= 0 or price <= 0:
            return False
            
        # 1. Liquidity Check
        if current_volume > 0:
            max_qty = current_volume * self.liquidity_limit_pct
            if qty > max_qty:
                logger.warning(f"Trade Rejected: Liquidity Limit. Qty {qty:.4f} > Max {max_qty:.4f} (1% of {current_volume})")
                return False
                
        # 2. Leverage Check
        # Estimate new exposure
        trade_value = qty * price
        
        # Current exposure
        if current_prices is None:
            current_exposure = portfolio.get_total_exposure({}) 
            current_equity = portfolio.get_total_value({})
        else:
            current_exposure = portfolio.get_total_exposure(current_prices)
            current_equity = portfolio.get_total_value(current_prices)
            
        if current_equity <= 0:
            return False
            
        new_exposure = current_exposure + trade_value
        projected_leverage = new_exposure / current_equity
        
        if projected_leverage > self.max_leverage:
            logger.warning(f"Trade Rejected: Leverage Limit. Projected {projected_leverage:.2f} > Max {self.max_leverage}")
            return False

        # 3. Concentration Check (Max Position Size)
        # Check if adding this trade makes this single position too large
        current_pos = portfolio.get_position(symbol)
        current_pos_value = abs(current_pos['qty']) * price # Approximate current value
        new_pos_value = current_pos_value + trade_value
        
        if new_pos_value > (current_equity * self.max_pos_size_pct):
            logger.warning(f"Trade Rejected: Concentration Limit. Symbol {symbol} would be {new_pos_value/current_equity:.1%} > Max {self.max_pos_size_pct:.1%}")
            return False
            
        return True

    def check_circuit_breaker(self, current_equity: float, daily_start_equity: float) -> bool:
        """
        Check intraday drawdown.
        If current_equity < daily_start_equity * (1 - limit), trigger breaker.
        """
        if self.circuit_breaker_triggered:
            return True # Already triggered

        if daily_start_equity <= 0:
            return False

        drawdown = 1 - (current_equity / daily_start_equity)
        
        if drawdown > self.max_drawdown_limit:
            self.circuit_breaker_triggered = True
            print(f"!!! CIRCUIT BREAKER TRIGGERED !!! Intraday Drawdown {drawdown*100:.2f}% > Limit {self.max_drawdown_limit*100:.2f}%")
            return True
            
        return False
