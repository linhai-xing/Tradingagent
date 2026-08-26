# CZSC 缠论分析脚本

这个目录包含用于缠论分析的 Python 脚本，演示如何使用 [waditu/czsc](https://github.com/waditu/czsc) 库进行缠论技术分析。

## 脚本列表

### 0. analyze_from_trist.py（推荐入口）— 一键缠论分析

直接输入股票代码，自动完成全部流程：

```bash
python analyze_from_trist.py 600522
python analyze_from_trist.py 000001.SZ --days 365
python analyze_from_trist.py 600522 --token your_tushare_token
```

自动执行：获取数据 → 缠论结构分析 → 买卖点信号分析。

### 1. fetch_market_data.py — 获取行情数据

数据源自动 fallback：**baostock → akshare → Tushare**（前两者免费无需 token）。

```bash
# 获取平安银行 2024年数据（无需 token）
python fetch_market_data.py --ts_code 000001.SZ --start_date 20240101 --end_date 20240614 --output data.csv

# 设置 Tushare token（可选兜底）
python fetch_market_data.py --ts_code 000001.SZ --token YOUR_TOKEN --output data.csv

# 列出所有 A 股
python fetch_market_data.py --list_stocks
```

### 2. analyze_czsc_structure.py — 分析缠论结构

使用 CZSC 对象分析 K 线数据，识别分型、笔、线段。

```bash
python analyze_czsc_structure.py --input data.csv --symbol 000001.SZ
```

### 3. signal_analysis.py — 买卖点信号分析

基于缠论结构生成买卖点信号，判断背驰和趋势。

```bash
python signal_analysis.py --input data.csv --symbol 000001.SZ
```

## 完整工作流程

```bash
# 步骤 1: 获取数据
python fetch_market_data.py --ts_code 000001.SZ --start_date 20240101 --end_date 20240614 --output data.csv

# 步骤 2: 分析缠论结构
python analyze_czsc_structure.py --input data.csv --symbol 000001.SZ

# 步骤 3: 分析买卖点信号
python signal_analysis.py --input data.csv --symbol 000001.SZ
```

## 环境要求

```bash
pip install czsc baostock akshare pandas
```

### 数据源说明

| 优先级 | 数据源 | 是否需要 Token |
|--------|--------|----------------|
| 1 | baostock | 否（免费） |
| 2 | akshare | 否（免费） |
| 3 | Tushare | 是（可选兜底） |

## 注意事项

1. 所有脚本默认使用日线级别
2. 信号仅供参考，实际交易需结合多方面因素
3. 务必设置止损、控制仓位
