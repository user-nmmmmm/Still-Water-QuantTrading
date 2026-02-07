# QuantTrading 量化交易系统
## 一个兴趣项目，不构成任何投资建议

## 项目简介

**QuantTrading** 是一个模块化、多策略的量化交易系统，旨在适应美股和加密货币市场。该系统基于 Python 开发，采用自定义的轻量级回测引擎，集成了市场状态识别、策略路由、风险管理和工程化回测报告功能。

核心设计理念是 **“环境适应策略”**：通过市场状态机（Market State Machine）实时判断当前市场处于上涨趋势、下跌趋势还是震荡区间，并通过策略路由层（Router）动态调度对应的策略模块，实现“牛市吃单、熊市做空、震荡均值回归”的自适应交易。

## 核心特性

-   **多周期架构 (Multi-Timeframe)**:
    -   **长短周期分离**: 使用 4H/1D 大周期判断市场方向 (UP/DOWN/RANGE)，1H 小周期执行具体交易。
    -   **严格时间对齐**: 杜绝未来函数，确保小周期只能获取已完成的大周期状态。
-   **多市场适配**: 支持加密货币 (CCXT) 和美股 (YFinance) 数据源，具备代理配置功能。
-   **灵活回测配置**: 支持指定**回测天数**或**具体起止日期**，支持自定义初始资金和交易标的。
-   **市场状态机**: 基于 SMA 和斜率判定市场状态 (TREND_UP, TREND_DOWN, SIDEWAYS, NO_TRADE)，含 3 根 K 线稳定过滤器。
-   **策略路由 (Router)**:
    -   **互斥执行**: 同一时间只允许一个策略持有仓位。
    -   **自动清仓**: 状态切换时强制平掉旧策略仓位。
    -   **冷却机制**: 状态切换后进入冷却期，防止震荡市频繁开仓。
-   **模块化策略**:
    -   **TrendUp**: 双均线 + 斜率过滤，回踩 SMA30 做多。
    -   **TrendDown**: 反弹 SMA30 做空 (支持合约空单)。
    -   **RangeMeanReversion**: 布林带回归策略，含 ATR 波动率过滤和连亏熔断机制。
-   **风险管理**:
    -   **ATR 止损**: 动态波动率止损。
    -   **时间止损**: 持仓 N 天无盈利强制离场。
    -   **资金管理**: 基于账户权益的动态仓位分配，支持杠杆限制 (3x)。
-   **工程化回测与报告**:
    -   **智能报告命名**: 报告文件夹自动包含关键回测结果（如 `20260206_144428_364d_2Syms_Ret14.1pct`），一目了然。
    -   **配置持久化**: `report.txt` 自动记录运行参数（日期范围、资金、标的等），便于复盘。
    -   生成专业级回测报告 (CAGR, Sharpe, MaxDrawdown, Expectancy)。
    -   自动绘制净值曲线图 (Equity Curve)。

## 目录结构

```text
D:\QauntTrading
├── core/                   # 核心基础模块
│   ├── data.py             # 数据标准化与验证
│   ├── data_fetcher.py     # 数据获取 (CCXT/YFinance/Synthetic)
│   ├── indicators.py       # 技术指标计算 (SMA, ATR, BBANDS 等)
│   ├── state.py            # 市场状态机实现
│   ├── broker.py           # 模拟交易所与订单执行
│   ├── portfolio.py        # 账户与持仓管理
│   └── risk.py             # 风控与仓位计算
├── strategies/             # 策略实现模块
│   ├── base.py             # 策略基类
│   ├── trend_following.py  # 趋势策略 (Up/Down)
│   └── mean_reversion.py   # 震荡回归策略
├── router/                 # 策略路由层
│   └── router.py           # 路由逻辑与互斥控制
├── backtest/               # 回测引擎
│   ├── engine.py           # 回测主循环
│   └── reporting.py        # 报告生成与指标计算
├── reports/                # 回测结果输出目录
├── archive/                # 归档文件（旧脚本/临时文件）
├── main.py                 # 系统入口脚本
├── requirements.txt        # 依赖包列表
└── verify_router.py        # 路由逻辑验证脚本
```

## 安装与配置

### 1. 环境准备
确保已安装 Python 3.8 或以上版本。

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 代理配置 (可选)
如果在中国大陆地区访问币安或美股数据，建议配置代理。
可以在代码中传入 `proxy_url` 或直接设置环境变量：
```python
# 示例：初始化时指定代理
fetcher = DataFetcher(proxy_url="http://127.0.0.1:7897")
```

## 使用指南

通过 `main.py` 启动回测，支持灵活的命令行参数配置。

### 1. 快速开始 (默认配置)
```bash
python main.py
```

### 2. 指定日期范围 (推荐)
精确回测指定时间段的行情（格式：YYYY-MM-DD）：
```bash
python main.py --start 2025-01-01 --end 2025-12-31
```

### 3. 指定回测天数
回测过去 N 天的行情：
```bash
python main.py --days 365
```

### 4. 自定义资金与标的
```bash
# 初始本金 50000 U，交易 BTC 和 SOL
python main.py --capital 50000 --symbols BTC-USD SOL-USD --start 2025-01-01 --end 2025-06-30
```

### 参数说明
-   `--start`: 开始日期 (YYYY-MM-DD)
-   `--end`: 结束日期 (YYYY-MM-DD)
-   `--days`: 回测天数 (默认 365，若指定了 start/end 则忽略此参数)
-   `--capital`: 初始资金 (默认 1000.0)
-   `--symbols`: 交易对列表 (空格分隔，默认 BTC-USD ETH-USD)
-   `--source`: 数据源 (`synthetic`, `yahoo`, `ccxt`，默认 `synthetic`)
-   `--slippage`: 滑点率 (例如 0.001 代表 0.1%，默认 0.0)
-   `--random_slip`: 启用随机滑点 (将在 0 ~ slippage 之间随机分布)
-   `--seed`: 随机种子 (默认 42，用于复现结果)

## 回测报告

回测完成后，结果将保存在 `reports/` 目录下，文件夹名称格式为：
`YYYYMMDD_HHMMSS_{Days}d_{Syms}Syms_{Ret}pct`
（例如：`20260206_133110_365d_2Syms_Ret15.5pct`）

报告包含：
1.  **report.txt**: 
    -   **Configuration**: 记录本次回测的起止日期、资金、标的等配置。
    -   **Metrics**: 核心指标（年化收益、最大回撤、夏普比率、胜率、盈亏比等）。
2.  **equity.png**: 账户净值曲线图。
3.  **trades.csv**: 详细交易记录。
4.  **equity.csv**: 每日净值数据。

## 策略与系统逻辑详述 (Deep Dive)

### 1. 市场状态机 (Market State Machine)
核心逻辑位于 `core/state.py`，基于 **MA30** 和 **斜率** 判定市场状态。
-   **TREND_UP (牛市)**:
    -   条件: `Close > SMA30` 且 `SMA30 Slope > 0`
-   **TREND_DOWN (熊市)**:
    -   条件: `Close < SMA30` 且 `SMA30 Slope < 0`
-   **SIDEWAYS (震荡)**:
    -   条件: 不满足上述任一条件。
-   **稳定过滤器**: 状态必须连续保持 **3根K线** 不变，才会触发系统状态切换，避免假突破。

### 2. 上涨趋势策略 (TrendUpStrategy)
-   **适用状态**: `TREND_UP`
-   **入场逻辑**:
    -   回踩确认: `Close <= SMA30 * 1.005` (即价格回调至均线附近 0.5% 范围内)
    -   趋势确认: `SMA30 Slope > 0`
    -   辅助确认: `SMA10 > SMA30` (多头排列)
-   **止损逻辑**:
    -   初始止损: `EntryPrice - 2 * ATR14`
    -   移动止损: `Max(PreviousTrail, Close - 2 * ATR14)` (只升不降)
-   **出场逻辑**:
    -   价格跌破均线: `Close < SMA30`
    -   状态改变: 市场状态不再是 `TREND_UP`
    -   止损触发: 价格触及止损线

### 3. 下跌趋势策略 (TrendDownStrategy)
-   **适用状态**: `TREND_DOWN`
-   **入场逻辑**:
    -   反弹确认: `0.99 * SMA30 <= Close <= SMA30` (即价格反弹至均线下方 1% 范围内)
    -   趋势确认: `SMA30 Slope < 0`
-   **止损逻辑**:
    -   初始止损: `EntryPrice + 2 * ATR14`
    -   移动止损: `Min(PreviousTrail, Close + 2 * ATR14)` (只降不升)
-   **出场逻辑**:
    -   价格突破均线: `Close > SMA30 * 1.005` (给予 0.5% 缓冲)
    -   状态改变: 市场状态不再是 `TREND_DOWN`
    -   止损触发: 价格触及止损线

### 4. 震荡均值回归策略 (RangeStrategy)
-   **适用状态**: `SIDEWAYS`
-   **指标参数**: 布林带 (Period=20, StdDev=2.0)
-   **入场逻辑**:
    -   做多: `Low <= LowerBand` (触碰下轨)
    -   做空: `High >= UpperBand` (触碰上轨)
-   **波动率过滤**: 当 `ATR14 / Close > 3%` 时禁止开仓，避免在剧烈波动中被扫损。
-   **出场逻辑**:
    -   回归中轨: 价格触及布林带中轨 (`MiddleBand`)

### 5. 系统限制与风险提示 (Known Limitations)
本系统目前主要用于 **策略研究与逻辑验证**，与实盘交易存在以下差异：

1.  **状态无持久化 (No Persistence)**:
    -   系统运行在内存中，重启后会丢失所有策略状态（如移动止损位、连亏计数）。实盘部署需增加数据库或文件存储支持。
2.  **单时间框架执行**:
    -   尽管架构支持多周期，目前 `main.py` 默认以单一时间框架（如日线）驱动。

### 6. 数据与回测机制
-   **数据源**: 默认为 `synthetic` (合成数据)，采用分段随机游走模型生成 牛/熊/震荡 三种行情以测试策略鲁棒性。
-   **成交机制**:
    -   **延迟成交**: 信号产生于 Bar `i` 收盘，成交于 Bar `i+1` 开盘 (`Open`)，消除未来函数。
    -   **滑点模拟**: 支持固定或随机滑点，成交价 = `Open * (1 ± Slip)`。
-   **手续费**:
    -   **双边收费**: 开仓和平仓各收一次费用 (默认 0.1%)。
-   **互斥逻辑**: `Router` 确保同一标的在同一时刻只能由一个策略管理，杜绝多策略打架或同时持有多空双向仓位。
