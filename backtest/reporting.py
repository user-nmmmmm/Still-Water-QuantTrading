import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from typing import List, Dict, Any, Tuple


class ReportGenerator:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def generate(
        self,
        trades: List[Dict],
        equity_curve: pd.DataFrame,
        metadata: Dict[str, Any] = None,
    ):
        # 1. Save CSVs
        equity_curve.to_csv(os.path.join(self.output_dir, "equity.csv"))

        trades_df = pd.DataFrame(trades)
        if not trades_df.empty:
            trades_df.to_csv(os.path.join(self.output_dir, "trades.csv"), index=False)

        # 2. Calculate Metrics
        trade_metrics = self._analyze_trades(trades_df)
        equity_metrics = self._calculate_equity_metrics(equity_curve)

        metrics = {**equity_metrics, **trade_metrics}

        # 3. Save Report Text
        self._save_report_text(metrics, metadata)

        # 4. Generate Plots
        self._plot_equity(equity_curve)

        return metrics

    def _calculate_equity_metrics(self, equity_curve: pd.DataFrame) -> Dict[str, Any]:
        equity = equity_curve["equity"]
        if equity.empty:
            return {}

        returns = equity.pct_change().dropna()

        start_val = equity.iloc[0]
        end_val = equity.iloc[-1]

        days = (equity.index[-1] - equity.index[0]).days
        years = max(days / 365.25, 0.01)

        cagr = (end_val / start_val) ** (1 / years) - 1

        # Max Drawdown
        rolling_max = equity.cummax()
        drawdown_pct = (equity - rolling_max) / rolling_max
        max_dd_pct = drawdown_pct.min()

        drawdown_amount = equity - rolling_max
        max_dd_amount = drawdown_amount.min()

        # Monthly Returns
        equity_curve["month"] = equity_curve.index.to_period("M")
        monthly_returns = equity_curve.groupby("month")["equity"].apply(
            lambda x: (x.iloc[-1] / x.iloc[0]) - 1
        )
        avg_monthly_return = monthly_returns.mean()

        # Sharpe
        if len(returns) < 2 or returns.std() == 0:
            sharpe = 0.0
        else:
            sharpe = returns.mean() / returns.std() * np.sqrt(252)

        return {
            "CAGR": cagr,
            "MaxDrawdownPct": max_dd_pct,
            "MaxDrawdownAmount": max_dd_amount,
            "AvgMonthlyReturn": avg_monthly_return,
            "SharpeRatio": sharpe,
            "EndEquity": end_val,
            "TotalReturn": (end_val - start_val) / start_val,
        }

    def _analyze_trades(self, trades_df: pd.DataFrame) -> Dict[str, Any]:
        if trades_df.empty:
            return {
                "TotalTrades": 0,
                "WinRate": 0.0,
                "ProfitFactor": 0.0,
                "AvgTrade": 0.0,
            }

        # Reconstruct PnL using FIFO
        closed_trades = []  # List of {'pnl': float, 'strategy': str}

        # Group by symbol
        for symbol, group in trades_df.groupby("symbol"):
            long_stack: List[
                Tuple[float, float, str, float]
            ] = []  # (qty, price, strategy_id, unit_comm)
            short_stack: List[
                Tuple[float, float, str, float]
            ] = []  # (qty, price, strategy_id, unit_comm)

            for _, row in group.iterrows():
                side = row["side"]
                qty = row["qty"]
                price = row["fill_price"]
                comm = row["commission"]
                unit_comm = comm / qty if qty > 0 else 0.0

                strategy_id = row.get("strategy_id", "Unknown")

                if side == "buy":
                    # Check if covering short
                    remaining = qty
                    while remaining > 0 and short_stack:
                        s_qty, s_price, s_strat, s_unit_comm = short_stack.pop(0)
                        matched = min(remaining, s_qty)

                        # Short PnL: (Entry - Exit) * qty
                        gross_pnl = (s_price - price) * matched
                        # Commission: Entry part + Exit part
                        # Entry part: s_unit_comm * matched
                        # Exit part: unit_comm * matched
                        trade_comm = (s_unit_comm + unit_comm) * matched
                        net_pnl = gross_pnl - trade_comm

                        closed_trades.append({"pnl": net_pnl, "strategy": s_strat})

                        remaining -= matched
                        if s_qty > matched:
                            short_stack.insert(
                                0, (s_qty - matched, s_price, s_strat, s_unit_comm)
                            )

                    if remaining > 0:
                        long_stack.append((remaining, price, strategy_id, unit_comm))

                elif side == "sell":
                    # Close Long
                    remaining = qty
                    while remaining > 0 and long_stack:
                        l_qty, l_price, l_strat, l_unit_comm = long_stack.pop(0)
                        matched = min(remaining, l_qty)

                        # Long PnL: (Exit - Entry) * qty
                        gross_pnl = (price - l_price) * matched
                        trade_comm = (l_unit_comm + unit_comm) * matched
                        net_pnl = gross_pnl - trade_comm

                        closed_trades.append({"pnl": net_pnl, "strategy": l_strat})

                        remaining -= matched
                        if l_qty > matched:
                            long_stack.insert(
                                0, (l_qty - matched, l_price, l_strat, l_unit_comm)
                            )

                    if remaining > 0:
                        short_stack.append((remaining, price, strategy_id, unit_comm))

                # Handle 'short' and 'cover' if they exist separately (Broker uses buy/sell/short/cover?)
                # Broker uses: buy, sell, short, cover?
                # Let's check Broker._execute_trade logic.
                # Broker maps: 'buy' (long open), 'sell' (long close), 'short' (short open), 'cover' (short close).
                # But reporting.py currently only handles 'buy' and 'sell'.
                # I should add 'short' and 'cover'.

                elif side == "short":
                    # Open Short
                    remaining = qty
                    # Should we check for existing longs? (Reversal?)
                    # For simplicity, assume strict separation or FIFO.
                    # If we have longs, 'short' usually means 'sell to close' + 'sell to open'?
                    # But Router sends 'sell' to close long, and 'short' to open short.
                    # So 'short' should just add to short_stack.

                    # Wait, if we have longs, 'short' command might be error if not flat?
                    # But assuming Router handles it (Router closes first).
                    short_stack.append((qty, price, strategy_id, unit_comm))

                elif side == "cover":
                    # Close Short (Buy to Cover)
                    # Match against short_stack
                    remaining = qty
                    while remaining > 0 and short_stack:
                        s_qty, s_price, s_strat, s_unit_comm = short_stack.pop(0)
                        matched = min(remaining, s_qty)

                        gross_pnl = (s_price - price) * matched
                        trade_comm = (s_unit_comm + unit_comm) * matched
                        net_pnl = gross_pnl - trade_comm

                        closed_trades.append({"pnl": net_pnl, "strategy": s_strat})

                        remaining -= matched
                        if s_qty > matched:
                            short_stack.insert(
                                0, (s_qty - matched, s_price, s_strat, s_unit_comm)
                            )

                    # If remaining > 0, we are buying more than we are short? -> Net Long?
                    if remaining > 0:
                        long_stack.append((remaining, price, strategy_id, unit_comm))

        if not closed_trades:
            return {"TotalTrades": 0, "WinRate": 0.0, "ProfitFactor": 0.0}

        # 1. Global Metrics
        all_pnls = [t["pnl"] for t in closed_trades]
        wins = [p for p in all_pnls if p > 0]
        losses = [p for p in all_pnls if p <= 0]

        win_rate = len(wins) / len(all_pnls)
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss != 0 else float("inf")

        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0

        # Expectancy = (WinRate * AvgWin) - (LossRate * AvgLoss)
        # Note: avg_loss is negative, so we add it if using the formula (Win% * AvgWin) + (Loss% * AvgLoss)
        # Or (Win% * AvgWin) - (Loss% * abs(AvgLoss))
        loss_rate = 1 - win_rate
        expectancy = (win_rate * avg_win) + (loss_rate * avg_loss)

        metrics = {
            "TotalTrades": len(all_pnls),
            "WinRate": win_rate,
            "ProfitFactor": profit_factor,
            "Expectancy": expectancy,
            "AvgWin": avg_win,
            "AvgLoss": avg_loss,
        }

        # 2. Per Strategy Metrics
        strat_map = {}
        for t in closed_trades:
            s = t["strategy"]
            if s not in strat_map:
                strat_map[s] = []
            strat_map[s].append(t["pnl"])

        for s, pnls in strat_map.items():
            s_wins = [p for p in pnls if p > 0]
            s_losses = [p for p in pnls if p <= 0]
            s_wr = len(s_wins) / len(pnls)
            s_pf = (
                sum(s_wins) / abs(sum(s_losses)) if sum(s_losses) != 0 else float("inf")
            )
            s_total = sum(pnls)

            metrics[f"Strat_{s}_Trades"] = len(pnls)
            metrics[f"Strat_{s}_WinRate"] = s_wr
            metrics[f"Strat_{s}_ProfitFactor"] = s_pf
            metrics[f"Strat_{s}_NetPnL"] = s_total

        return metrics

    def _save_report_text(
        self, metrics: Dict[str, Any], metadata: Dict[str, Any] = None
    ):
        # Metrics Translation Map
        METRIC_NAMES = {
            "CAGR": "CAGR (年化收益率)",
            "MaxDrawdownPct": "Max Drawdown % (最大回撤率)",
            "MaxDrawdownAmount": "Max Drawdown $ (最大回撤金额)",
            "AvgMonthlyReturn": "Avg Monthly Return (月均收益率)",
            "SharpeRatio": "Sharpe Ratio (夏普比率)",
            "EndEquity": "End Equity (最终净值)",
            "TotalReturn": "Total Return (总收益率)",
            "TotalTrades": "Total Trades (总交易次数)",
            "WinRate": "Win Rate (胜率)",
            "ProfitFactor": "Profit Factor (盈亏比)",
            "Expectancy": "Expectancy (期望值)",
            "AvgWin": "Avg Win (平均盈利)",
            "AvgLoss": "Avg Loss (平均亏损)",
        }

        path = os.path.join(self.output_dir, "report.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("Backtest Report (回测报告)\n")
            f.write("==========================\n\n")

            if metadata:
                f.write("Configuration (配置信息):\n")
                for k, v in metadata.items():
                    f.write(f"{k}: {v}\n")
                f.write("\nMetrics (核心指标):\n")

            for k, v in metrics.items():
                # Handle strategy specific metrics dynamically
                display_key = METRIC_NAMES.get(k, k)

                if isinstance(v, float):
                    f.write(f"{display_key:<40}: {v:.4f}\n")
                else:
                    f.write(f"{display_key:<40}: {v}\n")

    def _plot_equity(self, equity_curve: pd.DataFrame):
        try:
            # Create a figure with 4 subplots
            fig = plt.figure(figsize=(16, 12))
            gs = fig.add_gridspec(4, 1, height_ratios=[2, 1, 1, 1])

            ax1 = fig.add_subplot(gs[0])
            ax2 = fig.add_subplot(gs[1], sharex=ax1)
            ax3 = fig.add_subplot(gs[2], sharex=ax1)
            ax4 = fig.add_subplot(gs[3], sharex=ax1)

            # Ensure font supports basic text
            plt.rcParams["font.sans-serif"] = ["SimHei", "Arial", "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False

            # Plot 1: Equity Curve
            ax1.plot(
                equity_curve.index,
                equity_curve["equity"],
                label="Total Equity (总净值)",
                color="blue",
                linewidth=1.5,
            )
            ax1.set_title("Equity Curve (净值曲线)", fontsize=12, fontweight="bold")
            ax1.set_ylabel("Value (USDT)")
            ax1.legend(loc="upper left")
            ax1.grid(True, which="both", linestyle="--", alpha=0.6)

            # Plot 2: Drawdown
            rolling_max = equity_curve["equity"].cummax()
            drawdown = (equity_curve["equity"] - rolling_max) / rolling_max

            ax2.fill_between(
                drawdown.index, drawdown, 0, color="red", alpha=0.3, label="Drawdown"
            )
            ax2.plot(drawdown.index, drawdown, color="red", linewidth=1)
            ax2.set_title("Drawdown % (回撤率)")
            ax2.set_ylabel("Percentage")
            ax2.axhline(0, color="black", linewidth=0.5)
            ax2.grid(True, which="both", linestyle="--", alpha=0.6)

            # Plot 3: Daily Returns
            returns = equity_curve["equity"].pct_change().fillna(0)
            colors = ["green" if x >= 0 else "red" for x in returns]
            ax3.bar(
                returns.index, returns, color=colors, alpha=0.7, label="Daily Return"
            )
            ax3.set_title("Daily Returns (日收益率)")
            ax3.set_ylabel("Return %")
            ax3.grid(True, axis="y", linestyle="--", alpha=0.6)

            # Plot 4: Cash vs Position (Asset Allocation)
            # Assuming 'cash' column exists, otherwise infer from equity
            if "cash" in equity_curve.columns:
                cash = equity_curve["cash"]
                # Position value = Equity - Cash
                position_val = equity_curve["equity"] - cash

                ax4.stackplot(
                    equity_curve.index,
                    [cash, position_val],
                    labels=["Cash (现金)", "Position Value (持仓市值)"],
                    colors=["lightgray", "orange"],
                    alpha=0.6,
                )
                ax4.set_title("Asset Allocation (资产分布)")
                ax4.set_ylabel("Value (USDT)")
                ax4.legend(loc="upper left")
                ax4.grid(True, which="both", linestyle="--", alpha=0.6)

            ax4.set_xlabel("Date")

            plt.tight_layout()
            output_path = os.path.join(self.output_dir, "equity.png")
            plt.savefig(output_path, dpi=300)
            print(f"Plot saved to: {output_path}")
            plt.close()
        except Exception as e:
            print(f"Error saving plot: {e}")
