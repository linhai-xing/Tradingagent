---
name: czsc-thinking
description: 缠论（缠中说禅）技术分析 skill — 分型识别、笔线段分析、三类买卖点、背驰与趋势判断。当需要分析股票买卖点、大盘行情、制定交易策略时使用。
---

# 缠论思维 — CZSC 技术分析

本技能基于缠中说禅（2006-2008）原文思想，结合 `waditu/czsc` 库进行量化结构分析。

## 用法

当用户调用 `/czsc-thinking` 或 `/czsc-thinking <ticker>` 时：

### 单股缠论分析
```bash
cd C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\czsc_thinking\scripts
python analyze_from_trist.py <ticker>
```
读取输出，展示：分型、笔、线段、买卖点、背驰、趋势、操作建议。

### 数据获取 + 分步分析
```bash
cd C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\czsc_thinking\scripts

# 获取数据（baostock → akshare → Tushare 自动 fallback，无需 token）
python fetch_market_data.py --ts_code <ticker> --output data.csv

# 结构分析
python analyze_czsc_structure.py --input data.csv --symbol <ticker>

# 买卖点信号
python signal_analysis.py --input data.csv --symbol <ticker>
```

### 与 trist-selector 协作
```
1. /trist-selector <ticker>   → 选股打分
2. /czsc-thinking <ticker>    → 缠论结构分析
```
trist-selector 负责选股/打分，czsc-thinking 负责技术面结构分析。

## 核心思维框架

### 三大理念
1. **不测而测** — 不预测未来，只分析当下
2. **完全分类** — 列出所有可能，为每种情况准备应对
3. **级别思维** — 任何分析必须明确级别（日线/30分/周线）

### 分析流程
1. 明确级别 → 2. 识别结构(分型/笔/线段/中枢) → 3. 判断买卖点(一买/二买/三买) → 4. 评估背驰 → 5. 制定策略+止损

## 数据来源

| 数据 | 来源 |
|------|------|
| K 线 | baostock(首选) → akshare(备选) → Tushare(兜底) |
| 分析引擎 | waditu/czsc (CZSC 对象) |

## 文件结构

```
skills/czsc_thinking/
├── SKILL.md                        ← 本文件
├── references/chan-theory-core.md  ← 完整理论
├── examples/usage-scenarios.md     ← 实战场景
├── scripts/
│   ├── analyze_from_trist.py       ← 一键分析（推荐入口）
│   ├── fetch_market_data.py        ← 数据获取（多源 fallback）
│   ├── analyze_czsc_structure.py   ← 结构分析
│   ├── signal_analysis.py          ← 买卖点信号
│   └── example_workflow.py         ← 完整流程演示
```
