from typing import Dict, Optional, Any
import pandas as pd
from core.state import MarketState
from core.portfolio import Portfolio
from core.broker import Broker
from core.risk import RiskManager
from strategies.base import Strategy

class Router:
    def __init__(self, strategies: Dict[str, Strategy], regime_map: Dict[str, str] = None, cooldown_bars: int = 3, log_path: str = None):
        """
        strategies: Dict mapping strategy names to Strategy instances.
        regime_map: Dict mapping MarketState names (str) to Strategy names (str).
        cooldown_bars: Number of bars to wait after a state switch before allowing new entries.
        log_path: Path to save routing log CSV.
        """
        self.strategies = strategies
        self.cooldown_bars = cooldown_bars
        self.regime_map = regime_map or {
            "TREND_UP": "TrendUp",
            "TREND_DOWN": "TrendDown",
            "SIDEWAYS": "RangeMeanReversion",
            "VOLATILE": "Cash"
        }
        self.log_path = log_path
        
        # Track last state per symbol to detect switches
        self.symbol_states: Dict[str, MarketState] = {}
        # Track cooldown end index per symbol
        self.cooldowns: Dict[str, int] = {}
        
        # Log buffer
        self.log_buffer = []

    def route(self, symbol: str, i: int, df: pd.DataFrame, state: MarketState, 
              portfolio: Portfolio, broker: Broker, risk_manager: RiskManager, 
              current_prices: Optional[Dict[str, float]] = None):
        
        current_time = df.index[i]
        
        # 0. Check Cooldown
        in_cooldown = False
        if symbol in self.cooldowns:
            if i <= self.cooldowns[symbol]:
                in_cooldown = True
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
            
            # Log switch
            self._log_routing(current_time, symbol, state.name, "SWITCH_COOLDOWN", 0.0)
            return # Skip this bar after switch
            
        self.symbol_states[symbol] = state
        
        if in_cooldown:
            self._log_routing(current_time, symbol, state.name, "COOLDOWN", 0.0)
            return

        # 2. Select Strategy
        strategy_name = self._map_state_to_strategy(state)
        
        # If no strategy mapped (e.g. NO_TRADE), we do nothing (and just exited any old pos)
        if not strategy_name or strategy_name == "Cash":
            self._log_routing(current_time, symbol, state.name, "CASH", 0.0)
            return 
            
        strategy = self.strategies.get(strategy_name)
        if not strategy:
            self._log_routing(current_time, symbol, state.name, "MISSING_STRATEGY", 0.0)
            return
            
        # 3. Execute Strategy
        # Double check if strategy supports this state
        if state in strategy.allowed_states:
            # We don't easily know target weight here unless strategy returns it. 
            # Currently strategies execute directly.
            # We'll log "ACTIVE" for now.
            
            # TODO: Refactor strategy to return signals/weights for better logging.
            # For now, just logging that we routed to it.
            pos = portfolio.get_position(symbol)
            current_qty = pos['qty']
            self._log_routing(current_time, symbol, state.name, strategy_name, current_qty)
            
            strategy.on_bar(symbol, i, df, state, portfolio, broker, risk_manager, current_prices)

    def _map_state_to_strategy(self, state: MarketState) -> Optional[str]:
        # state is an Enum, state.name is string e.g. "TREND_UP"
        return self.regime_map.get(state.name)

    def _log_routing(self, timestamp, symbol, regime, strategy, qty):
        if self.log_path:
            self.log_buffer.append({
                "timestamp": timestamp,
                "symbol": symbol,
                "regime": regime,
                "strategy": strategy,
                "current_qty": qty
            })
            
            # Flush periodically or just let it grow? 
            # For backtest, memory is usually fine. But let's verify.
            
    def save_log(self):
        if self.log_path and self.log_buffer:
            df = pd.DataFrame(self.log_buffer)
            df.to_csv(self.log_path, index=False)

    def _handle_switch(self, symbol: str, i: int, df: pd.DataFrame,
                       old_state: MarketState, new_state: MarketState,
                       portfolio: Portfolio, broker: Broker):
        """
        Handle state transition:
        1. Cancel all pending/active broker orders for this symbol (prevents zombie fills)
        2. Clear context of old strategy
        3. Force close any existing positions for this symbol
        """
        # Cancel stale limit/stop orders BEFORE closing the position.
        # Without this, an unfilled LIMIT buy from the old regime could fill later
        # with no stop-loss context attached (context was already cleared).
        broker.cancel_symbol_orders(symbol)

        # Identify old strategy to clear its context
        old_strat_name = self._map_state_to_strategy(old_state)
        if old_strat_name and old_strat_name in self.strategies:
            if symbol in self.strategies[old_strat_name].context:
                self.strategies[old_strat_name].context[symbol] = {}

        # Force Close Position if any
        # This ensures strict mutex: we never hold a 'TrendUp' position when state becomes 'Range'
        pos = portfolio.get_position(symbol)
        qty = pos['qty']

        if qty != 0:
            current_price = df['close'].iloc[i]
            timestamp = df.index[i]
            if qty > 0:
                broker.submit_order(symbol, 'sell', abs(qty), current_price, timestamp=timestamp, strategy_id="Router", exit_reason="StateSwitch")
            elif qty < 0:
                broker.submit_order(symbol, 'cover', abs(qty), current_price, timestamp=timestamp, strategy_id="Router", exit_reason="StateSwitch")
