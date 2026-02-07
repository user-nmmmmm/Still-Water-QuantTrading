import pandas as pd
import numpy as np
from typing import Dict, List, Any
from core.indicators import Indicators
from core.state import MarketStateMachine, MarketState
from core.portfolio import Portfolio
from core.broker import Broker
from core.risk import RiskManager
from strategies.trend_following import TrendUpStrategy, TrendDownStrategy
from strategies.mean_reversion import RangeStrategy
from router.router import Router


class BacktestEngine:
    def __init__(
        self,
        initial_capital: float = 10000.0,
        slippage: float = 0.0,
        random_slip: bool = False,
    ):
        self.initial_capital = initial_capital
        self.slippage = slippage
        self.random_slip = random_slip

    @staticmethod
    def _prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """Normalize index type/tz and remove duplicated timestamps."""
        if df is None or df.empty:
            return pd.DataFrame()

        normalized = df.copy()
        normalized.index = pd.to_datetime(normalized.index, errors="coerce")
        valid_mask = ~pd.isna(normalized.index)
        normalized = normalized.loc[valid_mask].copy()

        if normalized.empty:
            return normalized

        idx = normalized.index
        if idx.tz is not None:
            idx = idx.tz_convert("UTC").tz_localize(None)
        normalized.index = idx

        normalized = normalized[~normalized.index.duplicated(keep="last")]
        normalized = normalized.sort_index()
        return normalized

    @staticmethod
    def _looks_daily_or_slower(indices: List[pd.DatetimeIndex]) -> bool:
        """Heuristic: detect daily/weekly-like bars to allow date-based alignment."""
        for idx in indices:
            if len(idx) < 2:
                continue

            diffs = idx.to_series().diff().dropna()
            if diffs.empty:
                continue

            median_gap_seconds = diffs.dt.total_seconds().median()
            if pd.notna(median_gap_seconds) and median_gap_seconds < 23 * 3600:
                return False

        return True

    def run(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """
        Run backtest on multiple symbols.
        data_map: symbol -> DataFrame (OHLCV)
        """
        # 1. Setup Core Components
        portfolio = Portfolio(self.initial_capital)
        broker = Broker(portfolio, slippage=self.slippage, random_slip=self.random_slip)
        risk_manager = RiskManager()
        state_machine = MarketStateMachine()

        # 2. Setup Strategies & Router
        strategies = {
            "TrendUp": TrendUpStrategy(),
            "TrendDown": TrendDownStrategy(),
            "RangeMeanReversion": RangeStrategy(),
        }
        router = Router(strategies)

        # 3. Prepare Data
        # Get intersection of indices to sync time axis
        if not data_map:
            return {}

        normalized_data_map: Dict[str, pd.DataFrame] = {}
        for symbol, df in data_map.items():
            normalized_df = self._prepare_dataframe(df)
            if normalized_df.empty:
                print(f"Skipping {symbol}: empty/invalid dataframe after normalization.")
                continue
            normalized_data_map[symbol] = normalized_df

        if not normalized_data_map:
            print("No valid symbol data available after normalization.")
            return {"trades": [], "equity_curve": pd.DataFrame()}

        common_index = None
        for df in normalized_data_map.values():
            if common_index is None:
                common_index = df.index
            else:
                common_index = common_index.intersection(df.index)

        # Fallback for daily bars from heterogeneous providers/timezones.
        if common_index is None or len(common_index) == 0:
            indices = [df.index for df in normalized_data_map.values()]
            if self._looks_daily_or_slower(indices):
                common_dates = None
                for idx in indices:
                    date_idx = pd.DatetimeIndex(idx.normalize().unique())
                    if common_dates is None:
                        common_dates = date_idx
                    else:
                        common_dates = common_dates.intersection(date_idx)

                if common_dates is not None and len(common_dates) > 0:
                    common_index = common_dates.sort_values()
                    remapped_data_map: Dict[str, pd.DataFrame] = {}

                    for symbol, df in normalized_data_map.items():
                        daily_df = df.groupby(df.index.normalize()).last()
                        daily_df.index = pd.DatetimeIndex(daily_df.index)
                        remapped_data_map[symbol] = daily_df

                    normalized_data_map = remapped_data_map
                    print("No exact timestamp overlap; aligned symbols by calendar date.")

        if common_index is None or len(common_index) == 0:
            print("No common timeframe found for symbols.")
            for symbol, df in normalized_data_map.items():
                print(
                    f"{symbol}: {df.index.min()} -> {df.index.max()} ({len(df)} bars)"
                )
            return {"trades": [], "equity_curve": pd.DataFrame()}

        common_index = common_index.sort_values()

        # Reindex and Calculate Indicators
        processed_data = {}
        for symbol, df in normalized_data_map.items():
            # Reindex
            df_aligned = df.reindex(common_index).copy()

            # Forward fill price data (if gaps exist)
            df_aligned = df_aligned.ffill().bfill()

            # Calculate Indicators
            # Indicators.calculate_all modifies the dataframe in-place
            Indicators.calculate_all(df_aligned)

            processed_data[symbol] = df_aligned

        # 4. Main Loop
        equity_curve = []
        timestamps = common_index

        print(f"Starting backtest on {len(timestamps)} bars...")

        # Skip first 50 bars to allow indicators to warm up (SMA30, ATR14, etc.)
        start_idx = 50

        for i in range(len(timestamps)):
            if i < start_idx:
                # Still record equity (cash only)
                equity_curve.append(
                    {
                        "timestamp": timestamps[i],
                        "equity": self.initial_capital,
                        "cash": self.initial_capital,
                    }
                )
                continue

            current_time = timestamps[i]

            # 4.1 Process Pending Orders (Execute at Open)
            current_bars_data = {}
            for symbol, df in processed_data.items():
                current_bars_data[symbol] = df.iloc[i]

            broker.process_orders(current_bars_data)

            # Update Portfolio Market Value (Mark to Market)
            current_prices = {}
            for symbol, df in processed_data.items():
                current_prices[symbol] = df["close"].iloc[i]

            # Routing & Execution per symbol
            for symbol, df in processed_data.items():
                # Get State
                state = state_machine.get_state(df, i)

                # Route
                router.route(
                    symbol,
                    i,
                    df,
                    state,
                    portfolio,
                    broker,
                    risk_manager,
                    current_prices,
                )

            # Record Equity
            total_value = portfolio.get_total_value(current_prices)
            equity_curve.append(
                {
                    "timestamp": current_time,
                    "equity": total_value,
                    "cash": portfolio.cash,
                }
            )

        print("Backtest completed.")

        return {
            "trades": broker.trades,
            "equity_curve": pd.DataFrame(equity_curve).set_index("timestamp"),
        }
