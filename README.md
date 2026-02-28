# Still Water QuantTrading

[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Status: Alpha](https://img.shields.io/badge/Status-Alpha-orange.svg)]()
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Backtest: 10Y](https://img.shields.io/badge/Backtest-10%20Years-green.svg)]()

---

## 项目简介

**Still Water QuantTrading** 是一个基于 Python 开发的模块化、事件驱动型量化回测框架，专为加密货币市场策略研究设计。

本项目核心验证了 **"市场状态识别 (Market Regime Detection) + 动态策略路由 (Dynamic Routing) + 风险平价仓位管理 (Risk Parity Sizing)"** 的组合交易范式。系统采用面向对象设计 (OOP)，遵循 SOLID 原则，将数据管道、策略逻辑、执行引擎与绩效分析解耦为独立模块，支持多标的统一时间轴回测。

---

## 核心特性

| 模块 | 功能描述 |
| :--- | :--- |
| **多标的事件驱动引擎** | 支持多品种在统一时间轴上的并发回测，精确模拟真实数据流推送与时间对齐 |
| **市场状态机** | 基于 ATR 波动率与 ADX/SMA 趋势强度，自动识别趋势/震荡/高波动三种市场状态 |
| **动态策略路由** | 趋势状态启用 CTA 跟踪，震荡状态切换 Bollinger 均值回归，高波动路由至 Trend Breakout |
| **机构级风控** | ATR 动态头寸调整、集中度限制、自定义滑点模型、双边手续费模拟 |
| **专业绩效归因** | 自动生成 Sharpe、MaxDD、Calmar、Profit Factor、逐策略拆分等完整报告 |
| **熔断机制** | 连续亏损或滚动 Sharpe < 0 时自动下线问题策略，保护净值 |

---

## 回测绩效展示 (2015–2025)

> **回测配置**
> - **标的**: BTC-USDT / ETH-USDT / SOL-USDT / BNB-USDT
> - **时间范围**: 2015-01-01 — 2025-12-13 (约 11 年)
> - **初始资金**: 10,000 USDT
> - **手续费**: 双边 0.1% (Taker Fee)
> - **滑点**: 固定 0.1%
> - **数据源**: Synthetic (基于真实价格分布的场景模拟)
> - **报告路径**: `reports/20260228_023942_3999d_4Syms_Ret14728.5pct/`

### 核心指标

| 指标 | 数值 | 说明 |
| :--- | ---: | :--- |
| **总收益率 (Total Return)** | **14,728.5%** | $10,000 → $1,482,852 |
| **年化收益率 (CAGR)** | **57.87%** | 11 年复利增长 |
| **最大回撤 (Max Drawdown)** | **-19.22%** | 峰值回撤约 $333K |
| **夏普比率 (Sharpe Ratio)** | **5.85** | 机构级风险调整收益 |
| **月均收益率** | **3.90%** | 月度层面稳定增长 |
| **盈亏比 (Profit Factor)** | **3.70** | 每亏 $1 盈利 $3.70 |
| **胜率 (Win Rate)** | **47.28%** | 低胜率配合高盈亏比 |
| **总交易次数** | **184** | 平均每月约 1.4 笔 |
| **净利润 (Net PnL)** | **$1,472,852** | 扣除手续费 & 滑点后 |
| **总手续费** | $70,025 | 占毛利润约 4.5% |
| **总滑点成本** | $75,371 | 占毛利润约 4.9% |

### 策略绩效拆分

| 策略 | 交易次数 | 胜率 | 盈亏比 | 净贡献 PnL |
| :--- | ---: | ---: | ---: | ---: |
| **TrendBreakout (Alpha)** | 45 | **66.67%** | **23.10** | **+$1,640,486** |
| TrendUp (CTA) | 88 | 42.05% | 0.64 | -$87,314 |
| TrendDown (Short CTA) | 47 | 36.17% | 0.65 | -$80,319 |
| Router (信号路由) | 4 | 75.00% | 23.99 | $0 (已归入上述) |

> **关键发现**: TrendBreakout Alpha 以 24.5% 的交易占比，贡献了超过 **111%** 的系统净利润，是整个策略组合的核心收益来源。CTA 趋势策略在当前参数下处于亏损，可作为下一步优化方向。

---

## Alpha 增强验证

针对 **Trend Breakout Alpha** 进行 "Baseline vs Baseline+Alpha" 严格对比验证（2025 短周期测试）：

| 指标 | 原系统 (Baseline) | 原系统 + Alpha | 提升幅度 |
| :--- | ---: | ---: | :--- |
| **年化收益 (CAGR)** | 2.21% | **9.69%** | **+338%** |
| **夏普比率 (Sharpe)** | 0.76 | **2.30** | **+203%** |
| **卡尔玛 (Calmar)** | 1.14 | **2.54** | **+123%** |
| **最大回撤 (MaxDD)** | -1.93% | -3.81% | 在可控范围内 |

> Alpha 策略在"强趋势启动 / 高波动"阶段提供了显著超额收益，验证了 P0-P5 研发流程的有效性。

---

## 研发方法论 (P0–P5 Pipeline)

本项目采用严格的 Alpha 研发到上线流水线，确保策略的鲁棒性：

```
P0 选题        → 明确 Alpha 类型与非目标（Trend Breakout，非高胜率策略）
P1 原型 (MVP)  → research/ 向量化裸回测，验证信号逻辑
P2 现实检验    → 引入真实成本 (Fee/Slip) 与极端行情压测
P3 系统集成    → 封装为 Strategy Plugin，接入 Router & RiskManager
P4 组合验证    → 对比 Baseline vs Alpha 绩效，确保 1+1 > 2
P5 熔断机制    → 定义自动失效判据，实现优雅下线
```

---

## 快速开始

### 1. 环境准备

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 运行回测

**模式 A — 交互式向导（推荐初次使用）**

```bash
python main.py
```

**模式 B — 命令行参数**

```bash
# 复现官方 2015–2025 十年回测
python main.py \
  --source synthetic \
  --start 2015-01-01 \
  --end 2025-12-13 \
  --capital 10000 \
  --symbols BTC-USDT ETH-USDT SOL-USDT BNB-USDT \
  --slippage 0.001

# 快速 1 年测试
python main.py --days 365 --capital 10000 --symbols BTC-USDT ETH-USDT
```

### 3. 参数说明

| 参数 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `--source` | str | `synthetic` | 数据源：`synthetic` / `yahoo` / `ccxt` |
| `--symbols` | list | `BTC-USDT ETH-USDT` | 交易标的，空格分隔 |
| `--days` | int | `365` | 回测天数（从今日倒推） |
| `--start` | str | — | 开始日期 `YYYY-MM-DD`，优先级高于 `--days` |
| `--end` | str | — | 结束日期 `YYYY-MM-DD` |
| `--capital` | float | `1000.0` | 初始资金 (USDT) |
| `--slippage` | float | `0.0` | 固定滑点率（0.001 = 0.1%） |
| `--random_slip` | flag | `False` | 启用随机滑点（模拟真实流动性） |
| `--seed` | int | `42` | 随机数种子，保证结果可复现 |

---

## 策略逻辑

### 市场状态机

$$
S_t =
\begin{cases}
\text{TREND\_UP},   & P_t > \text{SMA}(n)\ \land\ \text{Slope} > \theta \\
\text{TREND\_DOWN}, & P_t < \text{SMA}(n)\ \land\ \text{Slope} < -\theta \\
\text{VOLATILE},    & \text{ADX} > 25\ \land\ \text{ATR\%} > \tau \\
\text{SIDEWAYS},    & \text{otherwise}
\end{cases}
$$

### 仓位管理（风险平价）

$$
Q = \frac{\text{Equity} \times \text{Risk\%}}{\text{ATR} \times \text{Multiplier}}
$$

高波动时 ATR 上升 → 仓位自动下调，实现跨标的风险均衡。

### TrendBreakout Alpha（Donchian 突破）

| 要素 | 规则 |
| :--- | :--- |
| **触发条件** | VOLATILE 状态（ADX > 25）且处于 TREND_UP |
| **入场信号** | 价格突破 20 日最高价 |
| **出场信号** | 价格跌破 10 日最低价 |
| **熔断** | 连续 5 笔亏损 或 滚动 Sharpe < 0 时自动停用 |

---

## 系统架构

```
Still-Water-QuantTrading/
├── main.py                     # 系统入口（CLI / 交互式）
├── config/
│   ├── config.py               # 全局配置加载器
│   └── params.yaml             # 策略参数配置
├── core/
│   ├── data_fetcher.py         # 数据获取（CCXT / Yahoo / Synthetic）
│   ├── data.py                 # 数据管道（ETL / 对齐 / 质检）
│   ├── state.py                # 市场状态机
│   ├── broker.py               # 虚拟交易所（撮合 / 手续费 / 滑点）
│   ├── risk.py                 # 风控中心（仓位 / 止损 / 集中度）
│   └── indicators.py           # 量化因子库
├── strategies/
│   ├── base.py                 # 策略抽象基类
│   ├── trend_following.py      # CTA 趋势跟踪
│   ├── mean_reversion.py       # Bollinger 均值回归
│   └── trend_breakout.py       # Donchian 趋势突破（Alpha）
├── router/                     # 动态信号路由分发器
├── backtest/
│   ├── engine.py               # 事件驱动回测引擎
│   └── reporting.py            # 绩效报告生成器
├── research/                   # Alpha 孵化实验室（P1–P2）
├── reports/                    # 回测报告输出目录
└── docs/                       # 详细技术文档
```

---

## 详细文档

- **[回测假设与逻辑](docs/backtest_assumptions.md)** — 订单执行模型、滑点/手续费计算、数据处理逻辑
- **[部署与运维指南](docs/deployment.md)** — 服务器部署、API 配置、实盘监控

---

## 免责声明

本项目仅用于量化交易策略的**研究、教学演示与逻辑验证**。

- 项目中的任何策略、代码或数据**均不构成投资建议**
- 数字货币与金融衍生品交易具有极高风险，可能导致**资金全部损失**
- 本系统主要针对历史数据回测设计，**实盘部署需自行增加异常处理与网络安全模块**

---

Copyright © 2026 Still Water QuantTrading. All Rights Reserved.
