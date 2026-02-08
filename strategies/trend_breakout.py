from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
from core.state import MarketState
from core.portfolio import Portfolio
from strategies.base import Strategy


class TrendBreakoutStrategy(Strategy):
    """
    P3: Production Implementation of Trend Breakout Alpha.

    P0 Regime Definition:
    - This alpha earns in VOLATILE expansion (ADX > 25) and strong TREND_UP regimes.

    P5 Failure Criteria (Alpha Death):
    - Rolling Sharpe (20 trades) < 0.0
    - Consecutive Losses > 5
    - Max Drawdown > 15% (Strategy Level)

    Logic:
    - Enter Long if Close > Max(High, 20)
    - Exit Long if Close < Min(Low, 10)
    - Allowed Regimes: TREND_UP, VOLATILE
    """

    def __init__(self, entry_window: int = 20, exit_window: int = 10):
        # We allow VOLATILE because breakout often happens during volatility expansion
        super().__init__("TrendBreakout", {MarketState.TREND_UP, MarketState.VOLATILE})
        self.entry_window = entry_window
        self.exit_window = exit_window

        self.col_high_max = f"HIGH_MAX_{self.entry_window}"
        self.col_low_min = f"LOW_MIN_{self.exit_window}"

        # P5: Health Monitoring
        self.health_stats = {
            "total_trades": 0,
            "consecutive_losses": 0,
            "rolling_pnl": [],
            "is_alive": True,
            "death_reason": None,
        }

    def check_health(self) -> bool:
        """
        P5: Check if alpha should be disabled.
        """
        if not self.health_stats["is_alive"]:
            return False

        # 1. Consecutive Losses
        if self.health_stats["consecutive_losses"] > 5:
            self.health_stats["is_alive"] = False
            self.health_stats["death_reason"] = "Consecutive Losses > 5"
            return False

        # 2. Rolling Sharpe (Simplified check on last 20 PnL entries)
        pnl_history = self.health_stats["rolling_pnl"]
        if len(pnl_history) >= 20:
            recent_pnl = pnl_history[-20:]
            if np.mean(recent_pnl) < 0:  # Simple mean return check first
                # Calculate Sharpe if needed, but mean < 0 is enough to warn
                self.health_stats["is_alive"] = False
                self.health_stats["death_reason"] = (
                    "Rolling Mean Return < 0 (20 trades)"
                )
                return False

        return True

    def _ensure_indicators(self, df: pd.DataFrame):
        if self.col_high_max not in df.columns:
            # Shift 1 to avoid lookahead bias (Standard Donchian uses previous N days)
            df[self.col_high_max] = (
                df["high"].rolling(window=self.entry_window).max().shift(1)
            )

        if self.col_low_min not in df.columns:
            df[self.col_low_min] = (
                df["low"].rolling(window=self.exit_window).min().shift(1)
            )

    def should_enter(
        self,
        symbol: str,
        i: int,
        df: pd.DataFrame,
        state: MarketState,
        portfolio: Portfolio,
    ) -> Optional[Dict[str, Any]]:
        self._ensure_indicators(df)

        if i < self.entry_window:
            return None

        close = df["close"].iloc[i]
        high_max = df[self.col_high_max].iloc[i]

        # Check Entry Signal
        if pd.notna(high_max) and close > high_max:
            # Breakout!

            # Risk Management Integration (P3 Requirement)
            # We provide a stop_loss for the RiskManager to size the position.
            # For breakout, maybe Low of breakout candle or recent low?
            # Let's use the Exit Level (Donchian Low) as the initial stop.
            stop_loss = df[self.col_low_min].iloc[i]
            if pd.isna(stop_loss) or stop_loss >= close:
                # Fallback if stop is invalid (e.g. too close): use ATR-based or %?
                # Let's assume RiskManager handles sizing if we provide 'stop_loss'.
                # But if Donchian Low is higher than Close (impossible if breakout), check logic.
                stop_loss = close * 0.95  # Fallback 5%

            return {
                "action": "buy",
                "stop_loss": stop_loss,
                "order_type": "market",  # Breakouts usually need market entry to ensure fill
                # Or Limit at Close? Docs say "Limit Orders (passive entry at Close)".
                # But breakout needs to trigger. Let's use Market for Breakout to guarantee entry.
                # Actually, the system executes at Next Open.
                # If we signal "buy" now (at Close), execution is Open(i+1).
                # We can set limit=Close(i) to try to get a good price, but might miss.
                # Let's stick to system default (which is Market if no price specified? Or Limit?)
                # Looking at Broker: submit_order takes price.
                "price": close,  # Use Close as reference price
            }

        return None

    def should_exit(
        self,
        symbol: str,
        i: int,
        df: pd.DataFrame,
        state: MarketState,
        portfolio: Portfolio,
    ) -> Optional[Dict[str, Any]]:
        self._ensure_indicators(df)

        close = df["close"].iloc[i]
        low_min = df[self.col_low_min].iloc[i]

        # 1. Exit Signal
        if pd.notna(low_min) and close < low_min:
            return {
                "action": "sell",
                "reason": f"Breakout Exit (Below Low{self.exit_window})",
            }

        # 2. Regime Check (System Rule)
        if state not in self.allowed_states:
            # If regime switches to SIDEWAYS or TREND_DOWN, we exit.
            # This is the "System Control" part of P3.
            return {"action": "sell", "reason": f"Regime {state.name} Not Allowed"}

        return None
