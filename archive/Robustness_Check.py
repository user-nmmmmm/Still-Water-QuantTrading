import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime

# ================= 策略定义 (复制自 Local_Crypto_Backtest.py) =================
class DynamicLeverageStrategy(bt.Strategy):
    params = (
        ('fast_period', 10),
        ('slow_period', 30),
        ('trend_period', 120),
        ('atr_period', 14),
        ('atr_stop_mult', 2.0),
        ('time_stop_days', 15),
        ('risk_per_trade', 0.01),
        ('max_positions', 3),
        ('max_leverage', 3.0),
        ('printlog', False), # 优化时默认关闭日志
    )

    def __init__(self):
        self.inds = {}
        self.stops = {}
        self.highs = {}
        self.high_bars = {}
        
        for d in self.datas:
            self.inds[d] = {}
            self.inds[d]['sma_fast'] = bt.indicators.SimpleMovingAverage(
                d.close, period=self.params.fast_period)
            self.inds[d]['sma_slow'] = bt.indicators.SimpleMovingAverage(
                d.close, period=self.params.slow_period)
            self.inds[d]['sma_trend'] = bt.indicators.SimpleMovingAverage(
                d.close, period=self.params.trend_period)
            self.inds[d]['atr'] = bt.indicators.ATR(d, period=self.params.atr_period)
            self.inds[d]['crossover'] = bt.indicators.CrossOver(
                self.inds[d]['sma_fast'], self.inds[d]['sma_slow'])

    def log(self, txt, dt=None):
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print('%s, %s' % (dt.isoformat(), txt))

    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                d = order.data
                atr_val = self.inds[d]['atr'][0]
                self.stops[d] = order.executed.price - self.params.atr_stop_mult * atr_val
                self.highs[d] = order.executed.price
                self.high_bars[d] = len(d)
        self.order = None

    def next(self):
        current_positions = 0
        for d in self.datas:
            if self.getposition(d).size != 0:
                current_positions += 1

        for d in self.datas:
            if len(d) < self.params.trend_period:
                continue

            crossover = self.inds[d]['crossover'][0]
            pos = self.getposition(d).size
            
            sma_trend = self.inds[d]['sma_trend']
            trend_ok = (d.close[0] > sma_trend[0]) and (sma_trend[0] > sma_trend[-1])
            
            sma_slow = self.inds[d]['sma_slow']
            ma30_slope_ok = (len(sma_slow) > 5) and (sma_slow[0] > sma_slow[-5])

            if pos == 0:
                if crossover > 0:
                    if trend_ok and ma30_slope_ok:
                        if current_positions >= self.params.max_positions:
                            continue

                        equity = self.broker.getvalue()
                        risk_amt = equity * self.params.risk_per_trade
                        atr_val = self.inds[d]['atr'][0]
                        
                        if atr_val <= 0: continue

                        risk_per_share = self.params.atr_stop_mult * atr_val
                        size = risk_amt / risk_per_share
                        
                        max_allowed_value = equity * (self.params.max_leverage / self.params.max_positions)
                        if size * d.close[0] > max_allowed_value:
                            size = max_allowed_value / d.close[0]

                        self.buy(data=d, size=size)
                        current_positions += 1
            else:
                if d.high[0] > self.highs.get(d, 0):
                    self.highs[d] = d.high[0]
                    self.high_bars[d] = len(d)
                
                stop_price = self.stops.get(d, 0)
                if d.low[0] < stop_price:
                    self.close(data=d)
                    continue

                bars_since_high = len(d) - self.high_bars.get(d, len(d))
                if bars_since_high > self.params.time_stop_days:
                    self.close(data=d)
                    continue

                if crossover < 0:
                    self.close(data=d)

# ================= 模拟数据生成 =================
def fetch_data_mock(symbol, start_date, end_date):
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    days = (end_dt - start_dt).days + 1
    
    dates = pd.date_range(start=start_dt, end=end_dt)
    limit = len(dates)
    
    seed_val = sum(ord(c) for c in symbol)
    np.random.seed(seed_val)
    
    returns = np.random.normal(0.001, 0.03, limit)
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

# ================= 优化运行 =================
def run_optimization():
    cerebro = bt.Cerebro()
    
    # Generate data
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    print("正在生成模拟数据进行快速验证...")
    for sym in symbols:
        df = fetch_data_mock(sym, '2025-01-01', '2025-12-31')
        data = bt.feeds.PandasData(dataname=df, name=sym)
        cerebro.adddata(data)

    cerebro.broker.setcash(1000.0)
    cerebro.broker.setcommission(commission=0.0005)

    # Optimization
    # fast_period: 8, 10, 12
    # slow_period: 25, 30, 35
    # trend_period: 100, 120, 150
    # Total combinations: 3 * 3 * 3 = 27 runs
    
    cerebro.optstrategy(
        DynamicLeverageStrategy,
        fast_period=[8, 10, 12],
        slow_period=[25, 30, 35],
        trend_period=[100, 120, 150],
        printlog=False
    )
    
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.0, timeframe=bt.TimeFrame.Days, annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    
    print("开始参数优化 (共 27 组参数)...")
    # Windows 下多进程可能有问题，使用 maxcpus=1 安全模式
    results = cerebro.run(maxcpus=1)
    
    # Process results
    final_results = []
    for run in results:
        for strat in run:
            sharpe_info = strat.analyzers.sharpe.get_analysis()
            sharpe = sharpe_info.get('sharperatio')
            if sharpe is None: sharpe = -999 # Use a low value for sorting
            
            dd = strat.analyzers.drawdown.get_analysis()['max']['drawdown']
            
            params = (strat.params.fast_period, strat.params.slow_period, strat.params.trend_period)
            final_results.append((params, sharpe, dd))
            
    # Sort by Sharpe
    final_results.sort(key=lambda x: x[1], reverse=True)
    
    print("\n--- 优化结果 (Top 5) ---")
    print(f"{'参数 (Fast, Slow, Trend)':<30} | {'夏普比率':<10} | {'最大回撤':<10}")
    for res in final_results[:5]:
        sharpe_str = f"{res[1]:.4f}" if res[1] != -999 else "None"
        print(f"{str(res[0]):<30} | {sharpe_str:<10} | {res[2]:.2f}%")
        
    print("\n--- 稳健性评估 ---")
    top_sharpe = final_results[0][1]
    bottom_sharpe = final_results[-1][1]
    if bottom_sharpe == -999: bottom_sharpe = 0 # Handle None
    
    print(f"最优夏普: {top_sharpe:.4f}")
    print(f"最差夏普: {bottom_sharpe:.4f}")
    
    if top_sharpe > 0 and (top_sharpe - bottom_sharpe) < 1.0:
         print("结论: 策略在不同参数下表现相对稳定。")
    else:
         print("结论: 策略对参数较为敏感，或部分参数导致负收益。")

if __name__ == '__main__':
    run_optimization()
