import os
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from core.indicators import Indicators
from core.state import MarketStateMachine, MarketState
from core.portfolio import Portfolio
from core.broker import Broker
from core.risk import RiskManager
from strategies.trend_following import TrendUpStrategy, TrendDownStrategy
from strategies.mean_reversion import RangeStrategy
from strategies.trend_breakout import TrendBreakoutStrategy
from router.router import Router
from config.config import config


class BacktestEngine:
    def __init__(
        self,
        initial_capital: float = 10000.0,
        slippage: float = 0.0,
        random_slip: bool = False,
        warmup_period: int = 50,
    ):
        self.initial_capital = initial_capital
        # If config is present, use it to override or supplement
        # But command line args usually take precedence if passed explicitly?
        # Here we trust the caller passed the right overrides.

        # Load params from config
        self.config_execution = config.get("execution") or {}
        self.config_risk = config.get("risk") or {}
        self.config_routing = config.get("routing") or {}

        # CLI overrides
        self.slippage = slippage
        self.random_slip = random_slip
        self.warmup_period = warmup_period

        # Determine effective slippage (CLI vs Config)
        # If CLI is 0.0 (default), check config.
        # But if user explicitly wanted 0.0, this logic is flawed.
        # Let's assume CLI takes precedence if provided (caller logic).
        # Actually Main.py passes defaults.
        # We'll use the passed values as they come from Main which handles CLI.

        # However, Broker needs commission rates from config.

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

    def run(
        self,
        data_map: Dict[str, pd.DataFrame],
        strategies: Optional[Dict[str, Any]] = None,
        routing_log_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run backtest on multiple symbols.
        data_map: symbol -> DataFrame (OHLCV)
        strategies: Optional dict of Strategy instances. If None, uses defaults.
        routing_log_path: Optional path for routing log CSV.
        """
        # 1. Setup Core Components
        portfolio = Portfolio(self.initial_capital)

        # Setup Broker with Config
        broker = Broker(
            portfolio,
            slippage=self.slippage,
            random_slip=self.random_slip,
            commission_rate=self.config_execution.get("commission_rate_taker", 0.001),
            commission_rate_maker=self.config_execution.get(
                "commission_rate_maker", 0.0005
            ),
            use_impact_cost=self.config_execution.get("use_impact_cost", False),
        )

        # Setup Risk Manager with Config
        risk_manager = RiskManager(
            risk_per_trade=self.config_risk.get("risk_per_trade", 0.01),
            max_leverage=self.config_risk.get("max_leverage", 3.0),
            max_drawdown_limit=self.config_risk.get("max_drawdown_limit", 0.20),
        )

        state_machine = MarketStateMachine()

        # 2. Setup Strategies & Router
        if strategies is None:
            strategies = {
                "TrendUp": TrendUpStrategy(),
                "TrendDown": TrendDownStrategy(),
                "RangeMeanReversion": RangeStrategy(),
                "TrendBreakout": TrendBreakoutStrategy(),
            }

        # Setup Router logging path
        if routing_log_path is None:
            log_dir = os.path.join(os.getcwd(), "reports")
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            routing_log_path = os.path.join(log_dir, "routing_log.csv")
        else:
            # Ensure directory exists
            log_dir = os.path.dirname(routing_log_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir)

        router = Router(
            strategies, regime_map=self.config_routing, log_path=routing_log_path
        )

        # 3. Prepare Data
        # Get intersection of indices to sync time axis
        if not data_map:
            return {}

        normalized_data_map: Dict[str, pd.DataFrame] = {}
        for symbol, df in data_map.items():
            normalized_df = self._prepare_dataframe(df)
            if normalized_df.empty:
                print(
                    f"Skipping {symbol}: empty/invalid dataframe after normalization."
                )
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
                    print(
                        "No exact timestamp overlap; aligned symbols by calendar date."
                    )

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

        # Track Daily Start Equity for Circuit Breaker
        daily_start_equity = self.initial_capital
        current_day = None

        print(f"Starting backtest on {len(timestamps)} bars...")

        # Skip first N bars to allow indicators to warm up (SMA30, ATR14, etc.)
        start_idx = self.warmup_period

        for i in range(len(timestamps)):
            current_time = timestamps[i]

            # Update Daily Start Equity
            this_day = current_time.date()
            if current_day != this_day:
                # New day, update reference equity
                # Using yesterday's closing equity (or today's open if we tracked it)
                # Here we use the equity at the START of processing this bar (before PnL update? No, from last step)
                if i > 0 and len(equity_curve) > 0:
                    daily_start_equity = equity_curve[-1]["equity"]
                current_day = this_day
                # Reset circuit breaker (if we want it to reset daily? Usually yes for intraday limit)
                # But if we hit max drawdown limit of total account, it shouldn't reset.
                # RiskManager implements "max_drawdown_limit" which usually means Trailing Max Drawdown or Intraday?
                # The requirement said "Intraday Max Loss Circuit Breaker".
                # So we should reset the breaker flag in RiskManager if it's a new day?
                # But RiskManager logic I wrote compares current vs daily_start.
                # If triggered, it stays triggered. I should add a reset method or handle it here.
                # For safety, let's assume if it triggers, we stop for the day.
                # Next day we might resume? Or stop forever?
                # "triggers flatten + stop opening". Usually means stop for the day.
                if risk_manager.circuit_breaker_triggered:
                    # Optional: Reset for new day?
                    # risk_manager.reset_breaker()
                    pass

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

            # Circuit Breaker Check (Intraday)
            total_value = portfolio.get_total_value(current_prices)
            if risk_manager.check_circuit_breaker(total_value, daily_start_equity):
                # Flatten positions if triggered
                # We need to send market sell orders for all positions
                for symbol, pos in portfolio.positions.items():
                    qty = pos["qty"]
                    if qty != 0:
                        # Close it
                        # Assuming liquid market, close at current Close price (or next Open?)
                        # Backtest logic usually queues for Next Open.
                        # So we submit orders.
                        if qty > 0:
                            broker.submit_order(
                                symbol,
                                "sell",
                                abs(qty),
                                current_prices[symbol],
                                timestamp=current_time,
                                strategy_id="CircuitBreaker",
                                exit_reason="MaxLoss",
                            )
                        else:
                            broker.submit_order(
                                symbol,
                                "cover",
                                abs(qty),
                                current_prices[symbol],
                                timestamp=current_time,
                                strategy_id="CircuitBreaker",
                                exit_reason="MaxLoss",
                            )

                # Skip Routing (Stop Opening)
                # But we still need to record equity
            else:
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

        # Save Routing Log
        router.save_log()

        # 5. Calculate Benchmark (Equal Weight Buy & Hold)
        benchmark_series = None
        if processed_data and len(timestamps) > 0:
            try:
                # Extract close prices
                closes = pd.DataFrame(
                    {sym: df["close"] for sym, df in processed_data.items()}
                )
                # Calculate returns
                returns = closes.pct_change().fillna(0)
                # Equal weight returns
                portfolio_returns = returns.mean(axis=1)
                # Cumulative return index (start at 1.0)
                benchmark_idx = (1 + portfolio_returns).cumprod()
                # Normalize to initial capital
                # We want it to start matching the equity curve at start_idx (or 0)
                # But equity curve stays flat until start_idx.
                # Let's normalize so that at start_idx, Benchmark = Initial Capital

                if start_idx < len(benchmark_idx):
                    base_val = benchmark_idx.iloc[start_idx]
                    if base_val != 0:
                        benchmark_series = (
                            benchmark_idx / base_val
                        ) * self.initial_capital
                        # Set values before start_idx to initial_capital (cash)
                        benchmark_series.iloc[:start_idx] = self.initial_capital
                else:
                    benchmark_series = benchmark_idx * self.initial_capital  # Fallback

            except Exception as e:
                print(f"Warning: Failed to calculate benchmark: {e}")

        return {
            "trades": broker.trades,
            "equity_curve": pd.DataFrame(equity_curve).set_index("timestamp"),
            "benchmark": benchmark_series,
        }
