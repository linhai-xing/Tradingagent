"""600428 中远海特 — bypass X12 climax, full PA score + CZSC integration"""
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
from screener import compute_indicators, cache_update_one
from scoring import TristScorer, build_market_context
import scoring as sc
import numpy as np

orig_score = sc.TristScorer.score
def patched(self, data, sector=None, discipline=None):
    # Bypass X12: user wants to see underlying score regardless of market euphoria
    result = orig_score(self, data, sector, discipline)
    if hasattr(result, "forbidden_hits") and result.forbidden_hits:
        non_x12 = [h for h in result.forbidden_hits if "X12" not in h]
        if non_x12:
            result.forbidden_hits = non_x12
        else:
            result.forbidden_hits = []; result.vetoed = False
    return result
sc.TristScorer.score = patched

ctx = build_market_context()
kline = cache_update_one("600428", start_date="2026-01-01")
ind = compute_indicators(kline)
ind["ticker"] = "600428"; ind["name"] = "中远海特"
ind["price"] = float(kline["close"].values[-1])

r = TristScorer(market_context=ctx).score(ind, {})

ma5 = ind.get("ma5",0); ma10 = ind.get("ma10",0); ma20 = ind.get("ma20",0)
price = float(kline["close"].values[-1])
chg = float(kline["close"].values[-1]) / float(kline["close"].values[-2]) - 1 if len(kline) >= 2 else 0
pre5d = ind.get("pre_5d_return", 0)
pre20d = ind.get("pre_20d_return", 0)
turnover = float(kline["turnover"].values[-1]) if "turnover" in kline.columns and len(kline) > 0 else 0
v = kline["volume"].values
avg_vol_5d = np.mean(v[-5:]) / 1e6 if len(v) >= 5 else 0
avg_vol_20d = np.mean(v[-20:]) / 1e6 if len(v) >= 20 else 0
vol_ratio = avg_vol_5d / avg_vol_20d if avg_vol_20d > 0 else 0
high_20d = np.max(kline["high"].values[-20:]) if len(kline) >= 20 else price
low_20d = np.min(kline["low"].values[-20:]) if len(kline) >= 20 else price
gap_pct = (float(kline["open"].values[-1]) / float(kline["close"].values[-2]) - 1) if len(kline) >= 2 else 0

print(f"\n{'='*65}")
print(f"  中远海特 600428 @ {price:.2f} [X12 bypass — 忽略高潮期]")
print(f"{'='*65}")
print(f"  今日涨跌: {chg:+.2%} | 开盘跳空: {gap_pct:+.2%}")
print(f"")
print(f"  --- 均线系统 ---")
print(f"  MA5:{ma5:.2f}  MA10:{ma10:.2f}  MA20:{ma20:.2f}")
print(f"  多头排列(MA5>MA10>MA20): {ma5>ma10>ma20}")
print(f"  价格vs MA5: {price-ma5:+.2f} | vs MA10: {price-ma10:+.2f} | vs MA20: {price-ma20:+.2f}")
print(f"")
print(f"  --- 涨跌幅 ---")
print(f"  5日: {pre5d*100:+.1f}% | 20日: {pre20d*100:+.1f}%")
print(f"  20日最高: {high_20d:.2f} | 最低: {low_20d:.2f} | 当前位置: {(price-low_20d)/(high_20d-low_20d)*100:.0f}%分位")
print(f"")
print(f"  --- 量能 ---")
print(f"  换手率: {turnover:.2f}% | 5日均量: {avg_vol_5d:.0f}万手 | 量比: {vol_ratio:.2f}")
print(f"")
print(f"  {'='*65}")
print(f"  Score: {r.total_score}/100 (PA:{r.pa_score}/70 B:{r.bonus_score}/20 E:{r.external_score}/10)")
print(f"  Vetoed: {r.vetoed} | Position: {r.position}")
print(f"  Market: {r.market_state} | Signal: {r.signal_bar_quality}({r.signal_bar_type})")
if r.pa_details:
    items = [f"{k}:{v:+d}" for k,v in sorted(r.pa_details.items())]
    print(f"  PA: {' | '.join(items)}")
print(f"  H{r.h_count}/L{r.l_count} | Wedge:{r.wedge_type} | SR:{r.sr_confluence}重")
if r.forbidden_hits:
    print(f"  Forbidden(still): {r.forbidden_hits}")
if r.entry_signals:
    print(f"  Entry: {', '.join(r.entry_signals[:8])}")
if hasattr(r,'bonus_details'):
    hits = [k for k,v in r.bonus_details.items() if v]
    if hits: print(f"  Bonus: {', '.join(hits)}")
if hasattr(r,'gate_results') and r.gate_results:
    print(f"  Gates: {r.gate_results}")

# Additional CZSC cross-check hints
print(f"\n  --- 缠论交叉验证提示 ---")
print(f"  最近CZSC分型: 07-31底分型10.51 / 07-30顶分型11.50")
print(f"  缠论趋势: 上升趋势(高低点均抬高)")
print(f"  当前价{price:.2f} vs 前底分型10.51: {'上方' if price > 10.51 else '下方'}")
print(f"  如回踩10.51不破 -> 缠论二买确认")
print(f"  如跌破9.84 -> 上升笔破坏")
