import unittest
import sys
import os
import pandas as pd
import numpy as np

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from core.portfolio import Portfolio
from core.broker import Broker
from core.state import MarketState
from strategies.base import Strategy
from backtest.engine import BacktestEngine


class MockStrategy(Strategy):
    def __init__(self):
        super().__init__(
            "MockStrategy",
            {MarketState.SIDEWAYS, MarketState.TREND_UP, MarketState.TREND_DOWN},
        )
        self.triggered = False

    def should_enter(self, symbol, i, df, state, portfolio):
        # Trigger buy at index 50
        if i == 50 and not self.triggered:
            self.triggered = True
            current_price = df["close"].iloc[i]
            sl = current_price * 0.95
            return {"action": "buy", "stop_loss": sl}
        return None

    def should_exit(self, symbol, i, df, state, portfolio):
        return None


class TestNoLookahead(unittest.TestCase):
    def test_execution_timing(self):
        """
        Verify that a signal generated at Bar T executes at Bar T+1 Open.
        """
        # 1. Create Data (100 bars to satisfy indicator warmup)
        dates = pd.date_range(start="2024-01-01", periods=100, freq="D")

        # Linear price increase: 100, 101, 102...
        # Open = i+100
        # Close = i+100.5
        prices = np.arange(100) + 100.0

        data = {
            "open": prices,  # T0=100, T1=101... T50=150
            "high": prices + 2.0,
            "low": prices - 2.0,
            "close": prices + 0.5,  # T0=100.5, T1=101.5... T50=150.5
            "volume": [1000] * 100,
        }
        df = pd.DataFrame(data, index=dates)

        # T50: Open=150, Close=150.5 -> Signal Here
        # T51: Open=151, Close=151.5 -> Execution Here

        target_idx = 50

        # 2. Setup Engine
        engine = BacktestEngine(initial_capital=10000.0, warmup_period=20)

        # Inject Mock Strategy directly into the engine's router (need to subclass or patch)
        # Since Engine hardcodes strategies, we might need to mock the Router or the Engine's strategies dict.
        # But Engine.run creates new instances.

        # Workaround: Use a modified run method or monkey patch Router.
        # Let's verify by manually running the loop logic or creating a subclass of Engine.

        class TestEngine(BacktestEngine):
            def run(self, data_map):
                # ... Copy-paste run logic or just override the strategies setup part?
                # It's better to modify the Engine to accept strategies, but for now let's monkeypatch.
                pass

        # Actually, let's just rely on the existing TrendUpStrategy logic if possible?
        # No, TrendUp requires SMA30 etc. Data is too short.

        # Best approach: Test Broker + Loop Logic in isolation without full Engine,
        # OR patch Router.

        from router.router import Router

        original_init = Router.__init__
        original_map = Router._map_state_to_strategy

        def mock_init(self_router, strategies_dict=None):
            self_router.strategies = {"Mock": MockStrategy()}
            self_router.cooldown_bars = 0
            self_router.cooldowns = {}
            self_router.symbol_states = {}

        def mock_map(self_router, state):
            return "Mock"

        Router.__init__ = mock_init
        Router._map_state_to_strategy = mock_map

        try:
            # 3. Run Backtest
            results = engine.run({"TEST": df})

            # 4. Analyze Trades
            trades = results["trades"]
            self.assertTrue(len(trades) > 0, "No trades generated")

            trade = trades[0]

            # Check Signal Time
            # Signal was at index 50 -> T50 -> dates[50]
            signal_time = trade["signal_time"]
            expected_signal_time = dates[50]
            self.assertEqual(
                signal_time,
                expected_signal_time,
                f"Signal time mismatch. Got {signal_time}, expected {expected_signal_time}",
            )

            # Check Fill Time
            # Should be index 51 -> T51 -> dates[51]
            fill_time = trade["fill_time"]
            expected_fill_time = dates[51]
            self.assertEqual(
                fill_time,
                expected_fill_time,
                f"Fill time mismatch. Got {fill_time}, expected {expected_fill_time}",
            )

            # Check Fill Price
            # Should be T51 Open = 151.0
            fill_price = trade["fill_price"]
            expected_price = 151.0
            self.assertEqual(
                fill_price,
                expected_price,
                f"Fill price mismatch. Got {fill_price}, expected {expected_price} (T51 Open). T50 Close was 150.5.",
            )

            print("\n[Success] No Look-ahead Bias detected.")
            print(f"Signal at {signal_time} (T50 Close {df.iloc[50]['close']})")
            print(
                f"Filled at {fill_time} (T51 Open {df.iloc[51]['open']}) @ {fill_price}"
            )

        finally:
            # Restore Router
            Router.__init__ = original_init
            Router._map_state_to_strategy = original_map


if __name__ == "__main__":
    unittest.main()
