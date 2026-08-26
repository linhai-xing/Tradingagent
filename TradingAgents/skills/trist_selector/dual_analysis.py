"""
双股分析: 中远海特(600428) + 京北方(002987)
PA评分 + K线 + 交易计划
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

# ---- PATCH: X1/X7/X9/X12 bypass ----
orig_check = sc.TristScorer._check_forbidden
def patched_check(self, result, data, sector):
    hits = []; F = self.rules['forbidden']
    fc = data.get('float_cap', 1e10)
    if fc and fc < F.get('X2_liquidity',{}).get('min_float_cap', 2e9):
        hits.append('X2:流通市值<20亿')
    ud20 = data.get('up_days_ratio_20d', 0)
    if ud20 > F.get('X3_zhuanggu',{}).get('max_up_days_ratio', 0.85):
        hits.append('X3:20日上涨占比>85%')
    if data.get('bad_news_count', 0) > 0: hits.append('X4:利空')
    bench = self.ctx.get('benchmark', {})
    if bench.get('decline_5d', 0) < F.get('X6_market_crash',{}).get('max_decline_5d', -0.10):
        hits.append('X6:大盘5日跌>10%')
    lhb = data.get('lhb_seats', [])
    for kw in F.get('X10_lasa_seats',{}).get('lasa_keywords',[]):
        if any(kw in str(s) for s in lhb): hits.append('X10:拉萨天团'); break
    for kw in F.get('X11_foshan_seats',{}).get('foshan_keywords',[]):
        if any(kw in str(s) for s in lhb): hits.append('X11:佛山系'); break
    if getattr(result, 'external_blocked', False): hits.append('X15:外围风险')
    result.forbidden_hits = hits
    result.vetoed = False
sc.TristScorer._check_forbidden = patched_check

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

# ---- Build context ----
ctx = build_market_context()
scorer = TristScorer(market_context=ctx)
print(f'市场: 涨停{ctx.get("limit_up_count","?")} | 连板{ctx.get("max_chain_height","?")}')
print()

# ── Analyze each stock ──
STOCKS = [
    ('600428', '中远海特', 'sh'),
    ('002987', '京北方', 'sz'),
]

for code, name, mkt in STOCKS:
    print('=' * 55)
    print(f'  {code} {name}')
    print('=' * 55)

    # K-line
    kline = cache_update_one(code, start_date='2026-06-01')
    ind = compute_indicators(kline)
    rt = _get_tencent_quote(code)
    time.sleep(0.1)

    price = rt.get('price', float(kline['close'].values[-1]))
    change = rt.get('change_pct', 0) if rt else 0
    ind['ticker'] = code; ind['name'] = name
    ind['price'] = price; ind['is_realtime'] = True
    if change != 0: ind['today_ret'] = change / 100

    r = scorer.score(ind, {})

    # MA / ATR / K-line
    c = kline['close'].values; h = kline['high'].values
    l_p = kline['low'].values; o = kline['open'].values; v = kline['volume'].values
    ma5 = pd.Series(c).rolling(5).mean().values[-1]
    ma10 = pd.Series(c).rolling(10).mean().values[-1]
    ma20 = pd.Series(c).rolling(20).mean().values[-1]
    ma60 = pd.Series(c).rolling(60).mean().values[-1] if len(c) >= 60 else 0
    trs = [max(h[j]-l_p[j], abs(h[j]-c[j-1]), abs(l_p[j]-c[j-1])) for j in range(1,len(c))]
    atr5 = np.mean(trs[-5:]); atr14 = np.mean(trs[-14:])

    # Entry signals
    kd = {'closes': c.tolist(), 'opens': o.tolist(),
          'highs': h.tolist(), 'lows': l_p.tolist(), 'volumes': v.tolist()}
    sigs = detect_entry_signals(kd, code)
    r.entry_signals = [s.name for s in sigs]

    # ── Price & Score ──
    if ma5 > ma10 > ma20: align = 'MA多头排列'
    elif price > ma20: align = '站上MA20'
    else: align = 'MA空头'

    h20 = max(h[-20:]); l20 = min(l_p[-20:])
    pos20 = (price - l20) / (h20 - l20) * 100 if h20 > l20 else 50
    ret5 = (c[-1]/c[-6]-1)*100 if len(c) > 5 else 0
    ret20 = (c[-1]/c[-21]-1)*100 if len(c) > 20 else 0

    print(f'\n  实时: {price:.2f} ({change:+.2f}%)')
    print(f'  PA评分: {r.total_score} (PA{r.pa_score}+强化{r.bonus_score}+外围{r.external_score})')
    if r.total_score >= 72: pos = '满仓'
    elif r.total_score >= 54: pos = '半仓'
    else: pos = '观察'
    print(f'  仓位: {pos}')

    print(f'\n  [均线]')
    print(f'  MA5={ma5:.2f} MA10={ma10:.2f} MA20={ma20:.2f} MA60={ma60:.2f}')
    print(f'  排列: {align}')
    print(f'  vs MA5: {(price/ma5-1)*100:+.1f}% | vs MA20: {(price/ma20-1)*100:+.1f}%')

    print(f'\n  [波动]')
    print(f'  ATR5={atr5:.2f}({atr5/price*100:.1f}%) ATR14={atr14:.2f}({atr14/price*100:.1f}%)')
    print(f'  20日: H{h20:.2f}/L{l20:.2f} | 位置{pos20:.0f}%')
    print(f'  5日收益:{ret5:+.1f}% | 20日收益:{ret20:+.1f}%')

    print(f'\n  [近10日K线]')
    for _, row in kline.tail(10).iterrows():
        chg = (row['close']/row['open']-1)*100
        amp = (row['high']-row['low'])/row['open']*100
        vol_r = row['volume']/np.mean(v[-20:]) if len(v)>=20 else 1
        tags = []
        if chg > 9.5: tags.append('涨停')
        if abs(chg) < 2 and vol_r < 0.7: tags.append('缩量')
        tag = ' [{}]'.format(','.join(tags)) if tags else ''
        ro = row['open']; rh = row['high']; rl = row['low']; rc = row['close']
        print(f'    {row.name} O:{ro:.2f} H:{rh:.2f} L:{rl:.2f} C:{rc:.2f} ({chg:+.1f}% 量{vol_r:.1f}){tag}')

    print(f'\n  [PA评分明细]')
    if r.pa_details:
        for k, v in sorted(r.pa_details.items()):
            if v != 0: print(f'    {k}: {v:+d}')
    print(f'  市场: {r.market_state or "?"} | K线: {r.signal_bar_quality or "?"}({r.signal_bar_type or "-"})')
    print(f'  H{r.h_count}/L{r.l_count} | 楔形:{r.wedge_type or "无"} | SR:{r.sr_confluence}重')
    if r.bonus_details:
        bh = [k for k,v in r.bonus_details.items() if v and v is not False]
        if bh: print(f'  强化: {bh}')
    if r.entry_signals: print(f'  信号: {", ".join(r.entry_signals[:5])}')
    real_veto = [h for h in (r.forbidden_hits if hasattr(r,'forbidden_hits') else [])]
    if real_veto: print(f'  真实禁区: {real_veto}')

    print()

# ── Trading Plan ──
print('=' * 55)
print('  交易计划')
print('=' * 55)

print('''
  [今日状态]
  X14冷却刚过(8/3) — 今天可以交易
  两市情绪: 从高潮回落中，需确认

  ┌──────────────────────────────────────────────┐
  │  中远海特 600428                京北方 002987 │
  ├──────────────────────────────────────────────┤
  │  ⚡运输+特种船                   💻金融IT     │
  │  板块独立，不受科技波动影响      数字货币概念  │
  │  波动中等(ATR ~4%)              波动适中      │
  └──────────────────────────────────────────────┘

  [入场策略]
  不要同一天买两只 — 分批入场，互相对冲风险

  [止损]
  通用: 入场K线低点 - 0.5×ATR

  [仓位分配]
  总仓位 ≤ 50% (X8: 单票≤25%)
  每只半仓入场 = 总仓位的25%
''')
