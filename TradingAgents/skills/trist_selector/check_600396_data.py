"""Check 600396 raw K-line vs Tencent live — find MA5 discrepancy"""
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
from screener import cache_update_one
import numpy as np

kline = cache_update_one("600396", start_date="2026-07-15")
close = kline["close"].values
n = len(close)

# Tencent live
from direct_api import _get_tencent_quote
tq = _get_tencent_quote("600396")
live_price = tq.get('price', 0) if tq else 0
live_open = tq.get('open', 0) if tq else 0
live_prev = tq.get('prev_close', 0) if tq else 0

print("600396 华电辽能 — K线缓存 vs 腾讯实时")
print(f"腾讯实时: 现价{live_price:.2f} 开盘{live_open:.2f} 昨收{live_prev:.2f}")
print()

# Show last 10 cached K-lines
print("缓存最近10根日K:")
print(f"{'Idx':<5} {'开':>7} {'高':>7} {'低':>7} {'收':>7} {'量(万)':>8}")
for i in range(max(0, n-10), n):
    o=kline["open"].values[i]; h=kline["high"].values[i]
    l=kline["low"].values[i]; c=close[i]
    v=kline["volume"].values[i]/1e4
    print(f"{i:<5} {o:>7.2f} {h:>7.2f} {l:>7.2f} {c:>7.2f} {v:>8.0f}")

# Compute MA5 manually from cached data
print()
ma5_cached = np.mean(close[-5:]) if n>=5 else 0
print(f"缓存MA5(最近5根收盘均值): {ma5_cached:.2f}")
print(f"  = ({close[-5]:.2f} + {close[-4]:.2f} + {close[-3]:.2f} + {close[-2]:.2f} + {close[-1]:.2f}) / 5")

# Compute MA5 if we substitute latest Tencent price for last close
if live_price > 0:
    closes_with_live = list(close[-4:]) + [live_price]
    ma5_with_live = np.mean(closes_with_live)
    print(f"\n用腾讯实时价替代最新缓存收盘价:")
    print(f"MA5 = ({closes_with_live[0]:.2f} + {closes_with_live[1]:.2f} + {closes_with_live[2]:.2f} + {closes_with_live[3]:.2f} + {closes_with_live[4]:.2f}) / 5")
    print(f"    = {ma5_with_live:.2f}")

# User says MA5 should be 16.86 — what closes would give that?
print(f"\n用户平台MA5: 16.86")
print(f"要达到16.86，最近5天收盘均值 = 16.86")
print(f"总和 = 16.86 × 5 = 84.30")
print(f"如果最近4天缓存收盘为: {close[-4]:.2f} {close[-3]:.2f} {close[-2]:.2f} {close[-1]:.2f}")
print(f"则今天收盘需为: {84.30 - sum(close[-4:]):.2f}")

# Check: is the cached data missing the most recent day?
# Compare last cached close vs Tencent prev_close
print(f"\n数据一致性:")
print(f"缓存最新收盘: {close[-1]:.2f}")
print(f"腾讯昨收: {live_prev:.2f}")
print(f"腾讯现价: {live_price:.2f}")
if abs(close[-1] - live_prev) < 0.05:
    print("→ 缓存数据与腾讯同步 ✅")
else:
    print(f"→ 缓存数据滞后！差{live_prev - close[-1]:.2f}元")
    print(f"→ 缓存缺失了最近交易日的数据！")
