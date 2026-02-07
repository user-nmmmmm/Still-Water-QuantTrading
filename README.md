# QuantTrading 量化交易系统

[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Status: Alpha](https://img.shields.io/badge/Status-Alpha-orange.svg)]()

## 📖 项目简介

**QuantTrading** 是一个基于 Python 开发的模块化、事件驱动型量化回测框架。本项目旨在构建一个可扩展的算法交易研究平台，核心验证了 **"市场状态识别 (Market Regime) + 动态策略路由 (Dynamic Routing) + 风险平价 (Risk Parity)"** 的组合交易范式。

系统采用面向对象设计，解耦了数据流、策略逻辑、执行引擎与绩效分析模块，支持多标的统一时间轴回测，适用于加密货币（USDT本位）及传统金融资产的策略验证。

---

## 🚀 核心特性

- **多标的事件驱动引擎**: 支持多品种（如 BTC-USDT, ETH-USDT）在统一时间轴上的并发回测，准确模拟真实市场的数据流推送。
- **市场状态机 (Market Regime Detection)**: 内置基于波动率与趋势强度的状态识别模块，自动区分 **趋势 (Trend)** 与 **震荡 (Mean Reversion)** 市场。
- **动态策略路由**: 根据市场状态实时切换交易策略（趋势跟踪 vs 均值回归），提高资金利用效率并降低单一策略风险。
- **精细化风控**:
  - **资金管理**: 基于 ATR 的动态仓位计算 (Kelly Criterion / Fixed Risk)。
  - **执行模拟**: 支持自定义滑点 (Slippage)、双边手续费 (Commission) 及延迟成交模拟。
- **专业级绩效报告**: 自动生成包含夏普比率、最大回撤、胜率、盈亏比等机构级指标的分析报告。

---

## 📊 回测绩效展示 (2015-2025)

本框架已在加密货币市场主要标的（BTC, ETH, BNB, SOL）上完成了长周期回测验证。以下是基于 **2015年1月1日 - 2025年12月31日** 的核心绩效数据。

> **回测说明**: 
> - **初始资金**: 10,000 USDT
> - **手续费**: 双边 0.1%
> - **数据源**: CCXT (Binance) / Synthetic
> - **策略组合**: 趋势跟踪 (Trend Following) + 均值回归 (Mean Reversion)

### 核心指标概览

| 指标 (Metrics) | 数值 (Values) | 说明 |
| :--- | :--- | :--- |
| **总收益率 (Total Return)** | **15.66%** | 稳健增长，非暴利型策略 |
| **年化收益率 (CAGR)** | **2.74%** | 长期复利效应 |
| **最大回撤 (Max Drawdown)** | **-9.27%** | 极低的回撤控制，风险敞口小 |
| **夏普比率 (Sharpe Ratio)** | **0.43** | 风险调整后收益为正 |
| **盈亏比 (Profit Factor)** | **1.33** | 平均每亏损 $1 可盈利 $1.33 |
| **胜率 (Win Rate)** | **35.29%** | 典型趋势策略特征：小亏大赚 |

### 净值曲线 (Equity Curve)

![Equity Curve](reports/2015-2025回测/equity.png)

*图示：策略在 10 年周期内的净值增长情况。可以看出策略在回撤控制上表现优异，适合作为稳健型投资组合的一部分。*

---

## 🛠️ 快速开始

### 1. 环境准备
确保您的系统已安装 Python 3.8 或更高版本。
```bash
git clone https://github.com/yourusername/QuantTrading.git
cd QuantTrading
pip install -r requirements.txt
```

### 2. 运行回测
系统提供两种运行模式，满足不同场景需求。

#### 交互式向导模式 (推荐)
直接运行 `main.py`，系统将引导您完成配置：
```bash
python main.py
```
> 系统将提示您选择数据源、设置交易标的 (如 BTC-USDT)、初始资金及回测区间。

#### 命令行极客模式
适合批量测试或自动化脚本调用：
```bash
python main.py --source synthetic --days 3650 --capital 10000 --symbols BTC-USDT ETH-USDT
```

---

## 📂 系统架构

```text
QuantTrading/
├── main.py                 # [Entry] 系统入口与流程编排
├── core/                   # [Core] 核心基础设施
│   ├── state.py            # 市场状态机 (Trend/Sideways/Volatile)
│   ├── broker.py           # 虚拟交易所 (订单撮合/滑点/费率)
│   ├── risk.py             # 风控中心 (仓位计算/止损管理)
│   ├── data.py             # 数据管道 (ETL/Resampling)
│   └── indicators.py       # 量化因子库 (TA-Lib Wrapper)
├── strategies/             # [Alpha] 策略库
│   ├── trend_following.py  # 趋势策略 (CTA)
│   └── mean_reversion.py   # 均值回归策略 (Bollinger Bands)
├── router/                 # [Router] 信号路由分发
├── backtest/               # [Engine] 回测引擎
└── reports/                # [Output] 绩效报告归档
```

---

## ⚖️ 免责声明

本项目 (`QuantTrading`) 仅用于量化交易策略的研究、教学演示与逻辑验证。
- **非投资建议**: 项目中的任何策略、代码或数据均不构成投资建议。
- **风险提示**: 数字货币与金融衍生品交易具有极高风险，可能导致资金全部损失。
- **实盘慎用**: 本系统主要针对历史数据回测设计，实盘部署需自行增加异常处理与网络安全模块。

---

Copyright © 2026 QuantTrading Team. All Rights Reserved.
