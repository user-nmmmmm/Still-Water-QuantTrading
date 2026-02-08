from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from core.portfolio import Portfolio
import pandas as pd
import random


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderStatus(Enum):
    CREATED = "created"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class Order:
    symbol: str
    side: str
    qty: float
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None  # For limit/stop, or expected price
    timestamp: Any = None
    strategy_id: str = "Manual"
    slippage: float = 0.0  # Expected slippage rate
    stop_loss: float = 0.0
    take_profit: float = 0.0
    exit_reason: str = "signal"  # signal, stop, takeprofit, reverse

    # State tracking
    status: OrderStatus = OrderStatus.CREATED
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    id: str = field(
        default_factory=lambda: str(random.randint(100000, 999999))
    )  # Simple ID


class Broker:
    def __init__(
        self,
        portfolio: Portfolio,
        commission_rate: float = 0.001,
        commission_rate_maker: float = 0.0005,
        slippage: float = 0.0,
        random_slip: bool = False,
        use_impact_cost: bool = False,
    ):
        self.portfolio = portfolio
        self.commission_rate = commission_rate  # Taker
        self.commission_rate_maker = commission_rate_maker  # Maker
        self.slippage = slippage
        self.random_slip = random_slip
        self.use_impact_cost = use_impact_cost
        self.trades = []  # List to store executed trades
        self.pending_orders: List[Order] = []
        self.active_orders: List[
            Order
        ] = []  # Orders that persist across bars (Limit/Stop)

    def submit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float = None,
        order_type: str = "market",  # keeping string for compatibility, convert to Enum
        timestamp: Any = None,
        slippage: float = 0.0,
        strategy_id: str = "Manual",
        exit_reason: str = "signal",
    ) -> None:
        """
        Submit an order to be executed.
        order_type: 'market', 'limit', 'stop'
        price: Required for limit/stop orders
        """
        if qty <= 0:
            print(f"Order rejected: Quantity must be positive. {symbol} {side} {qty}")
            return

        # Map string to Enum
        otype_map = {
            "market": OrderType.MARKET,
            "limit": OrderType.LIMIT,
            "stop": OrderType.STOP,
        }
        otype = otype_map.get(order_type.lower(), OrderType.MARKET)

        if otype in [OrderType.LIMIT, OrderType.STOP] and price is None:
            print(f"Order rejected: Price required for {order_type} order.")
            return

        order = Order(
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=otype,
            price=price,
            timestamp=timestamp,
            slippage=slippage,
            strategy_id=strategy_id,
            exit_reason=exit_reason,
            status=OrderStatus.CREATED,
        )
        self.pending_orders.append(order)

    def process_orders(self, current_bar: Dict[str, pd.Series]) -> List[Dict]:
        """
        Process pending and active orders using the current bar's data (OHLCV).
        """
        executed_trades = []
        next_active_orders = []

        # Move pending to active
        for order in self.pending_orders:
            order.status = OrderStatus.SUBMITTED
            self.active_orders.append(order)
        self.pending_orders = []

        for order in self.active_orders:
            if order.symbol not in current_bar:
                next_active_orders.append(order)
                continue

            bar_data = current_bar[order.symbol]

            # OHLC Data
            open_price = bar_data["open"]
            high_price = bar_data["high"]
            low_price = bar_data["low"]
            close_price = bar_data[
                "close"
            ]  # Not strictly needed for execution check usually
            current_time = bar_data.name

            # Determine Execution Logic
            exec_price = None
            should_execute = False
            is_maker = False

            if order.order_type == OrderType.MARKET:
                exec_price = open_price
                should_execute = True

            elif order.order_type == OrderType.LIMIT:
                limit_price = order.price
                if order.side in ["buy", "cover"]:
                    # Buy Limit: Execute if Low <= Limit
                    if low_price <= limit_price:
                        should_execute = True
                        if open_price <= limit_price:
                            # Marketable at Open (Gap Down or opened below limit)
                            exec_price = open_price
                            is_maker = False
                        else:
                            # Intraday fill (touched limit)
                            exec_price = limit_price
                            is_maker = True
                else:  # sell, short
                    # Sell Limit: Execute if High >= Limit
                    if high_price >= limit_price:
                        should_execute = True
                        if open_price >= limit_price:
                            # Marketable at Open (Gap Up)
                            exec_price = open_price
                            is_maker = False
                        else:
                            # Intraday fill
                            exec_price = limit_price
                            is_maker = True

            elif order.order_type == OrderType.STOP:
                stop_price = order.price
                if order.side in ["buy", "cover"]:
                    # Buy Stop: Trigger if High >= Stop
                    if high_price >= stop_price:
                        should_execute = True
                        # Stop becomes Market -> Taker
                        exec_price = (
                            max(open_price, stop_price)
                            if open_price >= stop_price
                            else stop_price
                        )
                else:  # sell, short
                    # Sell Stop: Trigger if Low <= Stop
                    if low_price <= stop_price:
                        should_execute = True
                        # Stop becomes Market -> Taker
                        exec_price = (
                            min(open_price, stop_price)
                            if open_price <= stop_price
                            else stop_price
                        )

            if should_execute and exec_price is not None:
                # Anti-Lookahead Check
                if order.timestamp is not None and current_time <= order.timestamp:
                    # This logic assumes 'order.timestamp' is when signal was generated.
                    # 'current_time' is the bar we are executing on.
                    # Typically current_time (Bar i) > order.timestamp (Bar i-1).
                    # If they are equal, it implies signal generated at Close of Bar i, and we trying to exec at Bar i.
                    # Which is physically impossible unless we have intraday data or execute on Close.
                    # But we stick to Next-Bar execution.
                    # If Market order, keep it.
                    pass

                trade = self._execute_trade(
                    order,
                    exec_price,
                    current_time,
                    bar_data.get("volume", 0),
                    is_maker=is_maker,
                )

                if trade:
                    executed_trades.append(trade)
                    # For now, assume full fill
                    order.status = OrderStatus.FILLED
                    order.filled_qty = order.qty
                    order.avg_fill_price = exec_price
                    # Don't add to next_active_orders
                else:
                    # Execution failed (e.g. invalid move)
                    if order.order_type == OrderType.MARKET:
                        order.status = OrderStatus.REJECTED
                    else:
                        # Keep Limit/Stop orders active?
                        # If failed due to insufficient funds, maybe cancel?
                        # For simplicity, keep trying or cancel. Let's keep trying.
                        next_active_orders.append(order)
            else:
                next_active_orders.append(order)

        self.active_orders = next_active_orders
        return executed_trades

    def _execute_trade(
        self,
        order: Order,
        price: float,
        timestamp: Any,
        volume: float = 0,
        is_maker: bool = False,
    ) -> Optional[Dict]:
        """
        Internal execution logic.
        """
        # 1. Slippage Calculation
        # Fill Price = Open * (1 ± slip)
        # Check global slippage config if order doesn't specify it
        base_slip = order.slippage if order.slippage > 0 else self.slippage

        if self.random_slip and base_slip > 0:
            # Random slippage between 0 and base_slip
            slip_rate = random.uniform(0, base_slip)
        else:
            # Fixed slippage (worst case)
            slip_rate = base_slip

        # Impact Cost (Simple Model: Sqrt Law or Linear)
        # Cost = c * sigma * sqrt(OrderSize / Volume)
        # Here we use a simplified penalty if enabled
        impact_slip = 0.0
        if self.use_impact_cost and volume > 0:
            # Participation rate
            participation = order.qty / volume
            if participation > 0.01:  # Penalty if > 1% of bar volume
                impact_slip = participation * 0.1  # Arbitrary coefficient

        total_slip_rate = slip_rate + impact_slip

        if order.side in ["buy", "cover"]:
            fill_price = price * (1 + total_slip_rate)
            slip_val = price * total_slip_rate
            slip_dir = "positive"  # Costlier
        else:  # sell, short
            fill_price = price * (1 - total_slip_rate)
            slip_val = price * total_slip_rate
            slip_dir = "negative"  # Cheaper (less profit)

        # 2. Commission Calculation
        # Commission is typically on Notional Value
        value = order.qty * fill_price

        fee_rate = self.commission_rate_maker if is_maker else self.commission_rate
        commission = value * fee_rate

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
                    commission = value * fee_rate
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
            "is_maker": is_maker,
        }
        self.trades.append(trade_record)

        # Log to console as requested
        print(
            f"[Trade] {timestamp} {order.symbol} {order.side} {order.qty} @ {fill_price:.2f} "
            f"(Slip: {slip_val:.4f} {slip_dir}, Comm: {commission:.4f}, Maker: {is_maker}, "
            f"Reason: {trade_record['exit_reason']}, Signal: {order.timestamp})"
        )

        return trade_record

    # Keep compatibility if needed, or remove.
    # Since we are refactoring, I will remove execute_order to force updates.
