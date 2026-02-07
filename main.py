import sys
import os
import argparse
import random
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.data_fetcher import DataFetcher
from backtest.engine import BacktestEngine
from backtest.reporting import ReportGenerator


def get_data(
    symbol: str, start: str, end: str, source: str = "synthetic", days: int = 365
) -> pd.DataFrame:
    fetcher = DataFetcher()

    if source == "ccxt":
        return fetcher.fetch_ccxt(symbol, limit=days, start_date=start, end_date=end)
    elif source == "yahoo":
        return fetcher.fetch_yahoo(symbol, start, end)
    else:
        # Synthetic / Scenario
        return fetcher.generate_scenario(symbol, start, end)


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
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=0.0,
        help="Slippage rate (e.g. 0.001 for 0.1%). If random_slip is True, this is max slippage.",
    )
    parser.add_argument(
        "--random_slip",
        action="store_true",
        help="Enable random slippage (uniform distribution from 0 to --slippage)",
    )
    args = parser.parse_args()

    if args.seed is not None:
        np.random.seed(args.seed)
        random.seed(args.seed)
        print(f"Random seed set to {args.seed}")

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
        f"Config: Capital={args.capital}, Symbols={args.symbols}, Source={args.source}, Slippage={args.slippage}, RandomSlip={args.random_slip}"
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
    engine = BacktestEngine(
        initial_capital=args.capital,
        slippage=args.slippage,
        random_slip=args.random_slip,
    )

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
