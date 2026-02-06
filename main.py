import sys
import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backtest.engine import BacktestEngine
from backtest.reporting import ReportGenerator

import numpy as np


def generate_scenario_data(
    symbol: str, start_date: datetime, end_date: datetime
) -> pd.DataFrame:
    print(f"Generating scenario-based data for {symbol}...")

    dates = pd.date_range(start=start_date, end=end_date, freq="D")
    days = len(dates)

    if days < 10:
        print("Warning: Date range too short for meaningful scenario generation.")

    # Split into 3 phases: Trend Up, Sideways, Trend Down
    phase_len = days // 3

    # 1. Trend Up (Strong upward drift, low volatility)
    # Drift 0.5% per day, Vol 1%
    phase1_returns = np.random.normal(0.005, 0.01, size=phase_len)

    # 2. Sideways (Zero drift, higher volatility)
    # Drift 0%, Vol 2%
    phase2_returns = np.random.normal(0.0, 0.02, size=phase_len)

    # 3. Trend Down (Strong downward drift, high volatility)
    # Drift -0.5% per day, Vol 1.5%
    remaining = days - (phase_len * 2)
    phase3_returns = np.random.normal(-0.005, 0.015, size=remaining)

    returns = np.concatenate([phase1_returns, phase2_returns, phase3_returns])

    start_price = 10000.0 if "BTC" in symbol else 2000.0
    price_path = start_price * np.exp(np.cumsum(returns))

    # OHLC
    # High/Low relative to Close
    # Add some noise to High/Low to ensure ATR is not zero
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
    return df


from core.data_fetcher import DataFetcher


def get_data(
    symbol: str, start: str, end: str, source: str = "synthetic", days: int = 365
) -> pd.DataFrame:
    fetcher = DataFetcher()

    if source == "ccxt":
        # CCXT typically uses limits, so we estimate limit from days
        return fetcher.fetch_ccxt(symbol, limit=days)
    elif source == "yahoo":
        return fetcher.fetch_yahoo(symbol, start, end)
    else:
        s_dt = datetime.strptime(start, "%Y-%m-%d")
        e_dt = datetime.strptime(end, "%Y-%m-%d")
        return generate_scenario_data(symbol, s_dt, e_dt)


import argparse


def main():
    parser = argparse.ArgumentParser(description="Quantitative Trading System Backtest")
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Number of days to backtest (default: 365)",
    )
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--capital", type=float, default=1000.0, help="Initial capital (USDT)"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["BTC-USD", "ETH-USD"],
        help="List of symbols to trade",
    )
    parser.add_argument(
        "--source",
        type=str,
        default="synthetic",
        choices=["synthetic", "yahoo", "ccxt"],
        help="Data source",
    )
    args = parser.parse_args()

    print("Starting Quantitative Trading System...")
    print(f"Current Working Directory: {os.getcwd()}")

    # Determine Date Range
    if args.start and args.end:
        try:
            start_date = datetime.strptime(args.start, "%Y-%m-%d")
            end_date = datetime.strptime(args.end, "%Y-%m-%d")
            if start_date >= end_date:
                print("Error: Start date must be before end date.")
                return
            args.days = (end_date - start_date).days
            print(f"Config: Date Range={args.start} to {args.end} ({args.days} days)")
        except ValueError:
            print("Error: Invalid date format. Please use YYYY-MM-DD.")
            return
    else:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=args.days)
        print(
            f"Config: Last {args.days} Days (Auto-calculated: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})"
        )

    print(
        f"Config: Capital={args.capital}, Symbols={args.symbols}, Source={args.source}"
    )

    # 1. Fetch Data
    # start_date and end_date are already set above

    # Test with Crypto pairs
    symbols = args.symbols
    data_map = {}

    for sym in symbols:
        df = get_data(
            sym,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
            args.source,
            args.days,
        )

        if not df.empty and len(df) > 10:  # Lower limit for short tests
            print(f"Loaded {sym}: {len(df)} bars")
            data_map[sym] = df
        else:
            print(f"Failed to load sufficient data for {sym}")

    if not data_map:
        print("No data available. Exiting.")
        return

    # 2. Run Backtest
    print("\nInitializing Backtest Engine...")
    engine = BacktestEngine(initial_capital=args.capital)

    print("Running Backtest...")
    results = engine.run(data_map)

    if not results or results["equity_curve"].empty:
        print("Backtest failed or produced no results.")
        return

    # 3. Generate Report
    print("\nGenerating Report...")

    # Calculate basic return for naming
    equity = results["equity_curve"]["equity"]
    total_return = (equity.iloc[-1] / equity.iloc[0]) - 1
    return_str = f"Ret{total_return * 100:.1f}pct"

    # Naming convention: YYYYMMDD_HHMMSS_{Days}d_{Syms}Syms_{Ret}pct
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    symbols_str = f"{len(args.symbols)}Syms"
    days_str = f"{args.days}d"

    folder_name = f"{timestamp}_{days_str}_{symbols_str}_{return_str}"
    output_dir = os.path.join(os.getcwd(), "reports", folder_name)

    reporter = ReportGenerator(output_dir)

    # Prepare metadata
    metadata = {
        "Days": args.days,
        "Start": start_date.strftime("%Y-%m-%d"),
        "End": end_date.strftime("%Y-%m-%d"),
        "Capital": args.capital,
        "Symbols": ", ".join(args.symbols),
        "Source": args.source,
    }

    metrics = reporter.generate(
        results["trades"], results["equity_curve"], metadata=metadata
    )

    print("\n" + "=" * 30)
    print("BACKTEST RESULTS")
    print("=" * 30)
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"{k:<35}: {v:.4f}")
        else:
            print(f"{k:<35}: {v}")
    print("=" * 30)

    print(f"\nReport saved to: {output_dir}")


if __name__ == "__main__":
    main()
