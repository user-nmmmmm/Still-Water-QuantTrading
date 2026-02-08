import ccxt
import logging
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
from core.portfolio import Portfolio
from core.broker import Order, OrderStatus, OrderType

logger = logging.getLogger(__name__)


class LiveBroker:
    """
    Broker implementation for Live Trading using CCXT.
    Interacts directly with the exchange.
    """

    def __init__(
        self,
        portfolio: Portfolio,
        exchange_id: str = "binance",
        api_key: str = None,
        secret: str = None,
        sandbox: bool = False,
    ):
        self.portfolio = portfolio
        self.exchange_id = exchange_id

        # Initialize Exchange
        exchange_class = getattr(ccxt, exchange_id)
        config = {
            "apiKey": api_key or os.getenv("EXCHANGE_API_KEY"),
            "secret": secret or os.getenv("EXCHANGE_SECRET"),
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",  # Default to futures for most quant strategies? Or spot?
                # Let's default to spot for safety unless configured otherwise.
                # Actually, most trend strategies here assume shorting, so Futures is better.
                # But let's start with SPOT/Default and allow config.
            },
        }

        self.exchange = exchange_class(config)
        if sandbox:
            self.exchange.set_sandbox_mode(True)
            logger.info(f"Initialized {exchange_id} in SANDBOX mode")
        else:
            logger.info(f"Initialized {exchange_id} in LIVE mode")

        self.trades = []

    def sync(self):
        """
        Sync Portfolio state with Exchange (Balance & Positions).
        """
        try:
            # 1. Fetch Balance
            balance = self.exchange.fetch_balance()

            # Update Cash (USDT)
            # Assuming USDT as base currency
            total_equity = balance["total"].get("USDT", 0.0)
            free_cash = balance["free"].get("USDT", 0.0)

            self.portfolio.cash = free_cash
            # Note: Portfolio.initial_capital might need adjustment or ignore in live

            # 2. Fetch Positions (if Futures) or Balances (if Spot)
            # This is complex because CCXT unifies this differently.
            # For Spot: non-zero balances are positions.
            # For Futures: fetch_positions()

            # Let's assume Spot for simplicity first, or try fetch_positions for Futures support
            # Update self.portfolio.positions

            # Reset local positions
            self.portfolio.positions = {}

            # Iterate balances for Spot
            for currency, amount in balance["total"].items():
                if currency == "USDT":
                    continue
                if amount > 0:
                    # Construct symbol (e.g. BTC/USDT)
                    # This is a guess, strictly we should use fetch_positions for accuracy
                    symbol = f"{currency}/USDT"

                    # We need avg_price to track PnL, but exchange might not give avg entry price for spot easily
                    # For now, we just track Quantity.
                    self.portfolio.positions[symbol] = {
                        "qty": amount,
                        "avg_price": 0.0,  # Unknown for spot unless we track trades
                    }

            logger.info(f"Synced Portfolio. Cash: {self.portfolio.cash:.2f}")

        except Exception as e:
            logger.error(f"Failed to sync portfolio: {e}")

    def submit_order(
        self,
        symbol: str,
        side: str,  # 'buy', 'sell', 'short', 'cover'
        qty: float,
        price: float = None,
        order_type: str = "market",
        timestamp: Any = None,
        slippage: float = 0.0,  # Ignored in live
        strategy_id: str = "Manual",
        exit_reason: str = "signal",
    ) -> None:
        """
        Execute order on exchange.
        """
        if qty <= 0:
            logger.warning(f"Order rejected: Qty {qty} <= 0")
            return

        # Map side/type to CCXT
        # CCXT sides: 'buy', 'sell'
        # Our sides: 'buy', 'sell' (long close), 'short', 'cover' (short close)

        ccxt_side = side
        if side in ["short"]:
            ccxt_side = "sell"
        elif side in ["cover"]:
            ccxt_side = "buy"

        # If using Futures, we might need 'reduceOnly' for close orders
        params = {}
        if side in ["sell", "cover"]:
            # This is a closing trade
            # params['reduceOnly'] = True # Only for futures
            pass

        ccxt_type = order_type.lower()

        try:
            logger.info(
                f"Submitting Order: {symbol} {ccxt_side} {qty} {ccxt_type} @ {price}"
            )

            order = self.exchange.create_order(
                symbol=symbol,
                type=ccxt_type,
                side=ccxt_side,
                amount=qty,
                price=price,
                params=params,
            )

            logger.info(f"Order Executed: {order['id']} - Status: {order['status']}")

            # Record trade locally
            self.trades.append(
                {
                    "id": order["id"],
                    "symbol": symbol,
                    "side": side,
                    "qty": qty,
                    "price": order.get("average") or order.get("price") or price,
                    "timestamp": datetime.now(),
                    "strategy_id": strategy_id,
                    "exit_reason": exit_reason,
                }
            )

            # Sync portfolio after trade
            self.sync()

        except Exception as e:
            logger.error(f"Order Failed: {e}")
