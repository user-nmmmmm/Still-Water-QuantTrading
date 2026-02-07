# QuantTrading 量化交易系统

> 仅用于策略研究与回测验证，不构成任何投资建议。

## 1. 项目概述

`QuantTrading` 是一个基于 Python 的模块化回测系统，核心目标是验证“市场状态识别 + 策略路由 + 风险控制”的组合交易框架。

当前代码实现聚焦于：
- 多标的日线级别回测（统一时间轴）
- 市场状态机驱动的策略切换（上涨/下跌/震荡）
- 趋势与均值回归策略并行管理
- 统一的订单、账户、风控与报告输出

主入口：`main.py`

## 2. 快速开始

### 2.1 环境要求

- Python 3.8+
- 建议使用虚拟环境

### 2.2 安装依赖

```bash
pip install -r requirements.txt
```

依赖见 `requirements.txt`：`pandas`、`numpy`、`matplotlib`、`yfinance`、`ccxt`、`requests`。

### 2.3 最小可运行示例（推荐先用合成数据）

```bash
python main.py --source synthetic --days 365 --capital 10000 --symbols BTC-USD ETH-USD
```

运行完成后，会在 `reports/` 下生成一份报告目录。

## 3. 命令行参数

`main.py` 支持以下参数：

- `--days`：回测天数，默认 `365`
- `--start`：开始日期，格式 `YYYY-MM-DD`
- `--end`：结束日期，格式 `YYYY-MM-DD`
- `--capital`：初始资金，默认 `1000.0`
- `--symbols`：标的列表，空格分隔，默认 `BTC-USD ETH-USD`
- `--source`：数据源，`synthetic | yahoo | ccxt`，默认 `synthetic`
- `--seed`：随机种子，默认 `42`
- `--slippage`：滑点率（如 `0.001` 表示 0.1%）
- `--random_slip`：启用随机滑点（区间 `[0, slippage]`）

参数优先级说明：
- 同时提供 `--start` 和 `--end` 时，系统按日期区间回测，并自动覆盖 `--days`。
- 未提供日期区间时，系统按“当前时间向前 `--days` 天”计算窗口。

示例：

```bash
python main.py --start 2025-01-01 --end 2025-12-31 --source yahoo --symbols AAPL MSFT --capital 50000
```

```bash
python main.py --source ccxt --days 180 --symbols BTC-USD ETH-USD --slippage 0.001 --random_slip
```

## 4. 回测执行流程（按代码实现）

回测核心在 `backtest/engine.py`，执行顺序如下：

1. 初始化组件：`Portfolio`、`Broker`、`RiskManager`、`MarketStateMachine`
2. 初始化策略与路由：
   - `TrendUpStrategy`
   - `TrendDownStrategy`
   - `RangeStrategy`（在路由中命名为 `RangeMeanReversion`）
3. 对所有标的数据取时间索引交集，形成统一时间轴
4. 为每个标的补齐数据并计算指标（SMA/ATR/BBANDS/ADX）
5. 从第 50 根 K 线开始进入交易循环（前 50 根用于指标预热）
6. 每根 K 线先处理挂单（按当根 `open` 成交），再进行策略路由与信号生成
7. 记录净值曲线，最后输出交易记录和报告

## 5. 数据源与数据处理

数据获取在 `core/data_fetcher.py`：

- `synthetic`：合成场景数据（上涨、震荡、下跌三阶段）
- `yahoo`：通过 `yfinance`
- `ccxt`：通过 `ccxt`（Binance）

实现细节：
- `ccxt` 输入若为 `BTC-USD` 风格，会自动转换为 `BTC/USDT`
- 列名统一为小写 `open/high/low/close/volume`
- `DataFetcher` 默认会设置代理：`http://127.0.0.1:7897`

## 6. 策略与状态机

### 6.1 市场状态机（`core/state.py`）

状态定义：
- `TREND_UP`
- `TREND_DOWN`
- `SIDEWAYS`
- `NO_TRADE`（当前路由逻辑不会主动映射到策略）

判定规则：
- `TREND_UP`：`close > SMA_30` 且 `SMA_30` 斜率 > 0
- `TREND_DOWN`：`close < SMA_30` 且 `SMA_30` 斜率 < 0
- 其他：`SIDEWAYS`

稳定过滤：
- 新状态连续出现达到 `stability_period`（默认 3）后才切换，减少抖动。

### 6.2 路由机制（`router/router.py`）

- 状态到策略映射：
  - `TREND_UP -> TrendUp`
  - `TREND_DOWN -> TrendDown`
  - `SIDEWAYS -> RangeMeanReversion`
- 当状态切换时：
  - 清理旧策略上下文
  - 若有持仓，提交平仓单
  - 进入冷却期（默认 `cooldown_bars=3`）

### 6.3 趋势上行策略（`TrendUpStrategy`）

入场：
- `close <= SMA_30 * 1.005`
- `SMA_30` 斜率 > 0
- `SMA_10 > SMA_30`

初始止损：
- `stop_loss = close - 2 * ATR_14`

出场：
- `close < SMA_30`
- 或状态不再属于 `TREND_UP`
- 或触发 `max(stop_loss, trailing_stop)`

### 6.4 趋势下行策略（`TrendDownStrategy`）

入场：
- `0.99 * SMA_30 <= close <= SMA_30`
- `SMA_30` 斜率 < 0

初始止损：
- `stop_loss = close + 2 * ATR_14`

出场：
- `close > SMA_30 * 1.005`
- 或状态不再属于 `TREND_DOWN`
- 或触发 `min(stop_loss, trailing_stop)`

### 6.5 震荡均值回归策略（`RangeStrategy`）

入场：
- `low <= BB_LOWER` 开多
- `high >= BB_UPPER` 开空
- 且满足波动率过滤：`ATR_14 / close <= 0.03`

出场：
- 多头：`close >= BB_MIDDLE`
- 空头：`close <= BB_MIDDLE`
- 或触发止损

额外保护：
- 连续 3 次亏损后，进入 24 根 K 线冷却期（策略内熔断）。

## 7. 风控与成交模型

### 7.1 仓位计算（`core/risk.py`）

固定风险比例模型：

`qty = (equity * risk_per_trade) / abs(entry - stop_loss)`

默认 `risk_per_trade = 1%`。

### 7.2 杠杆约束（`strategies/base.py`）

下单前检查组合杠杆，目标不超过 3x；若超限会自动缩小下单数量。

### 7.3 成交规则（`core/broker.py`）

- 信号先入队列（`submit_order`）
- 在下一根 K 线处理（`process_orders`），按该根 `open` 成交
- 支持固定滑点与随机滑点
- 默认手续费：`0.1%`（双边）

## 8. 报告输出

报告生成在 `backtest/reporting.py`，输出目录格式：

`YYYYMMDD_HHMMSS_{Days}d_{N}Syms_Ret{X}pct`

输出文件：
- `report.txt`：配置与核心指标
- `equity.csv`：净值序列
- `trades.csv`：成交明细（若有交易）
- `equity.png`：净值、回撤、日收益、现金/持仓分布图

主要指标：
- `CAGR`
- `TotalReturn`
- `MaxDrawdownPct`
- `MaxDrawdownAmount`
- `SharpeRatio`
- `AvgMonthlyReturn`
- `TotalTrades`
- `WinRate`
- `ProfitFactor`
- `Expectancy`
- 以及按策略拆分的交易统计

## 9. 项目结构

```text
D:\QauntTrading
├── main.py
├── requirements.txt
├── README.md
├── backtest/
│   ├── engine.py
│   └── reporting.py
├── core/
│   ├── broker.py
│   ├── data.py
│   ├── data_fetcher.py
│   ├── indicators.py
│   ├── portfolio.py
│   ├── risk.py
│   └── state.py
├── router/
│   └── router.py
├── strategies/
│   ├── base.py
│   ├── mean_reversion.py
│   └── trend_following.py
├── tests/
├── reports/
└── archive/
```

## 10. 当前实现边界与注意事项

以下内容是对当前仓库状态的真实说明：

- 当前回测主流程是单时间框架驱动（默认日线数据），尚未在主流程中实现真正的多周期联动执行。
- `config/` 与 `models/` 目录下大多为占位代码（`pass`），未接入主回测链路。
- `tests/` 中部分测试代码使用了过期命名（如旧状态枚举、旧类名），现状下不保证可直接通过。
- 系统状态与策略上下文只在内存中维护，未做持久化。
- 该项目定位为回测研究框架，不是可直接连接实盘交易所的生产交易系统。

## 11. 建议的使用顺序

1. 先用 `synthetic` 验证流程完整性。
2. 再切换到 `yahoo` 或 `ccxt` 做历史数据回测。
3. 用 `reports/` 下的 `trades.csv` 与 `equity.csv` 做复盘分析。
4. 若要扩展策略，优先复用 `strategies/base.py` 的统一下单与风控流程。

## 12. 免责声明

本项目仅用于技术研究、策略开发与教学演示，不构成任何投资建议。所有交易决策与风险后果由使用者自行承担。
