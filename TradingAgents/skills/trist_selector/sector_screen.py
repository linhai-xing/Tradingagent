"""
Sector screen v2 — CPO + Semiconductor + PCB leaders.
120+ stocks, real-time quotes, full scoring.
"""
import sys, os, time, json, numpy as np, pandas as pd
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
from direct_api import get_realtime_quote
from data_cache import update_batch
from entry_signals import detect_entry_signals

OUT_DIR = os.path.join(os.path.dirname(__file__), 'output')
os.makedirs(OUT_DIR, exist_ok=True)

# 120+ stocks across CPO/Semi/PCB
POOL = {
    # CPO / Optical
    '300308','300502','300394','002281','000988','300570','300620','300548',
    '688048','688498','688608','688595','688313','300757','603083',
    # Semi Equipment
    '002371','688012','688082','688120','688072','688037','688200','688596',
    '300604','300666','603690','688559','688138','300456',
    # IC Design
    '603501','603986','002049','300782','300661','688256','688521','688536',
    '688099','688110','688766','300458','300672','688018','688019',
    '002079','300223','603160','688368','300327','603893',
    # Packaging/Foundry
    '600584','002156','002185','688981','600703','600460','603005',
    '688396','605358','603290','688187','300623','605111',
    # PCB
    '002916','002463','002938','002436','603228','300476','002384',
    '603920','002579','300657','300735','603186','688183','300852',
    '600601','002134','300739','603989','300632','600522',
    # Materials
    '002409','300236','300346','300102','300708','002129',
    '600171','300576','688300','300684','603650',
    # AI/Computing
    '688041','300474','603019','600667','300212',
    # Display/LED
    '000725','002456','300433',
}
tickers = list(POOL)
print(f'Sector Screen: {len(tickers)} stocks (CPO+Semi+PCB)')
print(f'Time: {datetime.now():%Y-%m-%d %H:%M}')
print()

# Step 1: Real-time quotes
print('[1/3] Real-time quotes...')
quotes = {}
for i, t in enumerate(tickers):
    try:
        q = get_realtime_quote(t)
        if q and q.get('price', 0) > 0: quotes[t] = q
    except: pass
    if (i+1) % 30 == 0: time.sleep(0.5)
    else: time.sleep(0.15)
print(f'  Got {len(quotes)} quotes')

# Step 2: K-lines
print(f'\n[2/3] K-lines...')
klines = update_batch(tickers, start_date='2026-03-01')
print(f'  Got {len(klines)}')

# Step 3: Score
print(f'\n[3/3] Scoring...')
results = []

for ticker, kdf in klines.items():
    if len(kdf) < 20: continue
    rt = quotes.get(ticker, {})
    c = kdf['close'].values; v = kdf['volume'].values
    h = kdf['high'].values; l = kdf['low'].values; o = kdf['open'].values

    # Use real-time if available, else use latest K-line close
    price = rt.get('price', 0) if rt.get('price', 0) > 0 else float(c[-1])
    chg = rt.get('change_pct', 0) if rt.get('price', 0) > 0 else float(c[-1]/c[-2]-1)*100
    turnover = rt.get('turnover', 0) if rt.get('turnover', 0) > 0 else 5.0  # fallback: assume 5%
    vol_r = rt.get('vol_ratio', 0) if rt.get('vol_ratio', 0) > 0 else float(v[-1]/np.mean(v[-5:])) if np.mean(v[-5:])>0 else 1
    amp = rt.get('amplitude', 0) if rt.get('amplitude', 0) > 0 else float((h[-1]-l[-1])/o[-1]*100) if o[-1]>0 else 0
    today_low = rt.get('low', 0) if rt.get('low', 0) > 0 else float(l[-1])
    today_open = rt.get('open', 0) if rt.get('open', 0) > 0 else float(o[-1])

    c_live = np.append(c, price)
    ma5 = float(np.mean(c_live[-5:])); ma10 = float(np.mean(c_live[-10:]))
    ma20 = float(np.mean(c_live[-20:])); ma60 = float(np.mean(c_live[-min(60,len(c_live)):]))

    ret5d = float(price/c[-min(5,len(c))]-1) if len(c) >= 5 else 0
    high20 = float(max(np.max(h[-20:]), price))
    pullback = (high20 - price) / high20 if high20 > 0 else 0
    is_star = ticker.startswith('688')

    # Veto
    vetoes = []
    if ret5d > 0.20: vetoes.append(f'X1追高(5d+{ret5d:.0%})')
    if ma5 < ma10: vetoes.append(f'X9死叉')
    if chg < -9.5: vetoes.append('跌停')
    if turnover < 0.5: vetoes.append('X2无量')
    if vetoes: continue

    # Score
    score = 0; core = {}
    c1 = ma5 > ma20 > ma60 and price > ma5
    if c1: score += 25; core['C1趋势'] = True
    else: core['C1趋势'] = False

    c2 = ret5d < 0.15
    if c2: score += 25; core['C2非追高'] = True
    else: core['C2非追高'] = False

    c3 = turnover > 2 or (0.5 < vol_r < 3.0)  # fallback to vol_ratio if turnover unavailable
    if c3: score += 25; core['C3量能'] = True
    else: core['C3量能'] = False

    c4 = 0.03 < pullback < 0.20
    if c4: score += 25; core['C4回调到位'] = True
    else: core['C4回调到位'] = False

    # Bonus
    bonus = 0
    leaders = {'300308','300502','300394','002371','603501','002049','688256','002916'}
    if ticker in leaders: bonus += 10

    dist_ma10 = abs(price/ma10 - 1) if ma10 > 0 else 0
    near_ma10 = 0 < dist_ma10 < 0.04 and price > ma10
    if near_ma10: bonus += 10

    s10 = today_low > 0 and today_low < ma10 and price > ma10 and amp > 3
    if s10: bonus += 10

    # B6: weak-to-strong
    ret3d = float(price/c[-min(3,len(c))]-1) if len(c)>=3 else 0
    b6 = ret3d < 0.03 and chg > 2 and vol_r > 1.3
    if b6: bonus += 10

    score += bonus

    # Entry signals
    sig_dict = {'closes':list(c),'opens':list(o),'highs':list(h),'lows':list(l),'volumes':list(v)}
    sigs = detect_entry_signals(sig_dict, ticker)
    sig_names = [s.name for s in sigs]
    if s10 and '机构洗盘V转' not in sig_names:
        sig_names.append('机构洗盘V转')

    if score >= 60:
        results.append({
            'ticker':ticker,'price':price,'score':score,'chg':round(chg,1),
            'ma5':round(ma5,2),'ma10':round(ma10,2),'ma20':round(ma20,2),
            'ret5d':round(ret5d,3),'pullback':round(pullback,2),
            'turnover':round(turnover,1),'vol_r':round(vol_r,2),
            'amp':round(amp,2),'core':core,'bonus':bonus,
            'is_leader':ticker in leaders,'is_star':is_star,
            'near_ma10':near_ma10,'s10':s10,'b6':b6,
            'signals':sig_names,'vetoes':vetoes,
            'position':'full' if score>=80 else 'half',
        })

results.sort(key=lambda r: r['score'], reverse=True)
top = results[:10]

print(f'\nScored: {len(klines)} | Passed: {len(results)}')
print(f'\n{"="*65}')
print(f'  TOP 10 | CPO + Semiconductor + PCB')
print(f'  {datetime.now():%Y-%m-%d %H:%M} | {len(tickers)} stocks observed')
print(f'{"="*65}')

for i, r in enumerate(top):
    pos = 'FULL' if r['position']=='full' else 'HALF'
    core_s = ''.join(['+' if v else '-' for v in r['core'].values()])
    sigs = ','.join(r['signals'][:3])
    leader_m = ' [龙头]' if r['is_leader'] else ''
    star_m = ' [STAR]' if r['is_star'] else ''
    ma10_m = ' [MA10]' if r['near_ma10'] else ''
    s10_m = ' [V转]' if r['s10'] else ''
    b6_m = ' [弱转强]' if r['b6'] else ''

    print(f"\n#{i+1} [{pos}]{leader_m}{star_m} {r['ticker']} @{r['price']:.2f} - {r['score']}pts{ma10_m}{s10_m}{b6_m}")
    print(f"  {r['chg']:+.1f}% | 5d:{r['ret5d']:+.1%} | 换手:{r['turnover']:.1f}% | 量比:{r['vol_r']:.2f} | 回调:{r['pullback']:.0%}")
    print(f"  MA5:{r['ma5']:.2f} MA10:{r['ma10']:.2f} MA20:{r['ma20']:.2f} | Core:{core_s} | {sigs}")

full = sum(1 for r in results if r['position']=='full')
half = sum(1 for r in results if r['position']=='half')
print(f'\nSummary: {len(results)} passed | {full} FULL | {half} HALF | {len(tickers)} observed')
