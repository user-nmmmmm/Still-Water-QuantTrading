import pandas as pd
import numpy as np
from typing import Dict, List, Any
from core.data import DataHandler
from core.indicators import Indicators
from core.state import MarketStateMachine, MarketState
from core.portfolio import Portfolio
from core.broker import Broker
from core.risk import RiskManager
from strategies.trend_following import TrendUpStrategy, TrendDownStrategy
from strategies.mean_reversion import RangeStrategy
from router.router import Router

class BacktestEngine:
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        
    def run(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """
        Run backtest on multiple symbols.
        data_map: symbol -> DataFrame (OHLCV)
        """
        # 1. Setup Core Components
        portfolio = Portfolio(self.initial_capital)
        broker = Broker(portfolio)
        risk_manager = RiskManager()
        state_machine = MarketStateMachine()
        
        # 2. Setup Strategies & Router
        strategies = {
            "TrendUp": TrendUpStrategy(),
            "TrendDown": TrendDownStrategy(),
            "RangeMeanReversion": RangeStrategy()
        }
        router = Router(strategies)
        
        # 3. Prepare Data
        # Get intersection of indices to sync time axis
        if not data_map:
            return {}
            
        common_index = None
        for df in data_map.values():
            # Ensure index is DatetimeIndex
            if not isinstance(df.index, pd.DatetimeIndex):
                try:
                    df.index = pd.to_datetime(df.index)
                except:
                    pass
                    
            if common_index is None:
                common_index = df.index
            else:
                common_index = common_index.intersection(df.index)
        
        if common_index is None or len(common_index) == 0:
            print("No common timeframe found for symbols.")
            return {'trades': [], 'equity_curve': pd.DataFrame()}
            
        common_index = common_index.sort_values()
        
        # Reindex and Calculate Indicators
        processed_data = {}
        for symbol, df in data_map.items():
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
                equity_curve.append({
                    'timestamp': timestamps[i],
                    'equity': self.initial_capital,
                    'cash': self.initial_capital
                })
                continue
                
            current_time = timestamps[i]
            
            # Update Portfolio Market Value (Mark to Market)
            current_prices = {}
            for symbol, df in processed_data.items():
                current_prices[symbol] = df['close'].iloc[i]
            
            # Routing & Execution per symbol
            for symbol, df in processed_data.items():
                # Get State
                state = state_machine.get_state(df, i)
                
                # Route
                router.route(symbol, i, df, state, portfolio, broker, risk_manager, current_prices)
            
            # Record Equity
            total_value = portfolio.get_total_value(current_prices)
            equity_curve.append({
                'timestamp': current_time,
                'equity': total_value,
                'cash': portfolio.cash
            })
            
        print("Backtest completed.")
        
        return {
            'trades': broker.trades,
            'equity_curve': pd.DataFrame(equity_curve).set_index('timestamp')
        }
