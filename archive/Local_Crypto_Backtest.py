
import os
import ccxt
import backtrader as bt
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import yfinance as yf

# 解决中文显示问题
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS'] # 用来正常显示中文标签
plt.rcParams['axes.unicode_minus'] = False  # 用来正常显示负号

# ================= 配置区域 =================
# 代理设置 (加速访问 Binance)
PROXY_URL = 'http://127.0.0.1:7897'  # 如无本地代理，可将 USE_PROXY 设为 False
USE_PROXY = True

# 初始资金 (USDT)
INITIAL_CASH = 1000.0

# 交易对 (CCXT 使用)
SYMBOLS_CCXT = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
# 交易对 (YFinance 使用)
SYMBOLS_YF = ['BTC-USD', 'ETH-USD', 'SOL-USD']

# 回测时间段设置
START_DATE = '2025-01-01'
END_DATE = '2025-12-31'
TIMEFRAME = '1h'  # 1d, 1h, 15m

# 交易所 (CCXT)
EXCHANGE_ID = 'binance'
FORCE_BINANCE = False  # 如果为 True，Binance 获取失败将直接报错，不再退回其他数据源

# ================= 策略定义 =================
class DynamicLeverageStrategy(bt.Strategy):
    """
    动态多币种合约策略：
    1. 交易多个币种 (BTC, ETH, SOL)
    2. 使用双均线策略生成信号
    3. 动态持仓：根据信号强度和资金情况
    4. 合约交易：使用杠杆，最大不超过 3 倍
    """
    params = (
        ('fast_period', 10),
        ('slow_period', 30),
        ('trend_period', 120), # 长期趋势周期
        ('atr_period', 14),    # ATR 周期
        ('atr_stop_mult', 2.0),# ATR 止损倍数
        ('time_stop_days', 15),# 时间止损天数 (无新高)
        ('risk_per_trade', 0.01), # 单笔交易风险 (1% of equity)
        ('max_positions', 3),  # 最大同时持仓数
        ('max_leverage', 3.0), # 最大总杠杆 (保留作为安全上限)
        ('printlog', True),
    )

    def __init__(self):
        self.inds = {}
        # 交易状态记录
        self.stops = {}      # 止损价
        self.highs = {}      # 持仓期间最高价
        self.high_bars = {}  # 最高价发生的 bar index
        
        for d in self.datas:
            self.inds[d] = {}
            # 计算指标
            self.inds[d]['sma_fast'] = bt.indicators.SimpleMovingAverage(
                d.close, period=self.params.fast_period)
            self.inds[d]['sma_slow'] = bt.indicators.SimpleMovingAverage(
                d.close, period=self.params.slow_period)
            # 长期趋势指标
            self.inds[d]['sma_trend'] = bt.indicators.SimpleMovingAverage(
                d.close, period=self.params.trend_period)
            # ATR 指标 (风控)
            self.inds[d]['atr'] = bt.indicators.ATR(d, period=self.params.atr_period)
            
            # 交叉信号 (1: 金叉, -1: 死叉)
            self.inds[d]['crossover'] = bt.indicators.CrossOver(
                self.inds[d]['sma_fast'], self.inds[d]['sma_slow'])

    def log(self, txt, dt=None):
        '''日志打印功能'''
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print('%s, %s' % (dt.isoformat(), txt))

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    '买入执行 [%s], 价格: %.2f, 成本: %.2f, 手续费: %.2f' %
                    (order.data._name,
                     order.executed.price,
                     order.executed.value,
                     order.executed.comm))
                
                # 初始化风控状态 (Phase 4)
                d = order.data
                atr_val = self.inds[d]['atr'][0]
                self.stops[d] = order.executed.price - self.params.atr_stop_mult * atr_val
                self.highs[d] = order.executed.price
                self.high_bars[d] = len(d)
                
                self.log(f'  >> 初始止损: {self.stops[d]:.2f} (ATR={atr_val:.2f})')

            elif order.issell():
                self.log(
                    '卖出执行 [%s], 价格: %.2f, 成本: %.2f, 手续费: %.2f' %
                    (order.data._name,
                     order.executed.price,
                     order.executed.value,
                     order.executed.comm))
            
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f'订单被取消/保证金不足/拒绝 [{order.data._name}]')

        self.order = None

    def next(self):
        # 计算当前持仓数量 (Phase 5)
        current_positions = 0
        for d in self.datas:
            if self.getposition(d).size != 0:
                current_positions += 1

        for d in self.datas:
            # 确保有足够的历史数据计算指标
            if len(d) < self.params.trend_period:
                continue

            crossover = self.inds[d]['crossover'][0]
            pos = self.getposition(d).size
            
            # 市场过滤条件 (Phase 2)
            # 1. 价格在 MA120 之上
            # 2. MA120 向上倾斜 (当前值 > 上一期值)
            sma_trend = self.inds[d]['sma_trend']
            trend_ok = (d.close[0] > sma_trend[0]) and (sma_trend[0] > sma_trend[-1])
            
            # 信号过滤条件 (Phase 3)
            # MA30 斜率 > 0 (如 5 日差分)
            sma_slow = self.inds[d]['sma_slow']
            # 确保有足够数据计算 5 日前的 MA30
            ma30_slope_ok = (len(sma_slow) > 5) and (sma_slow[0] > sma_slow[-5])

            if pos == 0:
                # 没有持仓，检查是否有买入信号 (金叉)
                if crossover > 0:
                    if trend_ok and ma30_slope_ok:
                        # 检查持仓限制 (Phase 5)
                        if current_positions >= self.params.max_positions:
                            self.log(f'买入信号忽略 [%s]: 达到最大持仓数 {self.params.max_positions}' % d._name)
                            continue

                        # 计算动态仓位 (Phase 5)
                        equity = self.broker.getvalue()
                        risk_amt = equity * self.params.risk_per_trade
                        atr_val = self.inds[d]['atr'][0]
                        
                        if atr_val <= 0:
                            self.log(f'买入忽略 [%s]: ATR异常 ({atr_val})' % d._name)
                            continue

                        risk_per_share = self.params.atr_stop_mult * atr_val
                        size = risk_amt / risk_per_share
                        
                        # 检查是否超过最大杠杆限制 (防止 ATR 过小导致仓位过大)
                        # 单个资产最大允许市值 = 总权益 * 3.0 / 3 = 总权益
                        max_allowed_value = equity * (self.params.max_leverage / self.params.max_positions)
                        if size * d.close[0] > max_allowed_value:
                            old_size = size
                            size = max_allowed_value / d.close[0]
                            self.log(f'  >> 仓位调整: 原Size={old_size:.4f} -> 新Size={size:.4f} (杠杆限制)')

                        self.log('买入信号创建 [%s], %.2f (趋势确认 + MA30向上)' % (d._name, d.close[0]))
                        self.log(f'  >> 资金管理: Equity={equity:.0f}, Risk={risk_amt:.2f}, ATR={atr_val:.2f}, Size={size:.4f}')
                        
                        self.buy(data=d, size=size)
                        current_positions += 1 # 假定成交，更新计数
                    else:
                        pass
                        # self.log(f'买入信号过滤 [%s]: Trend={trend_ok}, MA30_Slope={ma30_slope_ok}')
                    
            else:
                # 有持仓，执行风控检查 (Phase 4)
                
                # 1. 更新最高价状态
                if d.high[0] > self.highs.get(d, 0):
                    self.highs[d] = d.high[0]
                    self.high_bars[d] = len(d)
                
                # 2. ATR 止损检查
                stop_price = self.stops.get(d, 0)
                if d.low[0] < stop_price:
                    self.log(f'触发 ATR 止损 [%s]: 最低价 {d.low[0]:.2f} < 止损价 {stop_price:.2f}' % d._name)
                    self.close(data=d)
                    continue # 触发止损后跳过后续检查

                # 3. 时间止损检查 (N 天未创新高)
                bars_since_high = len(d) - self.high_bars.get(d, len(d))
                if bars_since_high > self.params.time_stop_days:
                    self.log(f'触发时间止损 [%s]: {bars_since_high} 天未创新高' % d._name)
                    self.close(data=d)
                    continue

                # 4. 趋势反转出场 (MA 死叉) - 保持原有逻辑
                if crossover < 0:
                    self.log('卖出信号创建 [%s], %.2f (死叉)' % (d._name, d.close[0]))
                    self.close(data=d)

# ================= 数据获取 =================
def fetch_data_ccxt(symbol, timeframe, start_date, end_date):
    print(f"尝试从 {EXCHANGE_ID} (CCXT) 获取 {symbol} 数据 (代理: {PROXY_URL if USE_PROXY else '无'})...")
    exchange_class = getattr(ccxt, EXCHANGE_ID)
    # 使用 Binance 官方 API，通过 ccxt 获取历史 K 线
    exchange = exchange_class({
        'enableRateLimit': True,
        'timeout': 15000,
    })
    
    if USE_PROXY:
        exchange.proxies = {
            'http': PROXY_URL,
            'https': PROXY_URL,
        }

    # 转换开始时间为时间戳 (毫秒)
    since = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
    end_ts = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000)
    
    # 获取 OHLCV 数据
    # CCXT fetch_ohlcv 每次可能有限制，这里简单演示一次获取，实际可能需要分页
    # limit=1000 是常见最大值
    all_ohlcv = []
    current_since = since
    
    while current_since < end_ts:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=current_since, limit=1000)
        if not ohlcv:
            break
        all_ohlcv.extend(ohlcv)
        # 更新 current_since 为最后一条数据的时间 + 1个周期
        last_ts = ohlcv[-1][0]
        if last_ts == current_since: # 防止死循环
             break
        current_since = last_ts + 1
        
        # 如果获取到的数据已经超过结束时间，停止
        if last_ts >= end_ts:
            break

    if not all_ohlcv:
        raise Exception("未获取到数据")
    
    # 转换为 Pandas DataFrame
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    
    # 过滤时间段
    df = df[(df.index >= start_date) & (df.index <= end_date)]
    return df

import numpy as np

def fetch_data_yf(symbol, start_date, end_date):
    print(f"CCXT 获取失败，尝试从 Yahoo Finance 获取 {symbol} 数据...")
    
    # 设置代理 (requests 环境变量)
    if USE_PROXY:
        os.environ['HTTP_PROXY'] = PROXY_URL
        os.environ['HTTPS_PROXY'] = PROXY_URL

    try:
        df = yf.download(symbol, start=start_date, end=end_date, progress=False)
        
        if df.empty:
            raise Exception("Yahoo Finance 返回空数据")

        # 处理多级索引列名 (如果存在)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1) 
            
        # yfinance 列名是 Open, High, Low, Close, Volume
        # 需要重命名为小写以匹配 backtrader
        df.columns = [c.lower() for c in df.columns]
            
        return df
    except Exception as e:
        raise Exception(f"Yahoo Finance 失败: {e}")

def fetch_data_mock(symbol, start_date, end_date):
    print(f"网络数据获取失败，生成【{symbol} 模拟数据】用于演示...")
    
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    days = (end_dt - start_dt).days + 1
    
    dates = pd.date_range(start=start_dt, end=end_dt)
    limit = len(dates)
    
    # 基于 symbol 生成不同的随机种子，保证每次运行结果一致但币种间不同
    seed_val = sum(ord(c) for c in symbol)
    np.random.seed(seed_val)
    
    returns = np.random.normal(0.001, 0.03, limit) # 波动率加大一点模拟币圈
    start_price = 10000 if 'BTC' in symbol else (2000 if 'ETH' in symbol else 100)
    price = start_price * np.cumprod(1 + returns)
    
    data = {
        'timestamp': dates,
        'open': price,
        'high': price * 1.02,
        'low': price * 0.98,
        'close': price,
        'volume': np.random.randint(100, 1000, limit)
    }
    
    df = pd.DataFrame(data)
    df.set_index('timestamp', inplace=True)
    return df

def fetch_data(symbol_ccxt, symbol_yf, timeframe, start_date, end_date):
    try:
        # 优先尝试 CCXT
        return fetch_data_ccxt(symbol_ccxt, timeframe, start_date, end_date)
    except Exception as e:
        print(f"CCXT 获取数据失败 ({symbol_ccxt}): {e}")
        # 如果强制使用 Binance，则直接抛出错误，让用户修复网络/代理问题
        if FORCE_BINANCE:
            raise
        try:
            # 失败后尝试 Yahoo Finance
            return fetch_data_yf(symbol_yf, start_date, end_date)
        except Exception as e2:
            print(f"Yahoo Finance 获取数据失败 ({symbol_yf}): {e2}")
            # 最后尝试模拟数据
            return fetch_data_mock(symbol_ccxt, start_date, end_date)

# ================= 主程序 =================
def run_backtest():
    # 1. 初始化 Cerebro 引擎
    cerebro = bt.Cerebro()

    # 2. 获取数据并添加到 Cerebro (多币种)
    for i in range(len(SYMBOLS_CCXT)):
        sym_ccxt = SYMBOLS_CCXT[i]
        sym_yf = SYMBOLS_YF[i]
        
        try:
            df = fetch_data(sym_ccxt, sym_yf, TIMEFRAME, START_DATE, END_DATE)
            print(f"[{sym_ccxt}] 成功获取 {len(df)} 条数据 ({START_DATE} 至 {END_DATE})")
            
            data = bt.feeds.PandasData(dataname=df, name=sym_ccxt)
            cerebro.adddata(data)
            
        except Exception as e:
            print(f"[{sym_ccxt}] 数据获取完全失败: {e}")

    # 3. 添加策略 (使用新的动态杠杆策略)
    cerebro.addstrategy(DynamicLeverageStrategy)

    # 4. 设置初始资金
    cerebro.broker.setcash(INITIAL_CASH)
    
    # 5. 设置手续费 (合约通常较低，Maker 0.02%, Taker 0.05%，这里设万分之五)
    cerebro.broker.setcommission(commission=0.0005)

    # 6. 添加分析指标
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.0, timeframe=bt.TimeFrame.Days, annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='timereturn', timeframe=bt.TimeFrame.Days)

    # 7. 运行回测
    print(f'初始资金: {INITIAL_CASH:.2f}')
    
    if len(cerebro.datas) == 0:
        print("错误: 没有数据被加载到回测引擎，无法运行回测。")
        print("请检查网络连接、代理设置，或确保 fetch_data 能够生成模拟数据。")
        return

    results = cerebro.run()
    if not results:
        print("回测未生成任何结果。")
        return
        
    strat = results[0]
    final_value = cerebro.broker.getvalue()

    # 8. 打印结果
    print(f'最终资金: {final_value:.2f}')
    total_return = ((final_value - INITIAL_CASH) / INITIAL_CASH) * 100
    print(f'收益率: {total_return:.2f}%')
    
    # 打印分析结果
    print('-----------------------------------')
    
    # 1. 收益率分析 (Phase 1.1)
    returns_dict = strat.analyzers.timereturn.get_analysis()
    returns_series = pd.Series(returns_dict)
    
    # 过滤无效值并确保长度
    clean_returns = returns_series.dropna()
    clean_returns = clean_returns[clean_returns != float('inf')]
    clean_returns = clean_returns[clean_returns != -float('inf')]
    
    print(f"交易天数: {len(clean_returns)}")
    if len(clean_returns) < 30:
        print("警告: 回测数据点少于 30 个，统计指标可能不显著。")
        
    print("\n--- 日收益率统计 ---")
    print(clean_returns.describe())
    
    # 2. 夏普比率 (Phase 1.2)
    sharpe_info = strat.analyzers.sharpe.get_analysis()
    sharpe_ratio = sharpe_info.get('sharperatio')
    
    if sharpe_ratio is None:
        print("\n夏普比率: None (通常因为收益率为常数或标准差为 0)")
        if clean_returns.std() == 0:
            print("警告: 收益率标准差为 0，无法计算夏普比率。")
    else:
        print(f"\n夏普比率: {sharpe_ratio:.4f}")
        
    # 3. 回撤分析 (Phase 1.3)
    dd = strat.analyzers.drawdown.get_analysis()
    max_dd = dd['max']['drawdown']
    print(f"最大回撤: {max_dd:.2f}%")
    print(f"最大回撤金额: {dd['max']['moneydown']:.2f}")

    # Sanity Check
    if max_dd > 100:
        print("警告: 最大回撤超过 100%，数据可能异常。")
    if total_return > 0 and max_dd == 0:
        print("提示: 盈利且无回撤，属于罕见情况，请检查数据。")

    # 4. 交易统计 (Phase 6)
    trade_info = strat.analyzers.trades.get_analysis()
    total_trades = trade_info.get('total', {}).get('closed', 0)
    
    if total_trades > 0:
        won = trade_info.get('won', {})
        lost = trade_info.get('lost', {})
        
        won_count = won.get('total', 0)
        lost_count = lost.get('total', 0)
        win_rate = (won_count / total_trades) * 100
        
        avg_won = won.get('pnl', {}).get('average', 0)
        avg_lost = lost.get('pnl', {}).get('average', 0)
        
        if avg_lost != 0:
            risk_reward_ratio = abs(avg_won / avg_lost)
        else:
            risk_reward_ratio = float('inf')
            
        print(f"\n--- 交易统计 ---")
        print(f"总交易数: {total_trades}")
        print(f"胜率: {win_rate:.2f}% ({won_count} 胜 / {lost_count} 负)")
        print(f"平均盈利: {avg_won:.2f}")
        print(f"平均亏损: {avg_lost:.2f}")
        print(f"盈亏比: {risk_reward_ratio:.2f}")
    else:
        print("\n--- 交易统计 ---")
        print("无闭合交易")

    # 9. 绘图
    # 注意：在某些无头环境(headless)可能无法显示窗口，会保存图片或报错
    print("正在绘图...")
    try:
        cerebro.plot(style='candlestick', volume=False)
    except Exception as e:
        print(f"绘图失败 (可能是环境限制): {e}")

if __name__ == '__main__':
    run_backtest()
