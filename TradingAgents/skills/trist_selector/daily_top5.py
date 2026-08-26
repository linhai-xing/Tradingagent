"""
Trist Selector v4.1 — 双股评分 + 全市场Top5
标准: 100分制, 80满仓/60半仓
"""
import noproxy
import sys, os, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector'
sys.path.insert(0, BASE); os.chdir(BASE)

from datetime import datetime
import pandas as pd, numpy as np
from direct_api import _get_tencent_quote
from data_cache import _load_cache
from screener import compute_indicators, cache_update_one
from scoring import TristScorer, build_market_context
from entry_signals import detect_entry_signals

print("=" * 60)
print(f"  Trist Selector v4.1 — 全市场Top5 + 双股深度")
print(f"  标准: 100分制 | 80满仓 | 60半仓")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 60)

# ── Market context ──
ctx = build_market_context()
lu = ctx.get('limit_up_count', '?')
print(f"\n市场: 涨停{lu} | 连板{ctx.get('max_chain_height','?')}")
x12_warn = lu > 80 if isinstance(lu, int) else False
if x12_warn: print(f"⚠️ X12活跃: 涨停{lu}>80 — 高潮期谨慎")

# ══════════════════════════════════════════════════════
# Part 1: 全市场 Top 5 (Tencent fallback)
# ══════════════════════════════════════════════════════
print(f"\n{'='*60}")
print(f"  Part 1: 全市场 Top 5")
print(f"{'='*60}")

CACHE_DIR = os.path.join(BASE, 'data_cache')
all_tickers = sorted([f.replace('.csv','') for f in os.listdir(CACHE_DIR) if f.endswith('.csv')])

# Pre-filter: MA aligned + not extreme low/high
trending = []
for t in all_tickers:
    df = _load_cache(t)
    if len(df) < 20: continue
    ind = compute_indicators(df)
    if not ind: continue
    ma5 = ind.get('ma5',0); ma10 = ind.get('ma10',0); ma20 = ind.get('ma20',0)
    price = float(df['close'].values[-1])
    if not (ma5 > ma10 > ma20 and price > ma20): continue
    if ind.get('today_ret',0) < -0.095: continue
    trending.append({'ticker': t, 'indicators': ind, 'ret_5d': ind.get('pre_5d_return',0)})

trending.sort(key=lambda x: -x['ret_5d'])
top300 = trending[:300]
print(f"  趋势筛选: {len(trending)}/{len(all_tickers)} → Top300")

# Score top candidates
scorer = TristScorer(market_context=ctx)
top_results = []
for i, s in enumerate(top300[:100]):  # score top 100
    t = s['ticker']
    try:
        rt = _get_tencent_quote(t)
        time.sleep(0.06)
        ind = s['indicators'].copy()
        price = rt.get('price', float(_load_cache(t)['close'].values[-1]))
        ind['ticker'] = t; ind['name'] = rt.get('name',''); ind['price'] = price
        ind['is_realtime'] = True
        if rt.get('change_pct',0) != 0: ind['today_ret'] = rt['change_pct']/100
        r = scorer.score(ind, {})
        r.rt_price = price; r.rt_change = rt.get('change_pct',0); r.rt_name = rt.get('name','')
        top_results.append(r)
    except: pass
    if (i+1) % 30 == 0: print(f"  评分: {i+1}/100")

passed = [r for r in top_results if not r.vetoed and r.total_score >= 40]
passed.sort(key=lambda x: -x.total_score)

print(f"\n  Top 5:")
for i, r in enumerate(passed[:5]):
    name = getattr(r, 'rt_name', '') or r.name
    rtp = getattr(r, 'rt_change', 0)
    if r.total_score >= 80: tag = "[满仓]"
    elif r.total_score >= 60: tag = "[半仓]"
    elif r.total_score >= 40: tag = "[观察]"
    else: tag = "[弱]"
    print(f"  #{i+1} {tag} {name}({r.ticker}) {r.total_score}分 @{r.rt_price:.2f} {rtp:+.1f}%")
    if r.pa_details:
        pas = [f"{k}:{v:+d}" for k,v in sorted(r.pa_details.items()) if v!=0]
        print(f"    PA: {' | '.join(pas[:6])}")
    print(f"    市场:{r.market_state} K线:{r.signal_bar_quality}({r.signal_bar_type}) H{r.h_count}/L{r.l_count} 楔形:{r.wedge_type or '-'} SR:{r.sr_confluence}")
    real_v = [h for h in (r.forbidden_hits if hasattr(r,'forbidden_hits') else [])]
    if real_v: print(f"    禁区: {real_v}")

# ══════════════════════════════════════════════════════
# Part 2: 深度分析 — 京北方 + 中远海特
# ══════════════════════════════════════════════════════
for code, name in [('002987','京北方'), ('600428','中远海特')]:
    print(f"\n{'='*60}")
    print(f"  Part 2: {code} {name}")
    print(f"{'='*60}")

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

    c = kline['close'].values; h = kline['high'].values
    l_p = kline['low'].values; o_vals = kline['open'].values; v = kline['volume'].values
    ma5 = pd.Series(c).rolling(5).mean().values[-1]
    ma10 = pd.Series(c).rolling(10).mean().values[-1]
    ma20 = pd.Series(c).rolling(20).mean().values[-1]
    ma60 = pd.Series(c).rolling(60).mean().values[-1] if len(c)>=60 else 0
    trs = [max(h[j]-l_p[j], abs(h[j]-c[j-1]), abs(l_p[j]-c[j-1])) for j in range(1,len(c))]
    atr5 = np.mean(trs[-5:]); atr14 = np.mean(trs[-14:])
    h20 = max(h[-20:]); l20 = min(l_p[-20:])
    pos20 = (price-l20)/(h20-l20)*100 if h20>l20 else 50
    ret5 = (c[-1]/c[-6]-1)*100 if len(c)>5 else 0
    ret20 = (c[-1]/c[-21]-1)*100 if len(c)>20 else 0

    if ma5 > ma10 > ma20: align = 'MA多头'
    elif price > ma20: align = '站上MA20'
    else: align = 'MA空头'

    # GAP check
    gap = ind.get('open_gap_pct', 0)

    print(f'\n  [实时] {price:.2f} ({change:+.2f}%)')
    print(f'\n  [评分] 总分: {r.total_score} (PA{r.pa_score}+强化{r.bonus_score}+外围{r.external_score})')
    if r.total_score >= 80: pos = '★满仓'
    elif r.total_score >= 60: pos = '●半仓'
    else: pos = '○观察'
    print(f'  仓位判定: {pos} ({r.total_score}/100, 线=60/80)')

    print(f'\n  [均线] {align}')
    print(f'  MA5={ma5:.2f} MA10={ma10:.2f} MA20={ma20:.2f} MA60={ma60:.2f}')
    print(f'  vs MA5: {(price/ma5-1)*100:+.1f}% | vs MA20: {(price/ma20-1)*100:+.1f}%')

    print(f'\n  [波动] ATR5={atr5:.2f}({atr5/price*100:.1f}%) ATR14={atr14:.2f}')
    print(f'  20日: H{h20:.2f}/L{l20:.2f} | 位置{pos20:.0f}%')
    print(f'  5日:{ret5:+.1f}% | 20日:{ret20:+.1f}%')

    print(f'\n  [近8日K线]')
    for _, row in kline.tail(8).iterrows():
        chg = (row['close']/row['open']-1)*100
        amp = (row['high']-row['low'])/row['open']*100
        vol_r = row['volume']/np.mean(v[-20:]) if len(v)>=20 else 1
        tags = []
        if chg > 9.5: tags.append('涨停')
        if abs(chg)<2 and vol_r<0.7: tags.append('缩量')
        tag_str = ','.join(tags)
        tag = f' [{tag_str}]' if tags else ''
        _ro = row['open']; _rh = row['high']; _rl = row['low']; _rc = row['close']
        print(f'    {row.name} O:{_ro:.2f} H:{_rh:.2f} L:{_rl:.2f} C:{_rc:.2f} ({chg:+.1f}% 量{vol_r:.1f}){tag}')

    print(f'\n  [PA明细]')
    if r.pa_details:
        for k, v in sorted(r.pa_details.items()):
            if v != 0: print(f'    {k}: {v:+d}')
    ms = r.market_state or '?'
    sq = r.signal_bar_quality or '?'
    st = r.signal_bar_type or '-'
    wt = r.wedge_type or '无'
    print(f'  市场: {ms} | K线: {sq}({st})')
    print(f'  H{r.h_count}/L{r.l_count} | 楔形:{wt} | SR:{r.sr_confluence}重')
    if r.bonus_details:
        bh = [k for k,v in r.bonus_details.items() if v and v is not False]
        if bh: print(f'  强化: {bh}')
    if r.entry_signals:
        es = ', '.join(r.entry_signals[:5])
        print(f'  信号: {es}')

    # X17 check
    print(f'\n  [X17跳空检查] gap={gap*100:.1f}%', end='')
    if abs(gap) > 0.05:
        print(f' → 🚫 触发! 跳空>{5}%, 当日禁入')
    else:
        print(f' → ✅ 放行')

    # Trading recommendation
    print(f'\n  [交易建议]')
    if r.vetoed:
        print(f'  ⛔ 禁区否决: {r.forbidden_hits}')
    elif r.total_score >= 80:
        print(f'  ✅ 满仓级别 — 可入场(确认X17放行)')
        print(f'  止损: {price - 1.5*atr5:.2f} (-{1.5*atr5/price*100:.1f}%)')
    elif r.total_score >= 60:
        print(f'  ⚡ 半仓级别 — 可半仓入场(确认X17放行)')
        print(f'  止损: {price - 1.5*atr5:.2f} (-{1.5*atr5/price*100:.1f}%)')
    else:
        missing = 60 - r.total_score
        print(f'  ⚠️ 差{missing}分到半仓线 — 等待更好入场点')
        print(f'  理想入场: 回踩MA10({ma10:.2f})附近')

print(f"\n{'='*60}")
print(f"  交易计划总结")
print(f"{'='*60}")
print(f"""
  [今日状态]
  X12: {'涨停'+str(lu)+'>80 高潮期谨慎' if x12_warn else '正常'}
  X17: 跳空检查每只独立判断
  冷却期: 已过期(8/3解禁)

  [操作指南]
  1. 看Top5中是否有60+分的半仓/满仓标的
  2. 优先半仓以上 + X17放行的标的
  3. 不符合条件的 → 加入观察列表，等回踩
  4. 单票 ≤ 总资金25%
""")
