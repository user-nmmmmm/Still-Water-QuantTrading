import argparse
import logging
import os
import sys

# Add project root
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.portfolio import Portfolio
from core.risk import RiskManager
from core.live_broker import LiveBroker
from live_trading.engine import LiveTradingEngine
from strategies.trend_following import TrendUpStrategy, TrendDownStrategy
from strategies.mean_reversion import RangeStrategy

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="QuantTrading Live Engine")
    parser.add_argument("--symbols", nargs="+", default=["BTC/USDT", "ETH/USDT"], help="Symbols to trade")
    parser.add_argument("--interval", type=int, default=60, help="Loop interval in seconds")
    parser.add_argument("--sandbox", action="store_true", help="Use Exchange Sandbox/Testnet")
    parser.add_argument("--exchange", type=str, default="binance", help="Exchange ID (ccxt)")
    parser.add_argument("--api_key", type=str, help="API Key (optional, can use env vars)")
    parser.add_argument("--secret", type=str, help="API Secret (optional, can use env vars)")
    
    args = parser.parse_args()
    
    # 1. Setup Core Components
    portfolio = Portfolio() # Initial capital will be synced from exchange
    
    risk_manager = RiskManager(
        risk_per_trade=0.01, 
        max_leverage=3.0
    )
    
    # 2. Setup Broker
    broker = LiveBroker(
        portfolio=portfolio,
        exchange_id=args.exchange,
        api_key=args.api_key,
        secret=args.secret,
        sandbox=args.sandbox
    )
    
    # 3. Setup Strategies
    # We use the optimized parameters from P4 (SMA 30, ATR 2.0)
    strategies = {
        "TrendUp": TrendUpStrategy(sma_period=30, atr_multiplier=2.0),
        "TrendDown": TrendDownStrategy(sma_period=30, atr_multiplier=2.0),
        "RangeMeanReversion": RangeStrategy()
    }
    
    # 4. Initialize Engine
    engine = LiveTradingEngine(
        symbols=args.symbols,
        strategies=strategies,
        broker=broker,
        risk_manager=risk_manager,
        interval_seconds=args.interval
    )
    
    # 5. Run
    engine.initialize()
    engine.run()

if __name__ == "__main__":
    main()
