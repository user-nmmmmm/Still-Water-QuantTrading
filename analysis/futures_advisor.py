"""
合约交易建议模块 (Futures Trading Advisor)

基于币安现货/合约市场数据，综合多维度技术指标，
为每个币种生成：多空方向、入场时机、止盈止损、盈亏比建议。

参考：skills/binance/SKILL.md（Binance Skills Hub）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from core.data_fetcher import DataFetcher
from core.indicators import Indicators

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class TradingAdvice:
    """单个币种的合约交易建议"""
    symbol: str
    direction: str          # "LONG" | "SHORT" | "NEUTRAL"
    signal_strength: float  # 0.0 ~ 1.0
    current_price: float

    entry_price: float
    entry_note: str         # 入场时机说明

    take_profit: float
    stop_loss: float

    risk_reward_ratio: float  # 盈亏比 = |TP - Entry| / |SL - Entry|
    potential_profit_pct: float
    potential_loss_pct: float

    timeframe: str
    timestamp: str

    # 指标快照
    indicators: Dict[str, float] = field(default_factory=dict)
    reasoning: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        direction_emoji = "🟢 多" if self.direction == "LONG" else ("🔴 空" if self.direction == "SHORT" else "⚪ 观望")
        lines = [
            f"{'=' * 55}",
            f"  {self.symbol}  |  {direction_emoji}  |  信号强度: {self.signal_strength:.0%}",
            f"{'=' * 55}",
            f"  当前价格  : {self.current_price:.4f}",
            f"  建议入场  : {self.entry_price:.4f}   ({self.entry_note})",
            f"  止盈目标  : {self.take_profit:.4f}   (+{self.potential_profit_pct:.2f}%)",
            f"  止损位置  : {self.stop_loss:.4f}   (-{self.potential_loss_pct:.2f}%)",
            f"  盈亏比    : {self.risk_reward_ratio:.2f} : 1",
            f"  时间框架  : {self.timeframe}",
            f"  分析时间  : {self.timestamp}",
        ]
        if self.indicators:
            lines.append(f"  --- 关键指标 ---")
            for k, v in self.indicators.items():
                lines.append(f"  {k:<12}: {v:.2f}")
        if self.reasoning:
            lines.append(f"  --- 信号依据 ---")
            for r in self.reasoning:
                lines.append(f"  • {r}")
        lines.append(f"{'=' * 55}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core Advisor
# ---------------------------------------------------------------------------

class FuturesTradingAdvisor:
    """
    合约交易建议引擎

    流程：
    1. 通过 ccxt / Binance API 拉取 K 线数据
    2. 计算多维技术指标（趋势、动量、波动率、成交量）
    3. 综合打分生成多空方向
    4. 用 ATR 动态计算止盈止损
    5. 输出结构化的 TradingAdvice
    """

    # 默认分析的热门合约币种
    DEFAULT_SYMBOLS = [
        "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT",
        "XRP/USDT", "DOGE/USDT", "ADA/USDT", "AVAX/USDT",
    ]

    def __init__(
        self,
        timeframe: str = "4h",
        lookback: int = 200,
        atr_multiplier_tp: float = 3.0,
        atr_multiplier_sl: float = 1.5,
        min_rr_ratio: float = 1.5,
        proxy_url: Optional[str] = "http://127.0.0.1:7897",
    ):
        """
        Parameters
        ----------
        timeframe        : K线周期，如 '1h', '4h', '1d'
        lookback         : 拉取多少根 K 线
        atr_multiplier_tp: 止盈为 N 倍 ATR（相对入场价）
        atr_multiplier_sl: 止损为 N 倍 ATR（相对入场价）
        min_rr_ratio     : 最低盈亏比要求，低于此值不出信号
        proxy_url        : 代理地址（境内访问币安时需要）
        """
        self.timeframe = timeframe
        self.lookback = lookback
        self.atr_multiplier_tp = atr_multiplier_tp
        self.atr_multiplier_sl = atr_multiplier_sl
        self.min_rr_ratio = min_rr_ratio
        self.fetcher = DataFetcher(proxy_url=proxy_url)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, symbols: Optional[List[str]] = None) -> List[TradingAdvice]:
        """
        分析一组币种，返回交易建议列表（按信号强度降序）。
        """
        if symbols is None:
            symbols = self.DEFAULT_SYMBOLS

        advices: List[TradingAdvice] = []
        for sym in symbols:
            try:
                advice = self._analyze_single(sym)
                if advice:
                    advices.append(advice)
            except Exception as e:
                logger.warning(f"[{sym}] 分析失败: {e}")

        advices.sort(key=lambda x: x.signal_strength, reverse=True)
        return advices

    def top_picks(self, n: int = 3, symbols: Optional[List[str]] = None) -> List[TradingAdvice]:
        """返回信号最强的 n 个交易建议（多空各取，去掉观望）"""
        all_advices = self.analyze(symbols)
        actionable = [a for a in all_advices if a.direction != "NEUTRAL"]
        return actionable[:n]

    # ------------------------------------------------------------------
    # Internal Analysis
    # ------------------------------------------------------------------

    def _analyze_single(self, symbol: str) -> Optional[TradingAdvice]:
        """对单个币种进行完整技术分析并生成建议。"""
        df = self._fetch(symbol)
        if df is None or len(df) < 50:
            logger.warning(f"[{symbol}] 数据不足，跳过")
            return None

        df = self._compute_indicators(df)
        last = df.iloc[-1]
        current_price = float(last["close"])
        atr = float(last.get("ATR_14", current_price * 0.02))

        direction, score, reasoning = self._score_direction(df)
        entry_price, entry_note = self._calc_entry(df, direction, atr)
        tp, sl = self._calc_tp_sl(entry_price, direction, atr)

        # 盈亏比
        profit_dist = abs(tp - entry_price)
        loss_dist = abs(entry_price - sl)
        rr = profit_dist / loss_dist if loss_dist > 0 else 0.0

        if rr < self.min_rr_ratio and direction != "NEUTRAL":
            # 盈亏比不达标，调整 TP 以满足最低要求
            if direction == "LONG":
                tp = entry_price + loss_dist * self.min_rr_ratio
            else:
                tp = entry_price - loss_dist * self.min_rr_ratio
            profit_dist = abs(tp - entry_price)
            rr = profit_dist / loss_dist if loss_dist > 0 else 0.0

        profit_pct = profit_dist / entry_price * 100
        loss_pct = loss_dist / entry_price * 100

        indicators_snap = {
            "RSI_14": round(float(last.get("RSI_14", np.nan)), 2),
            "MACD": round(float(last.get("MACD", np.nan)), 4),
            "ADX_14": round(float(last.get("ADX_14", np.nan)), 2),
            "ATR_14": round(atr, 4),
            "BB_POS%": round(float(last.get("BB_POS", np.nan)), 2),
        }

        timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")

        return TradingAdvice(
            symbol=symbol,
            direction=direction,
            signal_strength=round(score, 3),
            current_price=current_price,
            entry_price=round(entry_price, 6),
            entry_note=entry_note,
            take_profit=round(tp, 6),
            stop_loss=round(sl, 6),
            risk_reward_ratio=round(rr, 2),
            potential_profit_pct=round(profit_pct, 2),
            potential_loss_pct=round(loss_pct, 2),
            timeframe=self.timeframe,
            timestamp=timestamp,
            indicators=indicators_snap,
            reasoning=reasoning,
        )

    def _fetch(self, symbol: str) -> Optional[pd.DataFrame]:
        """通过 ccxt 拉取指定币种的 K 线数据。"""
        try:
            import ccxt

            proxies = None
            if self.fetcher.proxy_url:
                proxies = {
                    "http": self.fetcher.proxy_url,
                    "https": self.fetcher.proxy_url,
                }

            exchange = ccxt.binance({
                "enableRateLimit": True,
                "proxies": proxies,
            })
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=self.timeframe, limit=self.lookback)
            if not ohlcv:
                return None

            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            return df

        except ImportError:
            logger.error("ccxt 未安装，请运行: pip install ccxt")
            return None
        except Exception as e:
            logger.error(f"[{symbol}] 数据获取失败: {e}")
            return None

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算所有需要的技术指标。"""
        # 趋势
        df["SMA_20"] = Indicators.SMA(df["close"], 20)
        df["SMA_50"] = Indicators.SMA(df["close"], 50)
        df["EMA_12"] = Indicators.EMA(df["close"], 12)
        df["EMA_26"] = Indicators.EMA(df["close"], 26)

        # 动量
        df["RSI_14"] = Indicators.RSI(df["close"], 14)
        macd, macd_sig, macd_hist = Indicators.MACD(df["close"])
        df["MACD"] = macd
        df["MACD_SIGNAL"] = macd_sig
        df["MACD_HIST"] = macd_hist

        # 波动率
        df["ATR_14"] = Indicators.ATR(df, 14)
        bb_upper, bb_mid, bb_lower = Indicators.BBANDS(df["close"], 20, 2)
        df["BB_UPPER"] = bb_upper
        df["BB_LOWER"] = bb_lower
        df["BB_MID"] = bb_mid
        # 价格在布林带中的位置 (0=下轨, 100=上轨)
        bb_range = (bb_upper - bb_lower).replace(0, np.nan)
        df["BB_POS"] = (df["close"] - bb_lower) / bb_range * 100

        # 趋势强度
        df["ADX_14"] = Indicators.ADX(df, 14)

        # 成交量比率（当前量 / 20日均量）
        df["VOL_RATIO"] = df["volume"] / df["volume"].rolling(20).mean()

        return df

    def _score_direction(self, df: pd.DataFrame) -> Tuple[str, float, List[str]]:
        """
        综合多个指标信号打分，输出方向和信号强度。

        每个信号得 +1（多）或 -1（空）分，最后归一化到 [0,1]。
        """
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else last

        bull_score = 0
        bear_score = 0
        reasoning: List[str] = []

        # 1. 均线排列（趋势基础）
        price = float(last["close"])
        sma20 = float(last.get("SMA_20", price))
        sma50 = float(last.get("SMA_50", price))

        if price > sma20 > sma50:
            bull_score += 2
            reasoning.append(f"价格 > SMA20 > SMA50，多头排列")
        elif price < sma20 < sma50:
            bear_score += 2
            reasoning.append(f"价格 < SMA20 < SMA50，空头排列")

        # 2. RSI 动量
        rsi = float(last.get("RSI_14", 50))
        if rsi > 55 and rsi < 75:
            bull_score += 1
            reasoning.append(f"RSI={rsi:.1f}，动量偏多")
        elif rsi < 45 and rsi > 25:
            bear_score += 1
            reasoning.append(f"RSI={rsi:.1f}，动量偏空")
        elif rsi >= 75:
            bear_score += 1
            reasoning.append(f"RSI={rsi:.1f}，超买预警")
        elif rsi <= 25:
            bull_score += 1
            reasoning.append(f"RSI={rsi:.1f}，超卖反弹机会")

        # 3. MACD 金叉/死叉
        macd_hist = float(last.get("MACD_HIST", 0))
        prev_macd_hist = float(prev.get("MACD_HIST", 0))
        macd_val = float(last.get("MACD", 0))

        if macd_hist > 0 and prev_macd_hist <= 0:
            bull_score += 2
            reasoning.append("MACD 金叉，动能转多")
        elif macd_hist < 0 and prev_macd_hist >= 0:
            bear_score += 2
            reasoning.append("MACD 死叉，动能转空")
        elif macd_hist > 0 and macd_val > 0:
            bull_score += 1
            reasoning.append("MACD 柱状图正值且扩张")
        elif macd_hist < 0 and macd_val < 0:
            bear_score += 1
            reasoning.append("MACD 柱状图负值且扩张")

        # 4. 布林带位置
        bb_pos = float(last.get("BB_POS", 50))
        if bb_pos > 80:
            bear_score += 1
            reasoning.append(f"价格接近布林上轨 ({bb_pos:.0f}%)，注意回调风险")
        elif bb_pos < 20:
            bull_score += 1
            reasoning.append(f"价格接近布林下轨 ({bb_pos:.0f}%)，关注超卖反弹")

        # 5. ADX 趋势强度（过滤震荡市）
        adx = float(last.get("ADX_14", 20))
        if adx > 25:
            # 强趋势，加权方向分
            if bull_score > bear_score:
                bull_score += 1
                reasoning.append(f"ADX={adx:.1f} 趋势强劲，多信号增强")
            elif bear_score > bull_score:
                bear_score += 1
                reasoning.append(f"ADX={adx:.1f} 趋势强劲，空信号增强")
        else:
            reasoning.append(f"ADX={adx:.1f} 趋势较弱，信号可靠性下降")

        # 6. 成交量确认
        vol_ratio = float(last.get("VOL_RATIO", 1.0))
        if vol_ratio > 1.5:
            if bull_score >= bear_score:
                bull_score += 1
                reasoning.append(f"成交量放大 {vol_ratio:.1f}x，多头量能充足")
            else:
                bear_score += 1
                reasoning.append(f"成交量放大 {vol_ratio:.1f}x，空头量能充足")

        # 汇总
        total = bull_score + bear_score
        if total == 0:
            return "NEUTRAL", 0.0, ["无明显信号"]

        if bull_score > bear_score:
            direction = "LONG"
            strength = bull_score / total
        elif bear_score > bull_score:
            direction = "SHORT"
            strength = bear_score / total
        else:
            direction = "NEUTRAL"
            strength = 0.5

        # 信号强度阈值（低于 60% 视为观望）
        if strength < 0.60:
            direction = "NEUTRAL"
            reasoning.append(f"多空分歧（多{bull_score}:空{bear_score}），建议观望")

        return direction, strength, reasoning

    def _calc_entry(
        self, df: pd.DataFrame, direction: str, atr: float
    ) -> Tuple[float, str]:
        """
        计算建议入场价和入场时机说明。

        - LONG：等回撤到支撑位（EMA12 或 BB中轨），或突破确认后市价
        - SHORT：等反弹到阻力位（EMA12 或 BB中轨），或跌破确认后市价
        """
        last = df.iloc[-1]
        price = float(last["close"])
        ema12 = float(last.get("EMA_12", price))
        bb_mid = float(last.get("BB_MID", price))
        atr_val = atr if atr > 0 else price * 0.01

        if direction == "LONG":
            # 支撑位：EMA12 与 BB中轨 取较高者
            support = max(ema12, bb_mid)
            if price > support * 1.005:
                # 价格明显高于支撑，建议回调入场
                entry = round(support * 1.002, 6)
                note = f"等回调至 EMA12/BB中轨支撑区 (~{entry:.4f})"
            else:
                # 已在支撑附近，市价入场
                entry = price
                note = "已在支撑位附近，可市价入场"
        elif direction == "SHORT":
            # 阻力位：EMA12 与 BB中轨 取较低者
            resistance = min(ema12, bb_mid)
            if price < resistance * 0.995:
                # 价格明显低于阻力，建议反弹入场
                entry = round(resistance * 0.998, 6)
                note = f"等反弹至 EMA12/BB中轨阻力区 (~{entry:.4f})"
            else:
                # 已在阻力附近，市价入场
                entry = price
                note = "已在阻力位附近，可市价入场"
        else:
            entry = price
            note = "无方向，观望为主"

        return entry, note

    def _calc_tp_sl(
        self, entry_price: float, direction: str, atr: float
    ) -> Tuple[float, float]:
        """
        基于 ATR 动态计算止盈止损位。

        TP = entry ± atr_multiplier_tp * ATR
        SL = entry ∓ atr_multiplier_sl * ATR
        """
        atr_val = atr if atr > 0 else entry_price * 0.01

        if direction == "LONG":
            tp = entry_price + self.atr_multiplier_tp * atr_val
            sl = entry_price - self.atr_multiplier_sl * atr_val
        elif direction == "SHORT":
            tp = entry_price - self.atr_multiplier_tp * atr_val
            sl = entry_price + self.atr_multiplier_sl * atr_val
        else:
            tp = entry_price * 1.05
            sl = entry_price * 0.95

        return tp, sl


# ---------------------------------------------------------------------------
# Standalone runner (用于直接执行 python -m analysis.futures_advisor)
# ---------------------------------------------------------------------------

def run_advisor(
    symbols: Optional[List[str]] = None,
    timeframe: str = "4h",
    lookback: int = 200,
    top_n: int = 5,
    proxy_url: Optional[str] = "http://127.0.0.1:7897",
) -> List[TradingAdvice]:
    advisor = FuturesTradingAdvisor(
        timeframe=timeframe,
        lookback=lookback,
        proxy_url=proxy_url,
    )

    print(f"\n{'=' * 55}")
    print(f"  合约交易建议系统  |  周期: {timeframe}  |  分析中...")
    print(f"{'=' * 55}\n")

    target_symbols = symbols or FuturesTradingAdvisor.DEFAULT_SYMBOLS
    print(f"分析币种: {', '.join(target_symbols)}\n")

    advices = advisor.analyze(target_symbols)

    if not advices:
        print("未获取到任何交易建议，请检查网络或数据源。")
        return []

    actionable = [a for a in advices if a.direction != "NEUTRAL"]
    neutral = [a for a in advices if a.direction == "NEUTRAL"]

    print(f"\n>>> 有效信号 ({len(actionable)} 个):\n")
    for advice in actionable[:top_n]:
        print(advice)
        print()

    if neutral:
        neutral_syms = ", ".join(a.symbol for a in neutral)
        print(f">>> 观望币种: {neutral_syms}\n")

    # 汇总表
    print("\n--- 信号汇总 ---")
    header = f"{'币种':<12} {'方向':<8} {'信号强度':<10} {'入场价':<14} {'止盈':<14} {'止损':<14} {'盈亏比':<8}"
    print(header)
    print("-" * len(header))
    for a in advices:
        direction_str = {"LONG": "多 ▲", "SHORT": "空 ▼", "NEUTRAL": "观望 -"}[a.direction]
        print(
            f"{a.symbol:<12} {direction_str:<8} {a.signal_strength:<10.0%} "
            f"{a.entry_price:<14.4f} {a.take_profit:<14.4f} {a.stop_loss:<14.4f} "
            f"{a.risk_reward_ratio:<8.2f}"
        )
    print()

    return advices


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="合约交易建议 - Futures Trading Advisor")
    parser.add_argument("--symbols", nargs="+", default=None,
                        help="分析的币种列表，如 BTC/USDT ETH/USDT")
    parser.add_argument("--timeframe", default="4h",
                        choices=["15m", "30m", "1h", "4h", "1d"],
                        help="K线周期 (默认: 4h)")
    parser.add_argument("--lookback", type=int, default=200,
                        help="拉取K线数量 (默认: 200)")
    parser.add_argument("--top", type=int, default=5,
                        help="显示信号最强的前N个建议 (默认: 5)")
    parser.add_argument("--proxy", default="http://127.0.0.1:7897",
                        help="代理地址 (默认: http://127.0.0.1:7897)，设为 none 禁用")
    args = parser.parse_args()

    proxy = None if args.proxy.lower() == "none" else args.proxy
    run_advisor(
        symbols=args.symbols,
        timeframe=args.timeframe,
        lookback=args.lookback,
        top_n=args.top,
        proxy_url=proxy,
    )
