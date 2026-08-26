"""600352 浙江龙盛 — bypass X2 liquidity, re-score with full PA analysis"""
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
from screener import compute_indicators, cache_update_one
from scoring import TristScorer, build_market_context
import scoring as sc

orig_score = sc.TristScorer.score
def patched(self, data, sector=None, discipline=None):
    # Bypass X2: user says yesterday's turnover was high
    # Force a healthy turnover to skip X2 check
    orig_turnover = data.get("avg_turnover_5d", 0)
    if orig_turnover < 0.01:
        data["avg_turnover_5d"] = 2.5  # force 2.5% healthy turnover
    result = orig_score(self, data, sector, discipline)
    data["avg_turnover_5d"] = orig_turnover
    if hasattr(result, "forbidden_hits") and result.forbidden_hits:
        non_x2 = [h for h in result.forbidden_hits if "X2" not in h]
        if non_x2:
            result.forbidden_hits = non_x2
        else:
            result.forbidden_hits = []; result.vetoed = False
    return result
sc.TristScorer.score = patched

ctx = build_market_context()
kline = cache_update_one("600352", start_date="2026-01-01")
ind = compute_indicators(kline)
ind["ticker"] = "600352"; ind["name"] = "浙江龙盛"
ind["price"] = float(kline["close"].values[-1])

r = TristScorer(market_context=ctx).score(ind, {})

# Get real turnover data
import numpy as np
v = kline["volume"].values if "volume" in kline.columns else np.array([])
real_avg_vol_5d = np.mean(v[-5:]) / 1e6 if len(v) >= 5 else 0
turnover_5d = [kline.iloc[i]["turnover"] if "turnover" in kline.columns else 0 for i in range(max(0,len(kline)-5), len(kline))]
real_turnover_rate = float(kline["turnover"].values[-1]) if "turnover" in kline.columns and len(kline) > 0 else 0

ma5 = ind.get("ma5",0); ma10 = ind.get("ma10",0); ma20 = ind.get("ma20",0)
price = float(kline["close"].values[-1])
chg = float(kline["close"].values[-1]) / float(kline["close"].values[-2]) - 1 if len(kline) >= 2 else 0

print(f"\n{'='*60}")
print(f"  浙江龙盛 600352 @ {price:.2f} (今日涨跌:{chg:+.2%}) [X2 bypass]")
print(f"{'='*60}")
print(f"  MA5:{ma5:.2f} MA10:{ma10:.2f} MA20:{ma20:.2f} | 多头={'Y' if ma5>ma10>ma20 else 'N'}")
print(f"  真实换手率(最新): {real_turnover_rate:.2f}%")
print(f"  5日均量: {real_avg_vol_5d:.1f}万手")
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
    print(f"  Entry: {', '.join(r.entry_signals[:8])}")
if hasattr(r,'bonus_details'):
    hits = [k for k,v in r.bonus_details.items() if v]
    if hits: print(f"  Bonus: {', '.join(hits)}")
if hasattr(r,'gate_results') and r.gate_results:
    print(f"  Gates: {r.gate_results}")
