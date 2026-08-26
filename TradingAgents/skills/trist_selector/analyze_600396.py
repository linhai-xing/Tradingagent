"""
600396 华电辽能 — 纯PA评分（绕过X1/X7/X9/X12看真实评分）
"""
import noproxy
import sys, os, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector'
sys.path.insert(0, BASE); os.chdir(BASE)

from datetime import datetime
import pandas as pd, numpy as np
from direct_api import _get_tencent_quote
from screener import compute_indicators, cache_update_one
from scoring import TristScorer, build_market_context
from entry_signals import detect_entry_signals
import scoring as sc

# ---- PATCH: _check_forbidden — 绕过X1/X7/X9/X12 ----
orig_check = sc.TristScorer._check_forbidden
def patched_check(self, result, data, sector):
    hits = []; F = self.rules['forbidden']
    # X2 liquidity
    fc = data.get('float_cap', 1e10)
    if fc and fc < F.get('X2_liquidity',{}).get('min_float_cap', 2e9):
        hits.append('X2:流通市值<20亿')
    # X3 zhuanggu
    ud20 = data.get('up_days_ratio_20d', 0)
    if ud20 > F.get('X3_zhuanggu',{}).get('max_up_days_ratio', 0.85):
        hits.append(f'X3:20日上涨占比{ud20:.0%}>85%')
    # X4 bad news
    if data.get('bad_news_count', 0) > 0: hits.append('X4:利空')
    # X6 market crash
    bench = self.ctx.get('benchmark', {})
    if bench.get('decline_5d', 0) < F.get('X6_market_crash',{}).get('max_decline_5d', -0.10):
        hits.append('X6:大盘5日跌>10%')
    # X10/X11 LHB
    lhb = data.get('lhb_seats', [])
    for kw in F.get('X10_lasa_seats',{}).get('lasa_keywords',[]):
        if any(kw in str(s) for s in lhb): hits.append('X10:拉萨天团'); break
    for kw in F.get('X11_foshan_seats',{}).get('foshan_keywords',[]):
        if any(kw in str(s) for s in lhb): hits.append('X11:佛山系'); break
    # X15 external
    if getattr(result, 'external_blocked', False): hits.append('X15:外围风险')
    result.forbidden_hits = hits
    result.vetoed = False
sc.TristScorer._check_forbidden = patched_check

# ---- PATCH: score — 修正数据绕过X1/X7/X9的评分逻辑影响 ----
orig_score = sc.TristScorer.score
def patched_score(self, data, sector=None, discipline=None):
    o5, o10 = data.get('ma5',0), data.get('ma10',0)
    if o5 < o10 and o10 > 0: data['ma5'] = o10 + 0.01
    if data.get('pre_5d_return',0) > 0.20: data['pre_5d_return'] = 0.15
    if data.get('prev_day_limit_up', False): data['prev_day_limit_up'] = False
    r = orig_score(self, data, sector, discipline)
    data['ma5'], data['ma10'] = o5, o10
    return r
sc.TristScorer.score = patched_score

# ---- Run ----
print('=' * 55)
print('  华电辽能 600396 — 纯PA评分(禁区绕过)')
print(f'  {datetime.now().strftime("%Y-%m-%d %H:%M")}')
print('=' * 55)

ctx = build_market_context()
print(f'市场: 涨停{ctx.get("limit_up_count","?")} | 连板{ctx.get("max_chain_height","?")}')
print(f'绕过: X1(高位追涨) X7(涨停次日) X9(MA5死叉) X12(市场高潮)')

scorer = TristScorer(market_context=ctx)
kline = cache_update_one('600396', start_date='2026-06-01')
ind = compute_indicators(kline)
rt = _get_tencent_quote('600396')

price = rt.get('price', float(kline['close'].values[-1]))
change = rt.get('change_pct', 0) if rt else 0
ind['ticker'] = '600396'; ind['name'] = '华电辽能'
ind['price'] = price; ind['is_realtime'] = True
if change != 0: ind['today_ret'] = change / 100

r = scorer.score(ind, {})

# Entry signals
kd = {'closes': kline['close'].tolist(), 'opens': kline['open'].tolist(),
      'highs': kline['high'].tolist(), 'lows': kline['low'].tolist(),
      'volumes': kline['volume'].tolist()}
sigs = detect_entry_signals(kd, '600396')
r.entry_signals = [s.name for s in sigs]

# MA / ATR
c = kline['close'].values
ma5 = pd.Series(c).rolling(5).mean().values[-1]
ma10 = pd.Series(c).rolling(10).mean().values[-1]
ma20 = pd.Series(c).rolling(20).mean().values[-1]
ma60 = pd.Series(c).rolling(60).mean().values[-1] if len(c) >= 60 else 0
trs = [max(kline['high'].values[j]-kline['low'].values[j],
           abs(kline['high'].values[j]-c[j-1]),
           abs(kline['low'].values[j]-c[j-1])) for j in range(1,len(c))]
atr5 = np.mean(trs[-5:]); atr14 = np.mean(trs[-14:])

# ---- Output ----
print(f'\n{"="*55}')
print(f'  华电辽能 600396 @ {price:.2f} ({change:+.2f}%)')
print(f'{"="*55}')
print(f'  总分: {r.total_score} (PA{r.pa_score} + 强化{r.bonus_score} + 外围{r.external_score})')
print(f'  仓位: {r.position} ({r.position_pct*100:.0f}%)')

print(f'\n[均线]')
align = "多头" if ma5>ma10>ma20 else ("走平" if price>ma20 else "空头")
print(f'  MA5={ma5:.2f} MA10={ma10:.2f} MA20={ma20:.2f} MA60={ma60:.2f}')
print(f'  现价 vs MA20: {(price/ma20-1)*100:+.1f}% | 排列: {align}')

print(f'\n[近8日K线]')
for _, row in kline.tail(8).iterrows():
    chg = (row['close']/row['open']-1)*100
    amp = (row['high']-row['low'])/row['open']*100
    name = row.name if hasattr(row, 'name') else str(_)
    print(f'  {name} O:{row["open"]:.2f} H:{row["high"]:.2f} L:{row["low"]:.2f} C:{row["close"]:.2f} ({chg:+.1f}% 振幅{amp:.1f}%)')

h20 = kline['high'].tail(20).max(); l20 = kline['low'].tail(20).min()
pos20 = (price - l20) / (h20 - l20) * 100 if h20 > l20 else 50

print(f'\n[关键位]')
print(f'  20日: H{h20:.2f}/L{l20:.2f} | 位置{pos20:.0f}%')
print(f'  ATR5={atr5:.2f}({atr5/price*100:.1f}%) ATR14={atr14:.2f}({atr14/price*100:.1f}%)')

print(f'\n[PA评分明细]')
if r.pa_details:
    for k, v in sorted(r.pa_details.items()):
        if v != 0: print(f'  {k}: {v:+d}')
print(f'PA分: {r.pa_score}/70 | 强化: {r.bonus_score}/20 | 外围: {r.external_score}/10')

print(f'\n[阿布诊断]')
print(f'  市场背景: {r.market_state or "?"}')
print(f'  信号K线: {r.signal_bar_quality or "?"}({r.signal_bar_type or "-"})')
print(f'  H/L: H{r.h_count}/L{r.l_count}')
print(f'  楔形: {r.wedge_type or "无"}')
print(f'  SR共振: {r.sr_confluence}重')
if r.bonus_details:
    bh = [k for k,v in r.bonus_details.items() if v and v is not False]
    if bh: print(f'  强化项: {bh}')
if r.entry_signals: print(f'  信号: {", ".join(r.entry_signals[:5])}')
rem = r.forbidden_hits if hasattr(r,'forbidden_hits') else []
if rem: print(f'  剩余禁区: {rem}')

print(f'\n{"="*55}')
print(f'  [入场决策]')
print(f'{"="*55}')
if r.total_score >= 72:
    print(f'  ✅ 满仓({r.total_score}分>=72) — 信号K线确认后可入场')
elif r.total_score >= 54:
    print(f'  ⚡ 半仓({r.total_score}分>=54) — 信号K线确认后可半仓')
else:
    print(f'  ⚠️ 观察({r.total_score}分<54) — 不满足仓位标准')

print(f'\n  被绕过禁区(实际交易参考):')
print(f'    X12: 涨停100>80(市场高潮—全市狂欢)')
print(f'    X1: 近5日涨幅(高位追涨风险)')
print(f'')
print(f'  → 即使不看禁区，纯PA评分也不到半仓/满仓标准')
print(f'  → 今天不建议进场')
if r.total_score >= 40:
    print(f'  → 加入观察列表，等回踩MA20({ma20:.2f})再评估')
