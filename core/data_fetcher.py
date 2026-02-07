import os
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from typing import Optional, Union

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataFetcher:
    """
    Unified data fetcher for Yahoo Finance (yfinance) and Crypto Exchanges (ccxt).
    Supports proxy configuration.
    """

    def __init__(self, proxy_url: Optional[str] = None):
        self.proxy_url = proxy_url
        self._setup_proxy()

    def _setup_proxy(self):
        """Configure environment variables for proxy."""
        if self.proxy_url:
            os.environ["HTTP_PROXY"] = self.proxy_url
            os.environ["HTTPS_PROXY"] = self.proxy_url
            logger.info(f"Proxy configured: {self.proxy_url}")

    def fetch_yahoo(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch data from Yahoo Finance."""
        try:
            import yfinance as yf

            logger.info(f"Fetching {symbol} via yfinance...")

            # yfinance uses requests internally, which respects env vars
            df = yf.download(symbol, start=start_date, end=end_date, progress=False)

            if df.empty:
                logger.warning(f"No data returned for {symbol}")
                return pd.DataFrame()

            # Handle MultiIndex columns if present
            if isinstance(df.columns, pd.MultiIndex):
                try:
                    df.columns = df.columns.droplevel(1)
                except IndexError:
                    pass

            return self._normalize(df)

        except ImportError:
            logger.error("yfinance not installed. Please run: pip install yfinance")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error fetching {symbol} from Yahoo: {e}")
            return pd.DataFrame()

    def fetch_ccxt(
        self,
        symbol: str,
        timeframe: str = "1d",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """
        Fetch data from Binance via CCXT.
        Symbol format expected: 'BTC/USDT' (standard CCXT format).
        If 'BTC-USD' is passed, it will try to convert.
        """
        try:
            import ccxt

            logger.info(f"Fetching {symbol} via CCXT (Binance)...")

            # Convert Yahoo style (BTC-USD) to CCXT style (BTC/USDT) if needed
            if "-" in symbol and "/" not in symbol:
                base, quote = symbol.split("-")
                if quote == "USD":
                    quote = "USDT"  # Binance uses USDT mostly
                symbol = f"{base}/{quote}"

            proxies = None
            if self.proxy_url:
                proxies = {
                    "http": self.proxy_url,
                    "https": self.proxy_url,
                }

            exchange = ccxt.binance(
                {
                    "enableRateLimit": True,
                    "proxies": proxies,
                }
            )

            # Calculate 'since' timestamp if start_date is provided
            since = None
            if start_date:
                dt = datetime.strptime(start_date, "%Y-%m-%d")
                since = int(dt.timestamp() * 1000)

            # Check if symbol exists (optional)
            # exchange.load_markets()

            ohlcv = exchange.fetch_ohlcv(
                symbol, timeframe=timeframe, limit=limit, since=since
            )

            if not ohlcv:
                logger.warning(f"No data returned for {symbol}")
                return pd.DataFrame()

            df = pd.DataFrame(
                ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)

            # Filter by end_date if provided
            if end_date:
                df = df[df.index <= end_date]

            return self._normalize(df)

        except ImportError:
            logger.error("ccxt not installed. Please run: pip install ccxt")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error fetching {symbol} from CCXT: {e}")
            return pd.DataFrame()

    def generate_scenario(
        self,
        symbol: str,
        start_date: Union[str, datetime],
        end_date: Union[str, datetime],
    ) -> pd.DataFrame:
        """Generate synthetic scenario-based data."""
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, "%Y-%m-%d")

        print(f"Generating scenario-based data for {symbol}...")

        dates = pd.date_range(start=start_date, end=end_date, freq="D")
        days = len(dates)

        if days < 10:
            print("Warning: Date range too short for meaningful scenario generation.")

        # Split into 3 phases: Trend Up, Sideways, Trend Down
        phase_len = days // 3

        # 1. Trend Up (Strong upward drift, low volatility)
        phase1_returns = np.random.normal(0.005, 0.01, size=phase_len)

        # 2. Sideways (Zero drift, higher volatility)
        phase2_returns = np.random.normal(0.0, 0.02, size=phase_len)

        # 3. Trend Down (Strong downward drift, high volatility)
        remaining = days - (phase_len * 2)
        phase3_returns = np.random.normal(-0.005, 0.015, size=remaining)

        returns = np.concatenate([phase1_returns, phase2_returns, phase3_returns])

        start_price = 10000.0 if "BTC" in symbol else 2000.0
        price_path = start_price * np.exp(np.cumsum(returns))

        # OHLC
        high = price_path * (1 + np.abs(np.random.normal(0, 0.01, size=days)))
        low = price_path * (1 - np.abs(np.random.normal(0, 0.01, size=days)))
        close = price_path
        open_p = price_path * (1 + np.random.normal(0, 0.005, size=days))

        # Fix High/Low consistency
        high = np.maximum(high, np.maximum(open_p, close))
        low = np.minimum(low, np.minimum(open_p, close))

        data = {
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.random.randint(1000, 100000, size=days),
        }

        df = pd.DataFrame(data, index=dates)
        return self._normalize(df)

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names and types."""
        df.columns = [c.lower() for c in df.columns]
        # Ensure required columns exist
        required = ["open", "high", "low", "close", "volume"]
        for col in required:
            if col not in df.columns:
                # Try to map similar names? For now just return as is
                pass
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df
