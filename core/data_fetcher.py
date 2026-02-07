import os
import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Optional

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataFetcher:
    """
    Unified data fetcher for Yahoo Finance (yfinance) and Crypto Exchanges (ccxt).
    Supports proxy configuration.
    """

    def __init__(self, proxy_url: str = "http://127.0.0.1:7897"):
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
                except:
                    pass

            return self._normalize(df)

        except ImportError:
            logger.error("yfinance not installed. Please run: pip install yfinance")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error fetching {symbol} from Yahoo: {e}")
            return pd.DataFrame()

    def fetch_ccxt(
        self, symbol: str, timeframe: str = "1d", limit: int = 1000
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

            exchange = ccxt.binance(
                {
                    "enableRateLimit": True,
                    "proxies": {
                        "http": self.proxy_url,
                        "https": self.proxy_url,
                    }
                    if self.proxy_url
                    else None,
                }
            )

            # Check if symbol exists
            # exchange.load_markets() # Can be slow, skip if confident

            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

            if not ohlcv:
                logger.warning(f"No data returned for {symbol}")
                return pd.DataFrame()

            df = pd.DataFrame(
                ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)

            return self._normalize(df)

        except ImportError:
            logger.error("ccxt not installed. Please run: pip install ccxt")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error fetching {symbol} from CCXT: {e}")
            return pd.DataFrame()

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names and types."""
        df.columns = [c.lower() for c in df.columns]
        # Ensure required columns exist
        required = ["open", "high", "low", "close", "volume"]
        for col in required:
            if col not in df.columns:
                # Try to map similar names? For now just return as is, DataHandler will catch it
                pass
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df
