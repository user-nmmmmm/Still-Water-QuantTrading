from typing import Dict, Optional, Any
import pandas as pd
from core.state import MarketState
from core.portfolio import Portfolio
from core.broker import Broker
from core.risk import RiskManager
from strategies.base import Strategy

class Router:
    def __init__(self, strategies: Dict[str, Strategy], cooldown_bars: int = 3):
        """
        strategies: Dict mapping strategy names to Strategy instances.
        Expected keys: 'TrendUp', 'TrendDown', 'RangeMeanReversion'
        cooldown_bars: Number of bars to wait after a state switch before allowing new entries.
        """
        self.strategies = strategies
        self.cooldown_bars = cooldown_bars
        # Track last state per symbol to detect switches
        self.symbol_states: Dict[str, MarketState] = {}
        # Track cooldown end index per symbol
        self.cooldowns: Dict[str, int] = {}
        
    def route(self, symbol: str, i: int, df: pd.DataFrame, state: MarketState, 
              portfolio: Portfolio, broker: Broker, risk_manager: RiskManager, 
              current_prices: Optional[Dict[str, float]] = None):
        
        # 0. Check Cooldown
        if symbol in self.cooldowns:
            if i <= self.cooldowns[symbol]:
                return # In cooldown, do nothing (we are flat after switch)
            else:
                del self.cooldowns[symbol] # Cooldown expired

        last_state = self.symbol_states.get(symbol)
        
        # 1. Detect Switch
        if last_state is not None and state != last_state:
            self._handle_switch(symbol, i, df, last_state, state, portfolio, broker)
            # Set cooldown
            self.cooldowns[symbol] = i + self.cooldown_bars
            # Update state immediately so next bar knows we already switched
            self.symbol_states[symbol] = state
            return # Skip this bar after switch
            
        self.symbol_states[symbol] = state
        
        # 2. Select Strategy
        strategy_name = self._map_state_to_strategy(state)
        
        # If no strategy mapped (e.g. NO_TRADE), we do nothing (and just exited any old pos)
        if not strategy_name:
            return 
            
        strategy = self.strategies.get(strategy_name)
        if not strategy:
            return
            
        # 3. Execute Strategy
        # Double check if strategy supports this state
        if state in strategy.allowed_states:
            strategy.on_bar(symbol, i, df, state, portfolio, broker, risk_manager, current_prices)

    def _map_state_to_strategy(self, state: MarketState) -> Optional[str]:
        if state == MarketState.TREND_UP:
            return "TrendUp"
        elif state == MarketState.TREND_DOWN:
            return "TrendDown"
        elif state == MarketState.SIDEWAYS:
            return "RangeMeanReversion"
        # NO_TRADE maps to None
        return None

    def _handle_switch(self, symbol: str, i: int, df: pd.DataFrame, 
                       old_state: MarketState, new_state: MarketState, 
                       portfolio: Portfolio, broker: Broker):
        """
        Handle state transition:
        1. Clear context of old strategy
        2. Force close any existing positions for this symbol
        """
        # Identify old strategy to clear its context
        old_strat_name = self._map_state_to_strategy(old_state)
        if old_strat_name and old_strat_name in self.strategies:
            # Manually reset context for this symbol
            # Assuming context is a dict: strategy.context[symbol] = {}
            if symbol in self.strategies[old_strat_name].context:
                self.strategies[old_strat_name].context[symbol] = {}

        # Force Close Position if any
        # This ensures strict mutex: we never hold a 'TrendUp' position when state becomes 'Range'
        pos = portfolio.get_position(symbol)
        qty = pos['qty']
        
        if qty != 0:
            current_price = df['close'].iloc[i]
            timestamp = df.index[i]
            # Use Broker to execute closing order
            # We treat this as a forced system exit
            if qty > 0:
                broker.execute_order(symbol, 'sell', abs(qty), current_price, timestamp=timestamp, strategy_id="Router")
            else:
                broker.execute_order(symbol, 'cover', abs(qty), current_price, timestamp=timestamp, strategy_id="Router")
