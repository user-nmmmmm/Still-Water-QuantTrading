import time
import logging
import pandas as pd
import json
import os
from typing import List, Dict
from datetime import datetime
from core.data_fetcher import DataFetcher
from core.portfolio import Portfolio
from core.risk import RiskManager
from core.live_broker import LiveBroker
from router.router import Router
from core.state import MarketStateMachine

logger = logging.getLogger(__name__)


class LiveTradingEngine:
    def __init__(
        self,
        symbols: List[str],
        strategies: Dict,
        broker: LiveBroker,
        risk_manager: RiskManager,
        interval_seconds: int = 60,  # Check every minute
        lookback_days: int = 30,  # Data buffer
        timeframe: str = "1d",
    ):
        self.symbols = symbols
        self.strategies = strategies
        self.broker = broker
        self.risk_manager = risk_manager
        self.interval = interval_seconds
        self.lookback_days = lookback_days
        self.timeframe = timeframe

        self.fetcher = DataFetcher()
        self.state_machine = MarketStateMachine()

        # Initialize Router
        self.router = Router(strategies)

        # Data Buffer: symbol -> DataFrame
        self.data_map: Dict[str, pd.DataFrame] = {}

        # Ensure reports directory exists for state export
        os.makedirs("reports", exist_ok=True)
        self.state_file = "reports/live_status.json"

    def initialize(self):
        """Warmup data"""
        logger.info("Initializing Live Trading Engine...")
        self.broker.sync()

        # Fetch initial data
        end_date = datetime.now().strftime("%Y-%m-%d")
        # Calculate start date approx
        # For simplicity, just fetch last N days

        for symbol in self.symbols:
            logger.info(f"Warming up data for {symbol}...")
            # We use fetch_ccxt to get latest data from exchange directly
            # Note: fetch_ccxt implementation in DataFetcher might need adjustment for 'since'
            # But let's use it as is for now.
            df = self.fetcher.fetch_ccxt(symbol, limit=1000)  # Fetch ample history
            if not df.empty:
                self.data_map[symbol] = df
                logger.info(f"Loaded {len(df)} bars for {symbol}")
            else:
                logger.warning(f"Failed to load data for {symbol}")

    def run(self):
        """Main Loop"""
        logger.info("Starting Main Loop...")
        try:
            while True:
                self._tick()
                logger.info(f"Sleeping for {self.interval} seconds...")
                time.sleep(self.interval)
        except KeyboardInterrupt:
            logger.info("Live Trading Stopped by User")

    def _tick(self):
        """Single iteration"""
        logger.info(f"Tick: {datetime.now()}")

        # 1. Update Data
        self._update_data()

        # 2. Sync Portfolio
        self.broker.sync()

        # 3. Process each symbol
        for symbol in self.symbols:
            if symbol not in self.data_map:
                continue

            df = self.data_map[symbol]
            if df.empty:
                continue

            # Current Index (Last completed bar)
            # In live trading, 'i' is the last index
            i = len(df) - 1

            # Get Market State
            state = self.state_machine.get_state(df, i)
            logger.info(f"{symbol} State: {state.name}")

            # Get Current Prices for Valuation
            current_price = df["close"].iloc[-1]
            current_prices = {symbol: current_price}  # Simplification

            # Route & Execute
            # Note: Router.route expects 'i' to be the index to act on.
            # It calls strategy.on_bar(..., i, ...)
            self.router.route(
                symbol,
                i,
                df,
                state,
                self.broker.portfolio,
                self.broker,
                self.risk_manager,
                current_prices,
            )

        # 4. Export State
        self._export_state()

    def _update_data(self):
        """Fetch latest candles and append"""
        for symbol in self.symbols:
            # In a real efficient engine, we fetch only new candles.
            # Here, we re-fetch the last 100 bars to ensure we have the latest closed bar
            # and potential updates.
            new_df = self.fetcher.fetch_ccxt(symbol, limit=100)

            if new_df.empty:
                continue

            # Merge logic
            # Simplest: Just replace the tail of existing buffer or append new ones
            # We rely on timestamp index

            current_df = self.data_map.get(symbol, pd.DataFrame())

            if current_df.empty:
                self.data_map[symbol] = new_df
            else:
                # Combine and drop duplicates
                # Use combine_first or concat + drop_duplicates
                updated = pd.concat([current_df, new_df])
                updated = updated[~updated.index.duplicated(keep="last")]
                updated = updated.sort_index()
                self.data_map[symbol] = updated

    def _export_state(self):
        """Export current engine state to JSON for monitoring"""
        try:
            # Calculate Equity
            # We need current prices for all symbols in portfolio
            # We can use the latest close from self.data_map
            current_prices = {}
            for s, df in self.data_map.items():
                if not df.empty:
                    current_prices[s] = df["close"].iloc[-1]

            equity = self.broker.portfolio.get_equity(current_prices)

            state_data = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "cash": self.broker.portfolio.cash,
                "equity": equity,
                "positions": self.broker.portfolio.positions,
                "symbols": self.symbols,
                "last_update": datetime.now().isoformat(),
            }

            with open(self.state_file, "w") as f:
                json.dump(state_data, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to export state: {e}")
