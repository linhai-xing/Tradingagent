"""600986 浙文互联 — extended history + trading plan"""
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
from screener import compute_indicators, cache_update_one
from scoring import TristScorer, build_market_context
import scoring as sc
import numpy as np

# Bypass all forbidden
sc.TristScorer._check_forbidden = lambda self, result, data, sector: None

ctx = build_market_context()

# Get 1 year of data
kline = cache_update_one("600986", start_date="2025-08-01")
close = kline["close"].values; high = kline["high"].values; low = kline["low"].values
open_ = kline["open"].values; vol = kline["volume"].values
n = len(close)

ind = compute_indicators(kline)

# Tencent live price
from direct_api import _get_tencent_quote
tq = _get_tencent_quote("600986")
price = tq.get('price', float(close[-1]))
chg = tq.get('change_pct', 0)
ind["price"] = price; ind["ticker"] = "600986"; ind["name"] = "浙文互联"

r = TristScorer(market_context=ctx).score(ind, {})

ma5 = ind.get("ma5",0); ma10 = ind.get("ma10",0); ma20 = ind.get("ma20",0)
ma60 = float(np.mean(close[-60:])) if n>=60 else 0
ma120 = float(np.mean(close[-120:])) if n>=120 else 0
pre5d = ind.get("pre_5d_return",0); pre20d = ind.get("pre_20d_return",0)
high_20d = np.max(high[-20:]); low_20d = np.min(low[-20:])
avg_vol5 = np.mean(vol[-5:])/1e6; avg_vol20 = np.mean(vol[-20:])/1e6

# Find consolidation period (low volatility, tight range)
# Look for periods where 20-day range < 10%
consolidations = []
for i in range(100, n-20, 20):
    seg_high = np.max(high[i:i+20])
    seg_low = np.min(low[i:i+20])
    seg_range = (seg_high - seg_low) / seg_low
    if seg_range < 0.15:
        consolidations.append((i, seg_low, seg_high, seg_range))

# Find recent breakout
recent_breakout = None
for i in range(n-30, n-1):
    if i > 10 and close[i] > np.max(high[max(0,i-60):i]) * 0.95:
        recent_breakout = i
        break

# Key price zones
# Find previous platform (area of price congestion before breakout)
prev_highs = []
for i in range(max(0, n-120), n-20):
    if i > 10 and high[i] > np.max(high[max(0,i-10):i]):
        prev_highs.append((i, high[i]))
prev_highs.sort(key=lambda x: x[1], reverse=True)

print(f"\n{'='*65}")
print(f"  600986 浙文互联 — 长周期结构分析 ({n}根日K)")
print(f"{'='*65}")
print(f"  现价: {price:.2f} ({chg:+.2f}%) | 你的成本: 8.20")
print(f"  浮动: {(price/8.20-1)*100:+.1f}%")
print(f"")
print(f"  均线系统:")
print(f"  MA5:{ma5:.2f} MA10:{ma10:.2f} MA20:{ma20:.2f} MA60:{ma60:.2f} MA120:{ma120:.2f}")
print(f"  多头(5>10>20>60>120): {ma5>ma10>ma20>ma60>ma120}")
print(f"  价格vs MA5: {price-ma5:+.2f} | vs MA20: {price-ma20:+.2f} | vs MA60: {price-ma60:+.2f}")

# Find key structural levels
# Recent significant highs and lows
print(f"\n  --- 关键结构价位 ---")
seg_size = max(20, n // 6)
for seg_start in range(0, n, seg_size):
    seg_end = min(seg_start+seg_size, n)
    seg_h = np.max(high[seg_start:seg_end])
    seg_l = np.min(low[seg_start:seg_end])
    seg_c_first = close[seg_start]
    seg_c_last = close[seg_end-1]
    seg_ret = (seg_c_last/seg_c_first-1)*100
    seg_vol_avg = np.mean(vol[seg_start:seg_end])/1e6
    bar = "█" * max(1, int(abs(seg_ret)/5))
    print(f"  [{seg_start:>4}-{seg_end:<4}] 高{seg_h:.2f} 低{seg_l:.2f} 区间:{seg_h-seg_l:.2f} 涨幅{seg_ret:+5.1f}% {bar} 均量{seg_vol_avg:.0f}万")

# Score
print(f"\n  Score: {r.total_score}/100 (PA:{r.pa_score}/90 + B:{r.bonus_score}/10)")
print(f"  Position: {r.position} | Market: {r.market_state} | Signal: {r.signal_bar_quality}({r.signal_bar_type})")
if r.pa_details:
    items = [f"{k}:{v:+d}" for k,v in sorted(r.pa_details.items()) if v!=0]
    print(f"  PA: {' | '.join(items)}")
print(f"  H{r.h_count}/L{r.l_count} | Wedge:{r.wedge_type} | SR:{r.sr_confluence}")
print(f"  5日涨幅:{pre5d*100:+.1f}% | 20日:{pre20d*100:+.1f}%")
print(f"  20日高:{high_20d:.2f} 低:{low_20d:.2f} 分位:{(price-low_20d)/(high_20d-low_20d)*100:.0f}%")

# Support/resistance levels
print(f"\n  --- 支撑阻力位 ---")
print(f"  阻力3: {np.max(high[-60:]):.2f} (60日高)")
print(f"  阻力2: {np.max(high[-20:]):.2f} (20日高)")
print(f"  阻力1: MA5 {ma5:.2f}")
print(f"  ─────── 当前 {price:.2f} ───────")
print(f"  支撑1: {ma10:.2f} (MA10)")
print(f"  支撑2: {ma20:.2f} (MA20)")
print(f"  支撑3: {ma60:.2f} (MA60)")
print(f"  强支撑: {np.min(low[-60:]):.2f} (60日低)")
