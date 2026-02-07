# QuantTrading 量化交易系统
# 本项目为个人量化研究与学习记录
## 免责声明
本项目仅用于策略研究、教学演示与回测验证，不构成任何投资建议，不保证收益，也不提供任何实盘承诺。所有交易决策与风险后果由使用者自行承担。

## 项目简介
`QuantTrading` 是一个基于 Python 的模块化量化回测系统，核心目标是验证“市场状态识别 + 策略路由 + 风险控制”的组合交易框架。

当前实现重点：
- 多标的统一时间轴回测
- 市场状态机驱动策略切换
- 趋势策略与区间均值回归策略协同
- 统一订单模拟、账户管理、风控与报告输出

主入口文件：`main.py`

## 快速开始

### 环境要求
- Python 3.8 及以上
- 建议使用虚拟环境

### 安装依赖
```bash
pip install -r requirements.txt
```

### 最小可运行示例
#### 1. 交互式模式 (推荐)
直接运行 `main.py` 无参数即可进入交互式配置向导：
```bash
python main.py
```
系统将引导您配置：
- 数据源 (Synthetic/Yahoo/CCXT)
- 交易标的 (默认 BTC-USDT ETH-USDT)
- 初始资金 (USDT)
- 回测时间范围 (最近 N 天或指定日期区间)
- 滑点设置

#### 2. 命令行模式
```bash
python main.py --source synthetic --days 365 --capital 10000 --symbols BTC-USDT ETH-USDT
```

运行后会在 `reports/` 下生成一份独立报告目录。

## 命令行参数
`main.py` 支持以下参数（亦可通过交互模式配置）：

- `--days`：回测天数，默认 `365`
- `--start`：开始日期，格式 `YYYY-MM-DD`
- `--end`：结束日期，格式 `YYYY-MM-DD`
- `--capital`：初始资金 (USDT)，默认 `1000.0`
- `--symbols`：交易标的列表，空格分隔，默认 `BTC-USDT ETH-USDT`
- `--source`：数据源，`synthetic`、`yahoo`、`ccxt`，默认 `synthetic`
- `--seed`：随机种子，默认 `42`
- `--slippage`：滑点率，例如 `0.001` 表示 0.1%
- `--random_slip`：启用随机滑点，范围为 `0 ~ slippage`

参数优先级：
- 若同时传入 `--start` 和 `--end`，系统按日期区间回测，并自动覆盖 `--days`。
- 若未传入日期区间，系统按“当前时间往前 `--days` 天”计算回测窗口。

## 回测执行流程
1. 初始化组件：账户、经纪商、风控、状态机。
2. 初始化策略与路由器。
3. 对多标的数据索引取交集，形成统一时间轴。
4. 对每个标的数据补齐并计算指标。
5. 前 50 根 K 线作为预热阶段，不交易。
6. 每根 K 线先处理挂单（按当根开盘价成交），再执行策略路由。
7. 记录净值曲线并输出报告。

## 📂 项目结构说明

```text
QauntTrading/
├── main.py                       # [入口] 主程序 (参数解析/流程编排)
├── requirements.txt              # [依赖] 项目依赖库清单
├── README.md                     # [文档] 项目说明与使用指南
│
├── config/                       # [配置] 系统与策略配置
│   ├── params.yaml               # 全局参数配置文件 (YAML)
│   └── config.py                 # 配置加载与验证逻辑
│
├── core/                         # [核心] 交易底层架构模块
│   ├── broker.py                 # 交易执行 (订单队列/滑点/手续费)
│   ├── data.py                   # 数据管道 (清洗/验证/重采样)
│   ├── data_fetcher.py           # 数据采集 (Yahoo/CCXT/合成数据)
│   ├── indicators.py             # 技术指标库 (TA-Lib 封装)
│   ├── metrics.py                # 绩效评估 (夏普比/回撤/盈亏比)
│   ├── portfolio.py              # 账户管理 (资金/持仓/市值计算)
│   ├── risk.py                   # 风控中心 (仓位管理/止损止盈)
│   ├── state.py                  # 市场状态机 (Trend/Sideways 识别)
│   └── logger.py                 # 全局日志记录器
│
├── router/                       # [路由] 策略调度中心
│   └── router.py                 # 基于市场状态的策略动态切换
│
├── strategies/                   # [策略] 交易策略实现
│   ├── base.py                   # 策略抽象基类 (接口定义)
│   ├── trend_following.py        # 趋势跟踪策略 (顺势交易)
│   └── mean_reversion.py         # 均值回归策略 (震荡交易)
│
├── backtest/                     # [回测] 回测引擎
│   ├── engine.py                 # 事件驱动回测主循环
│   └── reporting.py              # 报告生成与可视化图表
│
├── models/                       # [模型] 机器学习模块 (预留)
│   ├── features.py               # 特征工程
│   ├── predictor.py              # 预测推理
│   └── trainer.py                # 模型训练
│
├── reports/                      # [输出] 回测结果自动归档
├── tests/                        # [测试] 单元测试套件
├── archive/                      # [归档] 历史版本代码
└── verify_*.py                   # [工具] 快速功能验证脚本
```

## 项目结构详细解释
1. `main.py`：程序入口，负责解析命令行参数、拉取数据、启动回测、生成报告。
2. `backtest/engine.py`：回测核心循环，统一时间轴、指标预热、撮合成交、策略执行都在这里完成。
3. `backtest/reporting.py`：将回测结果整理为文本指标、净值数据、交易明细和图表。
4. `core/data_fetcher.py`：统一数据接口，支持合成数据、Yahoo 数据和 CCXT 数据。
5. `core/data.py`：提供数据校验和 K 线重采样工具，用于规范输入数据格式。
6. `core/indicators.py`：集中计算 SMA、ATR、布林带、ADX 等策略所需指标。
7. `core/state.py`：根据价格与均线关系判断市场状态，并通过稳定过滤减少噪音切换。
8. `core/broker.py`：维护订单队列，在下一根开盘价成交，并叠加手续费与滑点。
9. `core/portfolio.py`：维护现金、持仓、平均成本、权益和总敞口。
10. `core/risk.py`：按固定风险比例与止损距离计算仓位大小。
11. `router/router.py`：把市场状态映射到策略；状态切换时执行清仓和冷却期控制。
12. `strategies/base.py`：策略统一模板，封装开平仓流程与风控对接。
13. `strategies/trend_following.py`：实现上涨趋势策略与下跌趋势策略。
14. `strategies/mean_reversion.py`：实现震荡区间的布林带均值回归策略。
15. `reports/`：每次回测结果会写入一个独立子目录，便于复盘和对比。
16. `tests/`：用于功能验证；当前部分测试脚本与最新代码命名尚未完全同步。
17. `config/`、`models/`：目前主要是占位模块，尚未接入主回测流程。
18. `archive/`：存放历史版本和实验脚本，不参与当前主流程。

## 报告输出结构
报告由 `backtest/reporting.py` 生成，输出到 `reports/` 目录。

目录命名格式：
`YYYYMMDD_HHMMSS_{Days}d_{N}Syms_Ret{X}pct`

字段含义：
- `YYYYMMDD_HHMMSS`：报告生成时间
- `{Days}d`：回测天数
- `{N}Syms`：标的数量
- `Ret{X}pct`：总收益率百分比

输出目录示例：
```text
reports/
└── example report
    ├── report.txt               # 配置与指标摘要
    ├── equity.csv               # 净值时间序列
    ├── trades.csv               # 成交明细（有交易时生成）
    └── equity.png               # 净值/回撤/收益/仓位图
```

`trades.csv` 常见字段：
- `signal_time`：信号产生时间
- `fill_time`：成交时间
- `symbol`：交易标的
- `side`：方向（buy/sell/short/cover）
- `qty`：成交数量
- `fill_price`：成交价格
- `commission`：手续费
- `slip`：滑点绝对值
- `slip_dir`：滑点方向
- `strategy_id`：策略标识
- `exit_reason`：平仓原因

## 策略与风控简述

### 市场状态机
- `TREND_UP`：`close > SMA_30` 且 `SMA_30` 斜率为正
- `TREND_DOWN`：`close < SMA_30` 且 `SMA_30` 斜率为负
- `SIDEWAYS`：其余情况
- 稳定过滤：候选状态连续达到 3 根 K 线后才切换

### 路由机制
- `TREND_UP` 映射 `TrendUp`
- `TREND_DOWN` 映射 `TrendDown`
- `SIDEWAYS` 映射 `RangeMeanReversion`
- 状态切换时强制平仓并进入冷却期（默认 3 根 K 线）

### 仓位与成交
- 仓位公式：`qty = (equity * risk_per_trade) / abs(entry - stop_loss)`
- 默认风险比例：1%
- 默认手续费：0.1%（双边）
- 信号在下一根 K 线开盘价成交，可叠加固定或随机滑点

## 当前实现边界
- 主流程目前是单时间框架驱动。
- `config/` 与 `models/` 目录当前未接入回测主链路。
- 部分 `tests/` 脚本仍需根据最新代码重构。
- 系统状态和策略上下文为内存态，未做持久化。

## 建议使用顺序
1. 先用 `synthetic` 数据检查流程是否跑通。
2. 再切换到 `yahoo` 或 `ccxt` 做历史回测。
3. 重点复盘 `report.txt`、`equity.csv`、`trades.csv`。
4. 扩展策略时优先继承 `strategies/base.py`。