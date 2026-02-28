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
    def should_enter(
        self,
        symbol: str,
        i: int,
        df: pd.DataFrame,
        state: MarketState,
        portfolio: Portfolio,
    ) -> Optional[Dict[str, Any]]:
        """
        Return entry signal.
        e.g. {'action': 'buy'|'short', 'stop_loss': float}
        """
        pass

    @abstractmethod
    def should_exit(
        self,
        symbol: str,
        i: int,
        df: pd.DataFrame,
        state: MarketState,
        portfolio: Portfolio,
    ) -> Optional[Dict[str, Any]]:
        """
        Return exit signal.
        e.g. {'action': 'sell'|'cover', 'reason': str}
        """
        pass

    def on_bar(
        self,
        symbol: str,
        i: int,
        df: pd.DataFrame,
        state: MarketState,
        portfolio: Portfolio,
        broker: Broker,
        risk_manager: RiskManager,
        current_prices: Optional[Dict[str, float]] = None,
    ):
        """
        Standard execution flow.
        """
        current_pos = portfolio.get_position(symbol)
        qty = current_pos["qty"]

        # 1. Check Exit if we have a position
        # Skip exit check on the bar immediately after entry to avoid same-bar entry-exit churn:
        # Entry order is submitted at bar N, fills at bar N+1 open, then on_bar runs at bar N+1.
        # We must not check exit at bar N+1 for a freshly opened position.
        ctx_pre = self.get_context(symbol)
        just_entered = i <= ctx_pre.get("entry_bar", -2) + 1

        if qty != 0 and not just_entered:
            exit_signal = self.should_exit(symbol, i, df, state, portfolio)
            if exit_signal:
                action = exit_signal["action"]  # 'sell' or 'cover'
                reason = exit_signal.get("reason", "signal")

                # Execute Exit
                # Calculate qty to close (all)
                close_qty = abs(qty)
                current_price = df["close"].iloc[i]

                # Extract optional order parameters
                order_type = exit_signal.get("order_type", "market")
                order_price = exit_signal.get("price", current_price)

                # If action matches position direction (sell for long, cover for short)
                if (qty > 0 and action == "sell") or (qty < 0 and action == "cover"):
                    timestamp = df.index[i]
                    broker.submit_order(
                        symbol,
                        action,
                        close_qty,
                        price=order_price,
                        order_type=order_type,
                        timestamp=timestamp,
                        strategy_id=self.name,
                        exit_reason=reason,
                    )

                    # Clear context (Optimistic)
                    self.context[symbol] = {}

        # 2. Check Entry if we don't have a position (or if strategy allows pyramiding, but let's assume 1 pos for now)
        if qty == 0:
            if state in self.allowed_states:
                entry_signal = self.should_enter(symbol, i, df, state, portfolio)
                if entry_signal:
                    action = entry_signal["action"]  # 'buy' or 'short'
                    stop_loss = entry_signal.get("stop_loss", 0.0)
                    current_price = df["close"].iloc[i]

                    # Extract optional order parameters
                    order_type = entry_signal.get("order_type", "market")
                    order_price = entry_signal.get("price", current_price)

                    # Calculate Position Size
                    # Use current_prices if available, else fallback to just this symbol
                    price_map = (
                        current_prices if current_prices else {symbol: current_price}
                    )
                    equity = portfolio.get_equity(price_map)

                    # Check Leverage Limit (Max 3x)
                    total_exposure = portfolio.get_total_exposure(price_map)
                    # We are about to add: size * current_price
                    # But we don't know size yet.

                    if stop_loss > 0:
                        size = risk_manager.calculate_position_size(
                            equity, current_price, stop_loss
                        )
                    else:
                        # Fallback: Use Fixed Percentage (e.g. 10% of Equity)
                        size = risk_manager.calculate_position_size_fixed_pct(
                            equity, current_price, pct=0.10
                        )

                    if size > 0:
                        # Pre-trade Risk Check
                        if risk_manager.check_entry_risk(
                            portfolio,
                            symbol,
                            size,
                            current_price,
                            current_volume=0,
                            current_prices=price_map,
                        ):
                            broker.submit_order(
                                symbol,
                                action,
                                size,
                                price=order_price,
                                order_type=order_type,
                                timestamp=df.index[i],
                                strategy_id=self.name,
                                # stop_loss is not passed to submit_order currently in Broker signature?
                                # Let's check Broker signature. It accepts strategy_id, exit_reason.
                                # It does NOT accept stop_loss.
                                # But we can store it in context.
                                exit_reason="signal",
                            )

                            # Initialize Context
                            self.context[symbol] = {
                                "stop_loss": stop_loss,
                                "entry_price": current_price,  # Approx
                                "trailing_stop": -np.inf
                                if action == "buy"
                                else np.inf,  # Init trail
                                "entry_bar": i,  # Track bar to prevent same-bar exit
                            }
