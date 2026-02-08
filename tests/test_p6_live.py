import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import sys
import os
from datetime import datetime

# Add project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.live_broker import LiveBroker
from live_trading.engine import LiveTradingEngine
from core.portfolio import Portfolio
from core.risk import RiskManager


class TestLiveTrading(unittest.TestCase):
    def setUp(self):
        self.portfolio = Portfolio()
        self.risk_manager = RiskManager()

        # Mock CCXT Exchange
        self.mock_exchange = MagicMock()
        self.mock_exchange.fetch_balance.return_value = {
            "total": {"USDT": 10000.0, "BTC": 0.0},
            "free": {"USDT": 10000.0, "BTC": 0.0},
        }
        self.mock_exchange.create_order.return_value = {
            "id": "12345",
            "status": "closed",
            "average": 50000.0,
        }
        self.mock_exchange.fetch_ohlcv.return_value = [
            [1609459200000, 50000, 51000, 49000, 50500, 100]  # Timestamp, O, H, L, C, V
        ]

    @patch("core.live_broker.ccxt")
    def test_broker_sync(self, mock_ccxt):
        # Setup Mock Class
        mock_ccxt.binance.return_value = self.mock_exchange

        broker = LiveBroker(self.portfolio, exchange_id="binance")
        broker.sync()

        self.assertEqual(self.portfolio.cash, 10000.0)
        self.mock_exchange.fetch_balance.assert_called_once()

    @patch("core.live_broker.ccxt")
    def test_broker_submit_order(self, mock_ccxt):
        mock_ccxt.binance.return_value = self.mock_exchange

        broker = LiveBroker(self.portfolio, exchange_id="binance")
        broker.submit_order("BTC/USDT", "buy", 0.1, 50000.0, "limit")

        self.mock_exchange.create_order.assert_called_with(
            symbol="BTC/USDT",
            type="limit",
            side="buy",
            amount=0.1,
            price=50000.0,
            params={},
        )
        self.assertEqual(len(broker.trades), 1)

    @patch("core.data_fetcher.DataFetcher.fetch_ccxt")
    @patch("core.live_broker.ccxt")
    def test_engine_initialization(self, mock_ccxt, mock_fetch_ccxt):
        mock_ccxt.binance.return_value = self.mock_exchange

        # Mock Data Fetcher returning a DataFrame
        df = pd.DataFrame(
            {
                "open": [100, 101],
                "high": [102, 103],
                "low": [99, 100],
                "close": [101, 102],
                "volume": [1000, 1000],
            },
            index=pd.to_datetime(["2021-01-01", "2021-01-02"]),
        )
        mock_fetch_ccxt.return_value = df

        broker = LiveBroker(self.portfolio, exchange_id="binance")
        engine = LiveTradingEngine(
            symbols=["BTC/USDT"],
            strategies={},
            broker=broker,
            risk_manager=self.risk_manager,
        )

        # We assume fetcher is mocked inside engine or injected
        # In implementation, engine instantiates DataFetcher internally.
        # So we patch the method on the class (done via decorator)

        engine.initialize()

        self.assertIn("BTC/USDT", engine.data_map)
        self.assertEqual(len(engine.data_map["BTC/USDT"]), 2)
        mock_fetch_ccxt.assert_called()


if __name__ == "__main__":
    unittest.main()
