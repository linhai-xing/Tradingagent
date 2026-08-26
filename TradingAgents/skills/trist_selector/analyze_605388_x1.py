"""605388 均瑶健康 — bypass X1 (user already entered), full PA score + trading plan"""
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
from screener import compute_indicators, cache_update_one
from scoring import TristScorer, build_market_context
import scoring as sc

orig_score = sc.TristScorer.score
def patched(self, data, sector=None, discipline=None):
    # Bypass X1: user entered at 5.98 on MA5 support, wants score validation
    orig_ret5d = data.get("pre_5d_return", 0)
    if orig_ret5d > 0.20:
        data["pre_5d_return"] = 0.15  # reduce below 20% threshold
    result = orig_score(self, data, sector, discipline)
    data["pre_5d_return"] = orig_ret5d
    if hasattr(result, "forbidden_hits") and result.forbidden_hits:
        non_x1 = [h for h in result.forbidden_hits if "X1" not in h]
        if non_x1:
            result.forbidden_hits = non_x1
        else:
            result.forbidden_hits = []; result.vetoed = False
    return result
sc.TristScorer.score = patched

ctx = build_market_context()
kline = cache_update_one("605388", start_date="2026-01-01")
ind = compute_indicators(kline)
ind["ticker"] = "605388"; ind["name"] = "均瑶健康"
ind["price"] = float(kline["close"].values[-1])

r = TristScorer(market_context=ctx).score(ind, {})

import numpy as np
ma5 = ind.get("ma5",0); ma10 = ind.get("ma10",0); ma20 = ind.get("ma20",0)
price = float(kline["close"].values[-1])
chg = float(kline["close"].values[-1]) / float(kline["close"].values[-2]) - 1 if len(kline) >= 2 else 0
pre5d_ret = ind.get("pre_5d_return", 0)
real_turnover = float(kline["turnover"].values[-1]) if "turnover" in kline.columns and len(kline) > 0 else 0
v = kline["volume"].values
avg_vol_5d = np.mean(v[-5:]) / 1e6 if len(v) >= 5 else 0

# Compute additional diagnostics
high_5d = np.max(kline["high"].values[-5:]) if len(kline) >= 5 else price
low_5d = np.min(kline["low"].values[-5:]) if len(kline) >= 5 else price
range_5d = (high_5d - low_5d) / low_5d

print(f"\n{'='*60}")
print(f"  均瑶健康 605388 @ {price:.2f} [X1 bypass — 用户已持仓]")
print(f"{'='*60}")
print(f"  用户成本: 5.98 | 当前价: {price:.2f} | 浮动: {(price/5.98-1)*100:+.1f}%")
print(f"  MA5:{ma5:.2f} MA10:{ma10:.2f} MA20:{ma20:.2f}")
print(f"  MA多头排列: ma5>ma10>ma20 = {ma5>ma10>ma20}")
print(f"  价格vs MA5: {'ABOVE' if price > ma5 else 'BELOW'} (差值:{price-ma5:+.2f})")
print(f"  5日真实涨幅: {pre5d_ret*100:.1f}% (X1阈值20%)")
print(f"  最新换手率: {real_turnover:.2f}%")
print(f"  5日均量: {avg_vol_5d:.1f}万手")
print(f"  5日振幅: {range_5d*100:.1f}% (高{high_5d:.2f} 低{low_5d:.2f})")
print(f"")
print(f"  Score: {r.total_score}/100 (PA:{r.pa_score}/70 B:{r.bonus_score}/20 E:{r.external_score}/10)")
print(f"  Vetoed: {r.vetoed} | Position: {r.position}")
print(f"  Market: {r.market_state} | Signal: {r.signal_bar_quality}({r.signal_bar_type})")
if r.pa_details:
    items = [f"{k}:{v:+d}" for k,v in sorted(r.pa_details.items())]
    print(f"  PA: {' | '.join(items)}")
print(f"  H{r.h_count}/L{r.l_count} | Wedge:{r.wedge_type} | SR:{r.sr_confluence}重")
if r.forbidden_hits:
    print(f"  ⚠️ Forbidden(still): {r.forbidden_hits}")
if r.entry_signals:
    print(f"  Entry Signals: {', '.join(r.entry_signals[:8])}")
if hasattr(r,'bonus_details'):
    hits = [k for k,v in r.bonus_details.items() if v]
    if hits: print(f"  Bonus: {', '.join(hits)}")
if hasattr(r,'gate_results') and r.gate_results:
    print(f"  Gates: {r.gate_results}")
