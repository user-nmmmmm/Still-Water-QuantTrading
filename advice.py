#!/usr/bin/env python3
"""
合约交易建议入口脚本 (Futures Trading Advice Entry Point)

用法示例:
  python advice.py
  python advice.py --timeframe 1h --top 3
  python advice.py --symbols BTC/USDT ETH/USDT SOL/USDT
  python advice.py --timeframe 1d --proxy none

参考: analysis/futures_advisor.py
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from analysis.futures_advisor import run_advisor
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="合约交易建议系统 - 基于 Binance 市场数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python advice.py                              # 默认分析 8 个主流合约，4h 周期
  python advice.py --timeframe 1h --top 3      # 1小时周期，展示前3个信号
  python advice.py --symbols BTC/USDT ETH/USDT # 只分析 BTC 和 ETH
  python advice.py --proxy none                 # 不使用代理

输出内容:
  - 币种名称
  - 多空方向 (LONG / SHORT / NEUTRAL)
  - 信号强度 (百分比)
  - 建议入场价 + 入场时机
  - 止盈目标价
  - 止损价格
  - 盈亏比
        """,
    )
    parser.add_argument(
        "--symbols", nargs="+", default=None,
        help="分析的币种，格式 BASE/QUOTE，如: BTC/USDT ETH/USDT (默认: 8个主流币)",
    )
    parser.add_argument(
        "--timeframe", default="4h",
        choices=["15m", "30m", "1h", "4h", "1d"],
        help="K线周期 (默认: 4h)",
    )
    parser.add_argument(
        "--lookback", type=int, default=200,
        help="历史K线数量 (默认: 200)",
    )
    parser.add_argument(
        "--top", type=int, default=5,
        help="展示信号最强的前N个建议 (默认: 5)",
    )
    parser.add_argument(
        "--proxy", default="http://127.0.0.1:7897",
        help="HTTP代理地址 (默认: http://127.0.0.1:7897)，设为 none 禁用",
    )

    args = parser.parse_args()
    proxy = None if args.proxy.lower() == "none" else args.proxy

    run_advisor(
        symbols=args.symbols,
        timeframe=args.timeframe,
        lookback=args.lookback,
        top_n=args.top,
        proxy_url=proxy,
    )
