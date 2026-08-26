"""v4.2 deep analysis for 603598 引力传媒 — bypass X7, evaluate MA5 pullback entry"""
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
from screener import compute_indicators, cache_update_one
from scoring import TristScorer, build_market_context
import scoring as sc
import numpy as np

orig_score = sc.TristScorer.score
def patched(self, data, sector=None, discipline=None):
    if data.get("prev_day_limit_up", False): data["prev_day_limit_up"] = False
    result = orig_score(self, data, sector, discipline)
    if hasattr(result, "forbidden_hits") and result.forbidden_hits:
        non = [h for h in result.forbidden_hits if "X7" not in h]
        result.forbidden_hits = non if non else []
        result.vetoed = bool(non)
    return result
sc.TristScorer.score = patched

ctx = build_market_context()
kline = cache_update_one("603598", start_date="2026-01-01")
ind = compute_indicators(kline)

price = float(kline["close"].values[-1])
ind.update({"ticker":"603598","name":"引力传媒","price":price})

# Try realtime
try:
    from direct_api import get_realtime_quote
    rt = get_realtime_quote("603598")
    if rt and rt.get('price',0)>0:
        ind['price'] = rt['price']
        ind['vol_ratio'] = rt.get('vol_ratio', ind.get('vol_ratio',1))
        ind['today_ret'] = rt.get('change_pct',0)/100
        price = rt['price']
except: pass

r = TristScorer(market_context=ctx).score(ind, {})

ma5=ind.get("ma5",0); ma10=ind.get("ma10",0); ma20=ind.get("ma20",0)
pre5d=ind.get("pre_5d_return",0); pre20d=ind.get("pre_20d_return",0)
turnover=float(kline["turnover"].values[-1]) if "turnover" in kline.columns else 0
chg=(float(kline["close"].values[-1])/float(kline["close"].values[-2])-1) if len(kline)>=2 else 0
v=kline["volume"].values
avg_vol_5d=np.mean(v[-5:])/1e6; avg_vol_20d=np.mean(v[-20:])/1e6
high_20d=np.max(kline["high"].values[-20:]) if len(kline)>=20 else price
low_20d=np.min(kline["low"].values[-20:]) if len(kline)>=20 else price
gap_pct=(float(kline["open"].values[-1])/float(kline["close"].values[-2])-1) if len(kline)>=2 else 0

# MA5 pullback analysis
dist_from_ma5 = (price - ma5) / ma5 * 100 if ma5 > 0 else 0
dist_from_ma10 = (price - ma10) / ma10 * 100 if ma10 > 0 else 0
dist_from_ma20 = (price - ma20) / ma20 * 100 if ma20 > 0 else 0

# Check if price has been above MA5 recently (trend strength)
recent_closes = kline["close"].values[-10:] if len(kline)>=10 else kline["close"].values
recent_ma5 = np.convolve(recent_closes, np.ones(5)/5, mode='valid') if len(recent_closes)>=5 else np.array([ma5])
days_above_ma5 = sum(1 for c in recent_closes[-5:] if c > ma5) if ma5>0 else 0

# Get recent K-lines detail
print(f"\n{'='*65}")
print(f"  603598 引力传媒 @ {price:.2f} [v4.2 X7 bypass]")
print(f"{'='*65}")
print(f"  今日涨跌: {chg:+.2%} | 开盘跳空: {gap_pct:+.2%}")
print(f"")
print(f"  --- 均线系统 ---")
print(f"  MA5:  {ma5:.2f}  |  价格距MA5: {dist_from_ma5:+.1f}%")
print(f"  MA10: {ma10:.2f}  |  价格距MA10: {dist_from_ma10:+.1f}%")
print(f"  MA20: {ma20:.2f}  |  价格距MA20: {dist_from_ma20:+.1f}%")
print(f"  多头排列(MA5>MA10>MA20): {ma5>ma10>ma20}")
print(f"  近5日收盘>MA5天数: {days_above_ma5}/5")
print(f"")
print(f"  --- 涨跌幅 ---")
print(f"  5日: {pre5d*100:+.1f}% | 20日: {pre20d*100:+.1f}%")
print(f"  20日高: {high_20d:.2f} | 低: {low_20d:.2f} | 位置: {(price-low_20d)/(high_20d-low_20d)*100:.0f}%分位")
print(f"")
print(f"  --- 量能 ---")
print(f"  换手: {turnover:.2f}% | 5日均量: {avg_vol_5d:.0f}万手 | 20日均量: {avg_vol_20d:.0f}万手")
print(f"  量比(5/20): {avg_vol_5d/avg_vol_20d:.2f}" if avg_vol_20d>0 else "")
print(f"")
print(f"  {'='*65}")
print(f"  Score: {r.total_score}/100 (PA:{r.pa_score}/90 + B:{r.bonus_score}/10)")
print(f"  Vetoed:{r.vetoed} | Position:{r.position}({r.position_pct*100:.0f}%)")
print(f"  Market:{r.market_state} | Signal:{r.signal_bar_quality}({r.signal_bar_type})")
if r.pa_details:
    items=[f"{k}:{v:+d}"for k,v in sorted(r.pa_details.items())if v!=0]
    print(f"  PA: {' | '.join(items)}")
print(f"  H{r.h_count}/L{r.l_count} | Wedge:{r.wedge_type} | SR:{r.sr_confluence}")
if r.forbidden_hits: print(f"  Forbidden(still):{r.forbidden_hits}")
if r.entry_signals: print(f"  Entry: {', '.join(r.entry_signals[:6])}")
if hasattr(r,'bonus_details'):
    hits=[k for k,v in r.bonus_details.items() if v]
    if hits: print(f"  Bonus: {', '.join(hits)}")

# ── MA5 Pullback Entry Assessment ──
print(f"\n{'='*65}")
print(f"  MA5回踩企稳买入评估")
print(f"{'='*65}")

# Checks
checks = []
if ma5 > ma10 > ma20 > 0:
    checks.append(("PASS", "MA多头排列", 3))
else:
    checks.append(("FAIL", f"MA非多头(MA5:{ma5:.2f} MA10:{ma10:.2f} MA20:{ma20:.2f})", -3))

if abs(dist_from_ma5) <= 2:
    checks.append(("PASS", f"价格接近MA5(距{dist_from_ma5:+.1f}%)，回踩到位", 3))
elif abs(dist_from_ma5) <= 4:
    checks.append(("WARN", f"价格距MA5 {dist_from_ma5:+.1f}%，接近但未完全回踩", 1))
else:
    checks.append(("FAIL", f"价格距MA5太远({dist_from_ma5:+.1f}%)，不是回踩", -2))

if r.h_count <= 5:
    checks.append(("PASS", f"H{r.h_count}适中，非抢购高潮", 2))
elif r.h_count <= 8:
    checks.append(("WARN", f"H{r.h_count}偏高，注意追高风险", 0))
else:
    checks.append(("FAIL", f"H{r.h_count}极端，聪明钱可能已派发", -2))

if r.wedge_type == "bull_wedge":
    checks.append(("PASS", "牛旗楔形->趋势中继", 2))
elif r.wedge_type == "bear_wedge":
    checks.append(("FAIL", "熊旗楔形->可能反转", -2))
else:
    checks.append(("WARN", f"楔形:{r.wedge_type}", 0))

if r.signal_bar_quality in ("excellent","good"):
    checks.append(("PASS", f"信号K线:{r.signal_bar_quality}", 2))
elif r.signal_bar_quality == "fair":
    checks.append(("WARN", f"信号K线:{r.signal_bar_quality}", 0))
else:
    checks.append(("FAIL", "信号K线:poor", -1))

if r.sr_confluence >= 2:
    checks.append(("PASS", f"SR共振{r.sr_confluence}重，止损可锚定", 2))
elif r.sr_confluence == 1:
    checks.append(("WARN", f"SR共振仅{r.sr_confluence}重", 0))
else:
    checks.append(("FAIL", "无SR共振，止损无处可锚", -2))

if avg_vol_5d >= avg_vol_20d * 0.8:
    checks.append(("PASS", "量能维持，未明显缩量", 1))
else:
    checks.append(("WARN", "缩量明显，需等放量", -1))

if pre5d <= 0.20:
    checks.append(("PASS", f"5日涨幅{pre5d*100:.1f}%未过热", 1))
else:
    checks.append(("FAIL", f"5日涨幅{pre5d*100:.1f}%偏高", -2))

print(f"\n  {'指标':<30} {'判定':<6} {'说明'}")
print(f"  {'─'*60}")
total_score_check = 0
for icon, desc, pts in checks:
    print(f"  {desc:<30} {icon:<6} ({pts:+d})")
    total_score_check += pts
print(f"  {'─'*60}")
print(f"  回踩买入评分: {total_score_check} (满分18, 及格10)")

print(f"\n  --- 结论 ---")
if total_score_check >= 12 and r.total_score >= 35:
    print(f"  [可考虑] MA5回踩买入条件基本满足，但注意仓位控制")
    print(f"  建议入场: 在{ma5:.2f}附近挂单")
    print(f"  止损: {ma10:.2f}(MA10) 或 {ma20:.2f}(MA20)")
    print(f"  止盈: {high_20d:.2f}(20日高)")
elif total_score_check >= 8:
    print(f"  [观望] 部分条件满足但存在硬伤，等信号改善")
else:
    print(f"  [不建议] 多项条件不满足，MA5回踩买入风险较大")

# ── Price levels ──
print(f"\n{'='*65}")
print(f"  关键价位")
print(f"{'='*65}")
print(f"  阻力2: {high_20d:.2f} (20日高)")
if ma5 > price:
    print(f"  阻力1: {ma5:.2f} (MA5) ← 价格在MA5下方")
else:
    print(f"  支撑1: {ma5:.2f} (MA5)")
print(f"  支撑2: {ma10:.2f} (MA10)")
print(f"  支撑3: {ma20:.2f} (MA20)")
print(f"  强支撑: {low_20d:.2f} (20日低)")
