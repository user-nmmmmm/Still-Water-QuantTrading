from abc import ABC, abstractmethod
from typing import Set, Dict, Any, Optional
import pandas as pd
import numpy as np
from core.state import MarketState
from core.portfolio import Portfolio
from core.broker import Broker
from core.risk import RiskManager

class Strategy(ABC):
    def __init__(self, name: str, allowed_states: Set[MarketState]):
        self.name = name
        self.allowed_states = allowed_states
        
        # State tracking for the strategy per symbol
        # symbol -> { 'entry_price': float, 'stop_loss': float, 'trailing_stop': float }
        self.context: Dict[str, Dict[str, Any]] = {}

    def get_context(self, symbol: str) -> Dict[str, Any]:
        if symbol not in self.context:
            self.context[symbol] = {}
        return self.context[symbol]

    @abstractmethod
    def should_enter(self, symbol: str, i: int, df: pd.DataFrame, state: MarketState, portfolio: Portfolio) -> Optional[Dict[str, Any]]:
        """
        Return entry signal. 
        e.g. {'action': 'buy'|'short', 'stop_loss': float}
        """
        pass

    @abstractmethod
    def should_exit(self, symbol: str, i: int, df: pd.DataFrame, state: MarketState, portfolio: Portfolio) -> Optional[Dict[str, Any]]:
        """
        Return exit signal. 
        e.g. {'action': 'sell'|'cover', 'reason': str}
        """
        pass

    def on_bar(self, symbol: str, i: int, df: pd.DataFrame, state: MarketState, portfolio: Portfolio, broker: Broker, risk_manager: RiskManager, current_prices: Optional[Dict[str, float]] = None):
        """
        Standard execution flow.
        """
        current_pos = portfolio.get_position(symbol)
        qty = current_pos['qty']
        
        # 1. Check Exit if we have a position
        if qty != 0:
            exit_signal = self.should_exit(symbol, i, df, state, portfolio)
            if exit_signal:
                action = exit_signal['action'] # 'sell' or 'cover'
                reason = exit_signal.get('reason', 'signal')
                
                # Execute Exit
                # Calculate qty to close (all)
                close_qty = abs(qty)
                current_price = df['close'].iloc[i]
                
                # If action matches position direction (sell for long, cover for short)
                if (qty > 0 and action == 'sell') or (qty < 0 and action == 'cover'):
                    timestamp = df.index[i]
                    broker.submit_order(symbol, action, close_qty, current_price, timestamp=timestamp, strategy_id=self.name, exit_reason=reason)
                    
                    # Clear context (Optimistic)
                    self.context[symbol] = {}
                        
        # 2. Check Entry if we don't have a position (or if strategy allows pyramiding, but let's assume 1 pos for now)
        if qty == 0:
            if state in self.allowed_states:
                entry_signal = self.should_enter(symbol, i, df, state, portfolio)
                if entry_signal:
                    action = entry_signal['action'] # 'buy' or 'short'
                    stop_loss = entry_signal.get('stop_loss', 0.0)
                    current_price = df['close'].iloc[i]
                    
                    # Calculate Position Size
                    # Use current_prices if available, else fallback to just this symbol
                    price_map = current_prices if current_prices else {symbol: current_price}
                    equity = portfolio.get_equity(price_map)
                    
                    # Check Leverage Limit (Max 3x)
                    total_exposure = portfolio.get_total_exposure(price_map)
                    # We are about to add: size * current_price
                    # But we don't know size yet.
                    
                    size = risk_manager.calculate_position_size(equity, current_price, stop_loss)
                    
                    if size > 0:
                        new_exposure = size * current_price
                        projected_leverage = (total_exposure + new_exposure) / equity
                        
                        if projected_leverage > 3.0:
                            # Reduce size to fit leverage? Or just Reject?
                            # Let's reject for safety or cap it.
                            # Cap it: max_new_exposure = (3 * equity) - total_exposure
                            max_new_exposure = (3.0 * equity) - total_exposure
                            if max_new_exposure <= 0:
                                return # Cannot open
                            
                            max_size = max_new_exposure / current_price
                            size = min(size, max_size)
                        
                        timestamp = df.index[i]
                        broker.submit_order(symbol, action, size, current_price, timestamp=timestamp, strategy_id=self.name, exit_reason='signal')
                        
                        # Initialize Context
                        self.context[symbol] = {
                            'stop_loss': stop_loss,
                            'entry_price': current_price, # Approx
                            'trailing_stop': -np.inf if action == 'buy' else np.inf # Init trail
                        }
