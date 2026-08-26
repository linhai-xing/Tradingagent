"""Check 603039 raw K-line data for gap calculation accuracy"""
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
from screener import cache_update_one
import numpy as np

kline = cache_update_one("603039", start_date="2026-07-01")
close = kline["close"].values
open_ = kline["open"].values
high = kline["high"].values
low = kline["low"].values
dates = list(range(len(kline)))

print("603039 泛微网络 — 最近15天原始K线数据")
print(f"{'Idx':<5} {'开盘':>7} {'最高':>7} {'最低':>7} {'收盘':>7} {'昨收→今开跳空':>14} {'涨跌幅':>8}")
print("─" * 62)

for i in range(max(0, len(close)-15), len(close)):
    o = open_[i]; h = high[i]; l = low[i]; c = close[i]
    # Calculate gap: (today_open - yesterday_close) / yesterday_close
    if i > 0:
        gap = (o - close[i-1]) / close[i-1] * 100
        chg = (c - close[i-1]) / close[i-1] * 100
    else:
        gap = 0; chg = 0
    print(f"{i:<5} {o:>7.2f} {h:>7.2f} {l:>7.2f} {c:>7.2f} {gap:>+13.2f}% {chg:>+7.2f}%")

# Check what the screener sees
from screener import compute_indicators
ind = compute_indicators(kline)
gap_value = ind.get("open_gap_pct", 0)
print(f"\nscreener computed open_gap_pct = {gap_value*100:+.2f}%")

# Check latest 2 days raw
print(f"\n最新两根日K:")
print(f"  昨天: O{open_[-2]:.2f} H{high[-2]:.2f} L{low[-2]:.2f} C{close[-2]:.2f}")
print(f"  今天: O{open_[-1]:.2f} H{high[-1]:.2f} L{low[-1]:.2f} C{close[-1]:.2f}")
actual_gap = (open_[-1] - close[-2]) / close[-2] * 100
print(f"  实际跳空 = (今开{open_[-1]:.2f} - 昨收{close[-2]:.2f}) / 昨收{close[-2]:.2f} = {actual_gap:+.2f}%")
print(f"  系统回报 = {gap_value*100:+.2f}%")

# Also check prev_day_limit_up
prev_chg = (close[-2] - close[-3]) / close[-3] * 100 if len(close) >= 3 else 0
print(f"\n前日涨跌幅: {prev_chg:+.2f}%")
print(f"prev_day_limit_up: {ind.get('prev_day_limit_up', 'N/A')}")

# Check 5-day return
close_5d_ago = close[-6] if len(close) >= 6 else close[0]
ret_5d = (close[-1] - close_5d_ago) / close_5d_ago * 100
print(f"5日实际涨幅: {ret_5d:+.2f}% (从{close_5d_ago:.2f}到{close[-1]:.2f})")
print(f"系统pre_5d_return: {ind.get('pre_5d_return', 0)*100:+.2f}%")
