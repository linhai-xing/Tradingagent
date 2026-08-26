"""
Phase 1b: Pull K-line data + technical indicators for all traded stocks.
Analyze pre-buy setup, during-hold performance, and post-sell trajectory.
"""
import json, os, sys
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd
import numpy as np

sys.path.insert(0, r"C:\Users\72955\.claude\plugins\cache\uzi-skill\stock-deep-analyzer\3.9.0\skills\deep-analysis\scripts")
sys.path.insert(0, r"C:\Users\72955\.claude\plugins\cache\uzi-skill\stock-deep-analyzer\3.9.0")

OUT_DIR = r"C:\Users\72955\Desktop\tradingagent\TradingAgents\delivery_analysis"

with open(os.path.join(OUT_DIR, "matched_trades.json"), encoding="utf-8") as f:
    data = json.load(f)
    matched = data["matched"]

with open(os.path.join(OUT_DIR, "stock_symbols.json"), encoding="utf-8") as f:
    symbols = json.load(f)

# Pull K-line for all stocks
import akshare as ak
import baostock as bs
import time

def pull_kline_akshare(code, start, end):
    """Try akshare with retry."""
    for attempt in range(3):
        try:
            time.sleep(0.5 + attempt * 0.5)
            df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
            if len(df) > 0:
                return df
        except Exception:
            time.sleep(1)
    return None

def pull_kline_baostock(code, start, end):
    """Fallback: baostock."""
    try:
        bs.login()
        rs = bs.query_history_k_data_plus(code,
            "date,open,high,low,close,volume,amount",
            start_date=start, end_date=end,
            frequency="d", adjustflag="2")
        rows = []
        while (rs.error_code == '0') & rs.next():
            rows.append(rs.get_row_data())
        bs.logout()
        if rows:
            df = pd.DataFrame(rows, columns=["日期","开盘","最高","最低","收盘","成交量","成交额"])
            df["日期"] = pd.to_datetime(df["日期"])
            for c in ["开盘","最高","最低","收盘","成交量","成交额"]:
                df[c] = pd.to_numeric(df[c], errors='coerce')
            return df
    except Exception:
        pass
    return None

def pull_benchmark_baostock():
    try:
        bs.login()
        rs = bs.query_history_k_data_plus("sh.000001",
            "date,open,high,low,close,volume,amount",
            start_date="2026-04-01", end_date="2026-06-25",
            frequency="d", adjustflag="2")
        rows = []
        while (rs.error_code == '0') & rs.next():
            rows.append(rs.get_row_data())
        bs.logout()
        if rows:
            df = pd.DataFrame(rows, columns=["日期","开盘","最高","最低","收盘","成交量","成交额"])
            df["日期"] = pd.to_datetime(df["日期"])
            for c in ["开盘","最高","最低","收盘","成交量","成交额"]:
                df[c] = pd.to_numeric(df[c], errors='coerce')
            df["close"] = df["收盘"]
            df["ret"] = df["收盘"].pct_change()
            return df
    except Exception as e:
        print(f"  benchmark baostock error: {e}")
    return None

print("Pulling daily K-line data for 17 stocks...")
klines = {}
for name, code in symbols.items():
    # Try akshare first, then baostock
    df = pull_kline_akshare(code, "20260401", "20260625")
    if df is None:
        # Try baostock - need to convert code format
        bs_code = ("sh." if code.startswith(("6","9")) else "sz.") + code
        df = pull_kline_baostock(bs_code, "2026-04-01", "2026-06-25")
        if df is not None:
            # Rename columns to match akshare format
            df = df.rename(columns={"close": "收盘", "open": "开盘", "high": "最高", "low": "最低", "volume": "成交量", "amount": "成交额"})

    if df is not None and len(df) > 0:
        df = df.sort_values("日期")
        # Technical indicators
        df["MA5"] = df["收盘"].rolling(5).mean()
        df["MA10"] = df["收盘"].rolling(10).mean()
        df["MA20"] = df["收盘"].rolling(20).mean()
        df["VOL_MA5"] = df["成交量"].rolling(5).mean()
        df["VOL_MA20"] = df["成交量"].rolling(20).mean()
        df["vol_ratio"] = df["成交量"] / df["VOL_MA20"]
        # RSI(14)
        delta = df["收盘"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df["RSI14"] = 100 - (100 / (1 + rs))
        # Daily return
        df["ret"] = df["收盘"].pct_change()
        df["high_low_pct"] = (df["最高"] - df["最低"]) / df["开盘"] * 100
        klines[code] = df
        print(f"  {name}({code}): {len(df)} days")
    else:
        print(f"  {name}({code}): NO DATA from both sources")

# Pull benchmark (上证指数)
print("\nPulling benchmark (上证指数)...")
try:
    benchmark = ak.stock_zh_index_daily(symbol="sh000001")
    benchmark["日期"] = pd.to_datetime(benchmark["date"])
    benchmark = benchmark.sort_values("日期")
    benchmark["ret"] = benchmark["close"].pct_change()
    print(f"  上证指数(akshare): {len(benchmark)} days")
except Exception as e:
    print(f"  akshare benchmark: {e}, trying baostock...")
    benchmark = pull_benchmark_baostock()
    if benchmark is not None:
        print(f"  上证指数(baostock): {len(benchmark)} days")
    else:
        print("  benchmark FAILED from both sources")
        benchmark = None

# Now analyze each matched trade
print("\n=== Per-Trade Technical Analysis ===")
trade_analysis = []

for t in matched:
    code = symbols.get(t["stock_name"])
    if code is None or code not in klines:
        continue

    df = klines[code]
    buy_date = datetime.strptime(t["buy_date"], "%Y-%m-%d")
    sell_date = datetime.strptime(t["sell_date"], "%Y-%m-%d")

    # Find buy day index
    buy_row = df[df["日期"] == pd.Timestamp(buy_date)]
    sell_row = df[df["日期"] == pd.Timestamp(sell_date)]

    if len(buy_row) == 0 or len(sell_row) == 0:
        continue

    buy_idx = buy_row.index[0]
    sell_idx = sell_row.index[0]
    buy_data = buy_row.iloc[0]
    sell_data = sell_row.iloc[0]

    # Pre-buy technical state (day before or same day)
    pre_idx = max(0, buy_idx - 1)
    pre_data = df.iloc[pre_idx]

    analysis = {
        "stock_name": t["stock_name"],
        "code": code,
        "buy_date": t["buy_date"],
        "pnl_pct": t["pnl_pct"],
        "net_pnl": t["net_pnl"],
        "hold_days": t["hold_days"],
        "is_win": t["net_pnl"] > 0,

        # Pre-buy indicators
        "pre_ma5_above_ma20": bool(pre_data.get("MA5", 0) > pre_data.get("MA20", 0)),
        "pre_ma10_above_ma20": bool(pre_data.get("MA10", 0) > pre_data.get("MA20", 0)),
        "pre_rsi14": float(pre_data.get("RSI14", 50)) if not pd.isna(pre_data.get("RSI14", float('nan'))) else 50,
        "pre_vol_ratio": float(pre_data.get("vol_ratio", 1)) if not pd.isna(pre_data.get("vol_ratio", float('nan'))) else 1,
        "pre_ret_1d": float(df.iloc[pre_idx]["ret"]) if pre_idx > 0 and not pd.isna(df.iloc[pre_idx]["ret"]) else 0,
        "pre_ret_3d": float(df.iloc[max(0,buy_idx-3):buy_idx]["ret"].sum()) if buy_idx >= 3 else 0,
        "pre_ret_5d": float(df.iloc[max(0,buy_idx-5):buy_idx]["ret"].sum()) if buy_idx >= 5 else 0,

        # On-buy indicators
        "buy_high_low": float(buy_data.get("high_low_pct", 0)) if not pd.isna(buy_data.get("high_low_pct", float('nan'))) else 0,
        "buy_vol_ratio": float(buy_data.get("vol_ratio", 1)) if not pd.isna(buy_data.get("vol_ratio", float('nan'))) else 1,

        # During hold
        "hold_period_ret": float(df.iloc[buy_idx:sell_idx+1]["ret"].sum()) if buy_idx < sell_idx else 0,
        "hold_max_drawdown": float(df.iloc[buy_idx:sell_idx+1]["收盘"].min() / buy_data["收盘"] - 1) if buy_idx < sell_idx else 0,

        # Post-sell performance (5 days after)
    }

    # Post-sell: what happened 5 days after selling?
    post_idx = min(len(df) - 1, sell_idx + 5)
    if post_idx > sell_idx:
        post_data = df.iloc[sell_idx:post_idx+1]
        analysis["post_sell_5d_ret"] = float(post_data["ret"].sum()) if len(post_data) > 1 else 0
        analysis["post_sell_5d_high"] = float(post_data["收盘"].max()) if len(post_data) > 1 else 0
        analysis["sold_too_early"] = analysis["post_sell_5d_ret"] > 0.03  # 3%+ means sold too early
    else:
        analysis["post_sell_5d_ret"] = 0
        analysis["post_sell_5d_high"] = 0
        analysis["sold_too_early"] = False

    # Compare vs benchmark
    if benchmark is not None:
        bench_buy = benchmark[benchmark["日期"] == pd.Timestamp(buy_date)]
        bench_sell = benchmark[benchmark["日期"] == pd.Timestamp(sell_date)]
        if len(bench_buy) > 0 and len(bench_sell) > 0:
            bench_buy_price = bench_buy.iloc[0]["close"]
            bench_sell_price = bench_sell.iloc[0]["close"]
            analysis["benchmark_ret"] = float(bench_sell_price / bench_buy_price - 1)
            analysis["excess_return"] = analysis["pnl_pct"] / 100 - analysis["benchmark_ret"]
        else:
            analysis["benchmark_ret"] = 0
            analysis["excess_return"] = 0

    trade_analysis.append(analysis)

# Aggregate by win/loss
winners = [a for a in trade_analysis if a["is_win"]]
losers = [a for a in trade_analysis if not a["is_win"]]

def avg(lst, key):
    vals = [a[key] for a in lst if a[key] is not None and not (isinstance(a[key], float) and np.isnan(a[key]))]
    return np.mean(vals) if vals else 0

def pct_true(lst, key):
    return sum(1 for a in lst if a.get(key)) / len(lst) * 100 if lst else 0

print(f"\n{'='*60}")
print(f"TECHNICAL PATTERN COMPARISON: Winners({len(winners)}) vs Losers({len(losers)})")
print(f"{'='*60}")

comparisons = [
    ("Pre-Buy MA5 > MA20", "pre_ma5_above_ma20", True),
    ("Pre-Buy MA10 > MA20", "pre_ma10_above_ma20", True),
    ("Pre-Buy RSI(14)", "pre_rsi14", None),
    ("Pre-Buy Volume Ratio", "pre_vol_ratio", None),
    ("Pre-Buy 1D Return %", "pre_ret_1d", None),
    ("Pre-Buy 5D Return %", "pre_ret_5d", None),
    ("Hold Max Drawdown %", "hold_max_drawdown", None),
    ("Post-Sell 5D Return %", "post_sell_5d_ret", None),
    ("Sold Too Early (>3%)", "sold_too_early", True),
    ("Excess Return vs 上证", "excess_return", None),
]

for label, key, is_bool in comparisons:
    w_val = pct_true(winners, key) if is_bool else avg(winners, key)
    l_val = pct_true(losers, key) if is_bool else avg(losers, key)
    if is_bool:
        print(f"  {label:30s}: Winners {w_val:.0f}% | Losers {l_val:.0f}%")
    else:
        print(f"  {label:30s}: Winners {w_val:>8.3f} | Losers {l_val:>8.3f}")

# Detailed: buy signal combo analysis
print(f"\n=== Buy Signal Combo Analysis ===")

for a in trade_analysis:
    # Define technical score at buy
    score = 0
    if a["pre_ma5_above_ma20"]: score += 1
    if a["pre_rsi14"] > 30 and a["pre_rsi14"] < 70: score += 1  # not overbought/oversold
    if a["pre_vol_ratio"] > 0.5 and a["pre_vol_ratio"] < 2.5: score += 1  # normal volume
    if a["pre_ret_5d"] > -0.05: score += 1  # not crashing
    a["tech_score"] = score

for score in range(5):
    subset = [a for a in trade_analysis if a["tech_score"] == score]
    if subset:
        wins = sum(1 for a in subset if a["is_win"])
        print(f"  Tech Score {score}/4: {len(subset)} trades, {wins} wins ({wins/len(subset)*100:.0f}%)")

# Save for next phase
with open(os.path.join(OUT_DIR, "trade_analysis.json"), "w", encoding="utf-8") as f:
    # Convert numpy types to native Python
    clean = []
    for a in trade_analysis:
        ca = {}
        for k, v in a.items():
            if isinstance(v, (np.bool_,)):
                ca[k] = bool(v)
            elif isinstance(v, (np.float64, np.float32)):
                ca[k] = float(v) if not np.isnan(v) else 0.0
            elif isinstance(v, (np.int64, np.int32)):
                ca[k] = int(v)
            else:
                ca[k] = v
        clean.append(ca)
    json.dump({"trades": clean, "total": len(clean)}, f, ensure_ascii=False, indent=2)

print(f"\nSaved detailed trade analysis to trade_analysis.json")
