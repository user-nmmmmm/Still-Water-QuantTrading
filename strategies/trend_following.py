from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
from core.state import MarketState
from core.portfolio import Portfolio
from core.indicators import Indicators
from strategies.base import Strategy


class TrendUpStrategy(Strategy):
    def __init__(self):
        super().__init__("TrendUp", {MarketState.TREND_UP})

    def _ensure_indicators(self, df: pd.DataFrame):
        # We need to check if indicators exist.
        # Note: If df is a slice or view, this might warn, but here we assume it's the main df.
        # Also, checking specific columns.
        if "SMA_30" not in df.columns:
            df["SMA_30"] = Indicators.SMA(df["close"], 30)
        if "SMA_10" not in df.columns:
            df["SMA_10"] = Indicators.SMA(df["close"], 10)
        if "ATR_14" not in df.columns:
            df["ATR_14"] = Indicators.ATR(df, 14)

    def should_enter(
        self,
        symbol: str,
        i: int,
        df: pd.DataFrame,
        state: MarketState,
        portfolio: Portfolio,
    ) -> Optional[Dict[str, Any]]:
        self._ensure_indicators(df)

        # Ensure we have enough history for i-1
        if i < 1:
            return None

        # Check if indicators are valid at i
        if pd.isna(df["SMA_30"].iloc[i]) or pd.isna(df["ATR_14"].iloc[i]):
            return None

        close = df["close"].iloc[i]
        sma30 = df["SMA_30"].iloc[i]
        sma30_prev = df["SMA_30"].iloc[i - 1]

        # Conditions
        # 1. Close pull back to SMA30 (<= 1.005 * SMA30)
        cond_pullback = close <= sma30 * 1.005

        # 2. SMA30 slope > 0
        slope = sma30 - sma30_prev
        cond_slope = slope > 0

        # 3. SMA10 > SMA30 (Optional)
        sma10 = df["SMA_10"].iloc[i]
        cond_alignment = sma10 > sma30

        if cond_pullback and cond_slope and cond_alignment:
            atr = df["ATR_14"].iloc[i]
            stop_loss = close - 2 * atr
            return {"action": "buy", "stop_loss": stop_loss}

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
        sma30 = df["SMA_30"].iloc[i]
        atr = df["ATR_14"].iloc[i]

        # Check Exit Conditions FIRST (using previous trail)

        # 1. close < SMA30
        if close < sma30:
            return {"action": "sell", "reason": "Close below SMA30"}

        # 2. state != TREND_UP
        if state not in self.allowed_states:
            return {"action": "sell", "reason": "State changed"}

        # 3. Stop/Trail triggered
        # Check against stop_loss (initial) and trailing_stop (from previous bar)
        stop_loss = ctx.get("stop_loss", -np.inf)
        trailing_stop = ctx.get("trailing_stop", -np.inf)
        effective_stop = max(stop_loss, trailing_stop)

        if close < effective_stop:
            return {"action": "sell", "reason": "Stop/Trail hit"}

        # Update Trailing Stop (for NEXT bar)
        # trail = max(trail, close - 2*ATR)
        # Logic: new_trail_candidate = close - 2*ATR.
        # if new_trail_candidate > current_trail: current_trail = new_trail_candidate

        new_trail_candidate = close - 2 * atr
        if new_trail_candidate > trailing_stop:
            ctx["trailing_stop"] = new_trail_candidate

        return None


class TrendDownStrategy(Strategy):
    def __init__(self):
        super().__init__("TrendDown", {MarketState.TREND_DOWN})

    def _ensure_indicators(self, df: pd.DataFrame):
        if "SMA_30" not in df.columns:
            df["SMA_30"] = Indicators.SMA(df["close"], 30)
        if "ATR_14" not in df.columns:
            df["ATR_14"] = Indicators.ATR(df, 14)

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

        if pd.isna(df["SMA_30"].iloc[i]) or pd.isna(df["ATR_14"].iloc[i]):
            return None

        close = df["close"].iloc[i]
        sma30 = df["SMA_30"].iloc[i]
        sma30_prev = df["SMA_30"].iloc[i - 1]

        # Conditions
        # 1. Close rally to SMA30 (0.99 * SMA30 <= close <= SMA30)
        # We want a pullback (rally) that gets close to SMA30 from below.
        cond_rally = (close >= sma30 * 0.99) and (close <= sma30)

        # 2. SMA30 slope < 0
        slope = sma30 - sma30_prev
        cond_slope = slope < 0

        if cond_rally and cond_slope:
            atr = df["ATR_14"].iloc[i]
            stop_loss = close + 2 * atr
            return {"action": "short", "stop_loss": stop_loss}

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
        sma30 = df["SMA_30"].iloc[i]
        atr = df["ATR_14"].iloc[i]

        # Check Exit Conditions FIRST (using previous trail)

        # 1. close > SMA30 * 1.005 (Buffer to avoid noise)
        if close > sma30 * 1.005:
            return {"action": "cover", "reason": "Close above SMA30"}

        # 2. state != TREND_DOWN
        if state not in self.allowed_states:
            return {"action": "cover", "reason": "State changed"}

        # 3. Stop/Trail triggered
        stop_loss = ctx.get("stop_loss", np.inf)
        trailing_stop = ctx.get("trailing_stop", np.inf)
        effective_stop = min(stop_loss, trailing_stop)

        if close > effective_stop:
            return {"action": "cover", "reason": "Stop/Trail hit"}

        # Update Trailing Stop for Short (for NEXT bar)
        # Trail only goes DOWN.
        # trail = min(trail, close + 2*ATR)

        new_trail_candidate = close + 2 * atr

        if new_trail_candidate < trailing_stop:
            ctx["trailing_stop"] = new_trail_candidate

        return None
