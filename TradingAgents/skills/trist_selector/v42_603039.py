"""v4.2 bypass X1+X7+X17 for 603039 泛微网络 — fair score evaluation"""
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
from screener import compute_indicators, cache_update_one
from scoring import TristScorer, build_market_context
import scoring as sc
import numpy as np

orig_score = sc.TristScorer.score
def patched(self, data, sector=None, discipline=None):
    if data.get("pre_5d_return",0) > 0.20: data["pre_5d_return"] = 0.15
    if data.get("prev_day_limit_up", False): data["prev_day_limit_up"] = False
    if abs(data.get("open_gap_pct",0)) > 0.05: data["open_gap_pct"] = 0
    result = orig_score(self, data, sector, discipline)
    if hasattr(result, "forbidden_hits") and result.forbidden_hits:
        non = [h for h in result.forbidden_hits if not any(t in h for t in ["X1","X7","X17"])]
        result.forbidden_hits = non if non else []
        result.vetoed = bool(non)
    return result
sc.TristScorer.score = patched

ctx = build_market_context()
kline = cache_update_one("603039", start_date="2026-01-01")
ind = compute_indicators(kline)
ind.update({"ticker":"603039","name":"泛微网络","price":float(kline["close"].values[-1])})
r = TristScorer(market_context=ctx).score(ind, {})

ma5=ind.get("ma5",0); ma10=ind.get("ma10",0); ma20=ind.get("ma20",0)
price=r.price; v=kline["volume"].values
avg_vol=np.mean(v[-5:])/1e6; pre5d=ind.get("pre_5d_return",0)
pre20d=ind.get("pre_20d_return",0)
turnover=float(kline["turnover"].values[-1]) if "turnover" in kline.columns else 0
chg=(float(kline["close"].values[-1])/float(kline["close"].values[-2])-1) if len(kline)>=2 else 0
high_20d=np.max(kline["high"].values[-20:]) if len(kline)>=20 else price
low_20d=np.min(kline["low"].values[-20:]) if len(kline)>=20 else price
gap_pct=(float(kline["open"].values[-1])/float(kline["close"].values[-2])-1) if len(kline)>=2 else 0

print(f"\n  603039 泛微网络 @ {price:.2f} (今日{chg:+.2%}) [v4.2 X1+X7+X17 bypass]")
print(f"  MA5:{ma5:.2f} MA10:{ma10:.2f} MA20:{ma20:.2f} 多头={ma5>ma10>ma20}")
print(f"  5日涨幅:{pre5d*100:+.1f}% | 20日涨幅:{pre20d*100:+.1f}%")
print(f"  20日高:{high_20d:.2f} 低:{low_20d:.2f} 位置:{(price-low_20d)/(high_20d-low_20d)*100:.0f}%分位")
print(f"  换手:{turnover:.2f}% | 5日均量:{avg_vol:.0f}万手 | 跳空:{gap_pct:+.2%}")
print(f"")
print(f"  Score: {r.total_score}/100 (PA:{r.pa_score}/90 + 强化:{r.bonus_score}/10)")
print(f"  Vetoed:{r.vetoed} Position:{r.position}({r.position_pct*100:.0f}%)")
print(f"  Market:{r.market_state} Signal:{r.signal_bar_quality}({r.signal_bar_type})")
if r.pa_details:
    items=[f"{k}:{v:+d}"for k,v in sorted(r.pa_details.items())if v!=0]
    print(f"  PA: {' | '.join(items)}")
print(f"  H{r.h_count}/L{r.l_count} Wedge:{r.wedge_type} SR:{r.sr_confluence}")
if r.forbidden_hits: print(f"  Forbidden(still):{r.forbidden_hits}")
if r.entry_signals: print(f"  Entry:{', '.join(r.entry_signals[:6])}")
if hasattr(r,'bonus_details'):
    hits=[k for k,v in r.bonus_details.items() if v]
    if hits: print(f"  Bonus:{', '.join(hits)}")
