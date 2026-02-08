import pandas as pd
import matplotlib.pyplot as plt
import argparse
import os
import glob

def plot_performance(report_dir):
    equity_file = os.path.join(report_dir, "equity.csv")
    if not os.path.exists(equity_file):
        print(f"Error: equity.csv not found in {report_dir}")
        return

    # Load Data
    df = pd.read_csv(equity_file, parse_dates=["timestamp"], index_col="timestamp")
    
    # Setup Plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
    
    # 1. Equity Curve
    ax1.plot(df.index, df["equity"], label="Strategy Equity", color="blue", linewidth=1.5)
    
    # Benchmark (Buy & Hold) - Normalize to initial capital
    # We assume 'close' prices are available or we can approximate from symbol data if needed.
    # For now, let's just plot Equity.
    
    ax1.set_title("Strategy Performance")
    ax1.set_ylabel("Equity (USDT)")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)

    # 2. Drawdown
    # Calculate Drawdown if not present
    if "drawdown_pct" not in df.columns:
        running_max = df["equity"].cummax()
        df["drawdown_pct"] = (df["equity"] - running_max) / running_max

    ax2.fill_between(df.index, df["drawdown_pct"], 0, color="red", alpha=0.3, label="Drawdown")
    ax2.set_ylabel("Drawdown (%)")
    ax2.set_xlabel("Date")
    ax2.legend(loc="lower left")
    ax2.grid(True, alpha=0.3)

    # Save
    output_path = os.path.join(report_dir, "performance_chart.png")
    plt.tight_layout()
    plt.savefig(output_path)
    print(f"Chart saved to: {output_path}")
    
    # Show (optional, if interactive)
    # plt.show()

def get_latest_report_dir():
    reports_dir = os.path.join(os.getcwd(), "reports")
    dirs = glob.glob(os.path.join(reports_dir, "*"))
    dirs = [d for d in dirs if os.path.isdir(d)]
    if not dirs:
        return None
    return max(dirs, key=os.path.getmtime)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot Performance from Backtest Report")
    parser.add_argument("--dir", type=str, help="Path to report directory")
    args = parser.parse_args()

    target_dir = args.dir
    if not target_dir:
        target_dir = get_latest_report_dir()
        if target_dir:
            print(f"Auto-detected latest report: {target_dir}")
        else:
            print("No reports found.")
            exit(1)

    plot_performance(target_dir)
