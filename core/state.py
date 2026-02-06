from enum import Enum
import pandas as pd
import numpy as np
from core.indicators import Indicators

class MarketState(Enum):
    TREND_UP = 1
    TREND_DOWN = 2
    SIDEWAYS = 3
    NO_TRADE = 4 # 模糊阶段，短期全部禁用

class MarketStateMachine:
    def __init__(self, stability_period: int = 3):
        self.stability_period = stability_period

    def get_state(self, df: pd.DataFrame, i: int) -> MarketState:
        """
        Get state for a specific bar index i.
        Ideally we compute states for the whole dataframe first, or cache it.
        For simplicity, if indicators are pre-calculated, we can compute on the fly.
        But stability filter requires history.
        So we should use 'get_states' (plural) to compute the whole series, 
        or rely on the Engine to call get_states once and pass the result.
        
        However, Engine calls `get_state(df, i)`.
        If we want stability, we must look back.
        """
        # Engine calls this inside a loop. 
        # If we calculate valid states for the whole DF once, it's efficient.
        # But 'get_state(df, i)' implies lookup.
        # Let's assume 'df' has a 'state' column if we pre-calculated?
        # Or we calculate it here looking back?
        
        # Let's implement `calculate_states(df)` and let Engine call it or 
        # let `get_state` compute it if not present.
        
        # Check if 'market_state' column exists
        if 'market_state' in df.columns:
            return df['market_state'].iloc[i]
            
        # If not, maybe we should calculate it for the whole DF now?
        # This might happen once per symbol.
        states = self.calculate_states(df)
        df['market_state'] = states
        return states.iloc[i]

    def calculate_states(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate Market State for the entire DataFrame.
        Rules:
        - TREND_UP: Close > SMA(30) & SMA(30) slope > 0
        - TREND_DOWN: Close < SMA(30) & SMA(30) slope < 0
        - SIDEWAYS: Else
        """
        # Ensure Indicators are present
        if 'SMA_30' not in df.columns:
            Indicators.calculate_all(df)
            
        close = df['close']
        sma30 = df['SMA_30']
        
        # Calculate Slope of SMA30
        # Slope = current - prev
        sma30_slope = sma30.diff()
        
        # Raw States
        raw_states = pd.Series(MarketState.SIDEWAYS, index=df.index)
        
        # TREND_UP
        up_cond = (close > sma30) & (sma30_slope > 0)
        raw_states[up_cond] = MarketState.TREND_UP
        
        # TREND_DOWN
        down_cond = (close < sma30) & (sma30_slope < 0)
        raw_states[down_cond] = MarketState.TREND_DOWN
        
        # Stability Filter
        return self._apply_stability_filter(raw_states)

    def _apply_stability_filter(self, raw_states: pd.Series) -> pd.Series:
        if len(raw_states) == 0:
            return raw_states

        stable_states = []
        current_stable = MarketState.SIDEWAYS
        
        consecutive_count = 0
        candidate_state = None
        
        for state in raw_states:
            if state == current_stable:
                consecutive_count = 0
                candidate_state = None
            else:
                if state == candidate_state:
                    consecutive_count += 1
                else:
                    candidate_state = state
                    consecutive_count = 1
                
                if consecutive_count >= self.stability_period:
                    current_stable = candidate_state
                    consecutive_count = 0
                    candidate_state = None
            
            stable_states.append(current_stable)
            
        return pd.Series(stable_states, index=raw_states.index)

    @staticmethod
    def align_state_to_lower_tf(state_high_tf: pd.Series, index_low_tf: pd.DatetimeIndex) -> pd.Series:
        """
        Align high timeframe states to low timeframe index.
        Uses ffill() to propagate the last known high timeframe state.
        Ensures strict time alignment (no lookahead).
        """
        # Reindex with forward fill
        aligned = state_high_tf.reindex(index_low_tf, method='ffill')
        
        # Handle initial NaNs if low TF starts before high TF
        # aligned.fillna(method='bfill', inplace=True) # Deprecated in newer pandas
        aligned.fillna(MarketState.SIDEWAYS, inplace=True)
        
        return aligned
