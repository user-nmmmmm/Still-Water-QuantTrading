from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
from core.state import MarketState
from core.portfolio import Portfolio
from core.indicators import Indicators
from strategies.base import Strategy


class TrendUpStrategy(Strategy):
    def __init__(
        self,
        sma_period: int = 30,
        sma_fast: int = 10,
        atr_period: int = 14,
        atr_multiplier: float = 2.0,
    ):
        super().__init__("TrendUp", {MarketState.TREND_UP})
        self.sma_period = sma_period
        self.sma_fast = sma_fast
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier

        # Column names
        self.col_sma = f"SMA_{self.sma_period}"
        self.col_sma_fast = f"SMA_{self.sma_fast}"
        self.col_atr = f"ATR_{self.atr_period}"

    def _ensure_indicators(self, df: pd.DataFrame):
        if self.col_sma not in df.columns:
            df[self.col_sma] = Indicators.SMA(df["close"], self.sma_period)
        if self.col_sma_fast not in df.columns:
            df[self.col_sma_fast] = Indicators.SMA(df["close"], self.sma_fast)
        if self.col_atr not in df.columns:
            df[self.col_atr] = Indicators.ATR(df, self.atr_period)

    def should_enter(
        self,
        symbol: str,
        i: int,
        df: pd.DataFrame,
        state: MarketState,
        portfolio: Portfolio,
    ) -> Optional[Dict[str, Any]]:
        self._ensure_indicators(df)

        if i < 1:
            return None

        if pd.isna(df[self.col_sma].iloc[i]) or pd.isna(df[self.col_atr].iloc[i]):
            return None

        close = df["close"].iloc[i]
        sma = df[self.col_sma].iloc[i]
        sma_prev = df[self.col_sma].iloc[i - 1]

        # Conditions
        # 1. Close pull back to SMA (<= 1.005 * SMA)
        cond_pullback = close <= sma * 1.005

        # 2. SMA slope > 0
        slope = sma - sma_prev
        cond_slope = slope > 0

        # 3. SMA_Fast > SMA (Optional)
        sma_fast_val = df[self.col_sma_fast].iloc[i]
        cond_alignment = sma_fast_val > sma

        if cond_pullback and cond_slope and cond_alignment:
            atr = df[self.col_atr].iloc[i]
            stop_loss = close - self.atr_multiplier * atr

            return {
                "action": "buy",
                "stop_loss": stop_loss,
                "order_type": "limit",
                "price": close,
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
        ctx = self.get_context(symbol)

        close = df["close"].iloc[i]
        sma = df[self.col_sma].iloc[i]
        atr = df[self.col_atr].iloc[i]

        # 1. close < SMA
        if close < sma:
            return {"action": "sell", "reason": f"Close below SMA{self.sma_period}"}

        # 2. state != TREND_UP
        if state not in self.allowed_states:
            return {"action": "sell", "reason": "State changed"}

        # 3. Stop/Trail triggered
        stop_loss = ctx.get("stop_loss", -np.inf)
        trailing_stop = ctx.get("trailing_stop", -np.inf)
        effective_stop = max(stop_loss, trailing_stop)

        if close < effective_stop:
            return {"action": "sell", "reason": "Stop/Trail hit"}

        # Update Trailing Stop
        new_trail_candidate = close - self.atr_multiplier * atr
        if new_trail_candidate > trailing_stop:
            ctx["trailing_stop"] = new_trail_candidate

        return None


class TrendDownStrategy(Strategy):
    def __init__(self, sma_period: int = 30, atr_period: int = 14, atr_multiplier: float = 2.0):
        super().__init__("TrendDown", {MarketState.TREND_DOWN})
        self.sma_period = sma_period
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        
        self.col_sma = f"SMA_{self.sma_period}"
        self.col_atr = f"ATR_{self.atr_period}"

    def _ensure_indicators(self, df: pd.DataFrame):
        if self.col_sma not in df.columns:
            df[self.col_sma] = Indicators.SMA(df["close"], self.sma_period)
        if self.col_atr not in df.columns:
            df[self.col_atr] = Indicators.ATR(df, self.atr_period)

    def should_enter(
        self,
        symbol: str,
        i: int,
        df: pd.DataFrame,
        state: MarketState,
        portfolio: Portfolio,
    ) -> Optional[Dict[str, Any]]:
        self._ensure_indicators(df)

        if i < 1:
            return None

        if pd.isna(df[self.col_sma].iloc[i]) or pd.isna(df[self.col_atr].iloc[i]):
            return None

        close = df["close"].iloc[i]
        sma = df[self.col_sma].iloc[i]
        sma_prev = df[self.col_sma].iloc[i - 1]

        # Conditions
        # 1. Close rally to SMA (0.99 * SMA <= close <= SMA)
        cond_rally = (close >= sma * 0.99) and (close <= sma)

        # 2. SMA slope < 0
        slope = sma - sma_prev
        cond_slope = slope < 0

        if cond_rally and cond_slope:
            atr = df[self.col_atr].iloc[i]
            stop_loss = close + self.atr_multiplier * atr

            return {
                "action": "short",
                "stop_loss": stop_loss,
                "order_type": "limit",
                "price": close,
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
        ctx = self.get_context(symbol)

        close = df["close"].iloc[i]
        sma = df[self.col_sma].iloc[i]
        atr = df[self.col_atr].iloc[i]

        # 1. close > SMA * 1.005
        if close > sma * 1.005:
            return {"action": "cover", "reason": f"Close above SMA{self.sma_period}"}

        # 2. state != TREND_DOWN
        if state not in self.allowed_states:
            return {"action": "cover", "reason": "State changed"}

        # 3. Stop/Trail triggered
        stop_loss = ctx.get("stop_loss", np.inf)
        trailing_stop = ctx.get("trailing_stop", np.inf)
        effective_stop = min(stop_loss, trailing_stop)

        if close > effective_stop:
            return {"action": "cover", "reason": "Stop/Trail hit"}

        # Update Trailing Stop for Short
        new_trail_candidate = close + self.atr_multiplier * atr

        if new_trail_candidate < trailing_stop:
            ctx["trailing_stop"] = new_trail_candidate

        return None
