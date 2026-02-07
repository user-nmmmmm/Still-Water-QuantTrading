from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from core.portfolio import Portfolio
import pandas as pd
import random


@dataclass
class Order:
    symbol: str
    side: str
    qty: float
    order_type: str = (
        "market"  # market, limit, stop (currently only market implemented effectively)
    )
    price: Optional[float] = None  # For limit/stop, or expected price
    timestamp: Any = None
    strategy_id: str = "Manual"
    slippage: float = 0.0  # Expected slippage rate
    stop_loss: float = 0.0
    take_profit: float = 0.0
    exit_reason: str = "signal"  # signal, stop, takeprofit, reverse


class Broker:
    def __init__(
        self,
        portfolio: Portfolio,
        commission_rate: float = 0.001,
        slippage: float = 0.0,
        random_slip: bool = False,
    ):
        self.portfolio = portfolio
        self.commission_rate = commission_rate
        self.slippage = slippage
        self.random_slip = random_slip
        self.trades = []  # List to store executed trades
        self.pending_orders: List[Order] = []

    def submit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float = None,
        timestamp: Any = None,
        slippage: float = 0.0,
        strategy_id: str = "Manual",
        exit_reason: str = "signal",
    ) -> None:
        """
        Submit an order to be executed at the next available opportunity (Next Bar Open).
        """
        if qty <= 0:
            print(f"Order rejected: Quantity must be positive. {symbol} {side} {qty}")
            return

        order = Order(
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            timestamp=timestamp,
            slippage=slippage,
            strategy_id=strategy_id,
            exit_reason=exit_reason,
        )
        self.pending_orders.append(order)

    def process_orders(self, current_bar: Dict[str, pd.Series]) -> List[Dict]:
        """
        Process pending orders using the current bar's data (Open price).
        current_bar: dict where key is symbol, value is the bar data (Series with open, high, low, close)
        """
        executed_trades = []
        remaining_orders = []

        for order in self.pending_orders:
            if order.symbol not in current_bar:
                remaining_orders.append(order)
                continue

            bar_data = current_bar[order.symbol]
            # Execute at Open
            exec_price = bar_data["open"]
            exec_time = bar_data.name  # Timestamp of the bar

            trade = self._execute_trade(order, exec_price, exec_time)
            if trade:
                executed_trades.append(trade)
            else:
                # If failed (e.g. insufficient funds), we discard it for now or log it
                pass

        self.pending_orders = remaining_orders
        return executed_trades

    def _execute_trade(
        self, order: Order, price: float, timestamp: Any
    ) -> Optional[Dict]:
        """
        Internal execution logic.
        """
        # Apply Slippage
        # Fill Price = Open * (1 ± slip)
        # Check global slippage config if order doesn't specify it
        base_slip = order.slippage if order.slippage > 0 else self.slippage

        if self.random_slip and base_slip > 0:
            # Random slippage between 0 and base_slip
            slip_rate = random.uniform(0, base_slip)
        else:
            # Fixed slippage (worst case)
            slip_rate = base_slip

        if order.side in ["buy", "cover"]:
            fill_price = price * (1 + slip_rate)
            slip_val = price * slip_rate
            slip_dir = "positive"  # Costlier
        else:  # sell, short
            fill_price = price * (1 - slip_rate)
            slip_val = price * slip_rate
            slip_dir = "negative"  # Cheaper (less profit)

        # Calculate Commission
        # Commission is typically on Notional Value
        value = order.qty * fill_price
        commission = value * self.commission_rate

        # Determine qty_delta for portfolio
        if order.side == "buy":
            qty_delta = order.qty
        elif order.side == "sell":
            qty_delta = -order.qty
        elif order.side == "short":
            qty_delta = -order.qty
        elif order.side == "cover":
            qty_delta = order.qty
        else:
            return None

        # Portfolio Check (Simplified)
        current_pos = self.portfolio.get_position(order.symbol)

        # Validation for Sell/Cover
        if order.side == "sell":
            if current_pos["qty"] < order.qty:
                # In a real system we might partial fill. Here we reject or clip.
                # Given it's a backtest, we might want to just close what we have?
                # Let's clip it to available qty to avoid errors.
                actual_qty = max(0, current_pos["qty"])
                if actual_qty == 0:
                    return None

                # Recalculate if clipped
                if actual_qty != order.qty:
                    qty_delta = -actual_qty
                    value = actual_qty * fill_price
                    commission = value * self.commission_rate
                    order.qty = actual_qty

        # Update Portfolio
        self.portfolio.update_position(order.symbol, qty_delta, fill_price, commission)

        trade_record = {
            "signal_time": order.timestamp,  # When it was submitted
            "fill_time": timestamp,  # When it was filled
            "symbol": order.symbol,
            "side": order.side,
            "qty": order.qty,
            "fill_price": fill_price,
            "commission": commission,
            "slip": slip_val,  # Absolute value of slip
            "slip_dir": slip_dir,
            "strategy_id": order.strategy_id,
            "exit_reason": getattr(
                order, "exit_reason", "signal"
            ),  # We might need to pass this
        }
        self.trades.append(trade_record)

        # Log to console as requested
        print(
            f"[Trade] {timestamp} {order.symbol} {order.side} {order.qty} @ {fill_price:.2f} "
            f"(Slip: {slip_val:.4f} {slip_dir}, Comm: {commission:.4f}, Reason: {trade_record['exit_reason']}, "
            f"Signal: {order.timestamp})"
        )

        return trade_record

    # Keep compatibility if needed, or remove.
    # Since we are refactoring, I will remove execute_order to force updates.
