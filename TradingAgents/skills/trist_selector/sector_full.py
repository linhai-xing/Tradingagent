"""
Full CPO + Semiconductor sector screen — fetches ALL constituents from eastmoney.
"""
import sys, os, time, json, numpy as np, pandas as pd
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
from direct_api import get_realtime_quote
from data_cache import update_batch
from entry_signals import detect_entry_signals
import requests

OUT_DIR = os.path.join(os.path.dirname(__file__), 'output')
os.makedirs(OUT_DIR, exist_ok=True)

# Sector codes on eastmoney
SECTORS = {
    '半导体': 'BK1036',
    'CPO概念': 'BK1150',
    '光通信模块': 'BK1136',
    'PCB': 'BK0429',
    '电子元件': 'BK0448',
    'AI芯片': 'BK1098',
    '先进封装': 'BK1163',
    '汽车芯片': 'BK1101',
    '第三代半导体': 'BK1028',
    '存储芯片': 'BK1113',
    'Chiplet': 'BK1189',
    '碳化硅': 'BK1080',
}

def get_sector_stocks(sector_code):
    """Get all constituent stocks for a sector."""
    s = requests.Session(); s.trust_env = False
    params = {
        'pn': 1, 'pz': 500, 'po': 1, 'np': 1, 'fltt': 2, 'invt': 2,
        'fid': 'f3', 'fs': f'b:{sector_code}+f:!50',
        'fields': 'f2,f3,f12,f14'
    }
    try:
        r = s.get('https://push2.eastmoney.com/api/qt/clist/get', params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if 'data' in data and data['data']:
                return [item['f12'] for item in data['data'].get('diff', [])]
    except Exception as e:
        print(f'    Error: {e}')
    return []

print(f'CPO + Semiconductor FULL Sector Screen')
print(f'=' * 65)
print(f'Time: {datetime.now():%Y-%m-%d %H:%M}')
print()

# Step 1: Get ALL constituents from every sector
all_tickers = set()
sector_map = {}

for name, code in SECTORS.items():
    print(f'  Fetching {name} ({code})...')
    tickers = get_sector_stocks(code)
    if tickers:
        all_tickers.update(tickers)
        for t in tickers:
            if t not in sector_map: sector_map[t] = []
            sector_map[t].append(name)
        print(f'    Got {len(tickers)} stocks')
    else:
        print(f'    Failed')
    time.sleep(2.0)  # generous spacing to avoid rate limit

# Remove STAR board for safety, mark them
all_list = list(all_tickers)
star_stocks = [t for t in all_list if t.startswith('688')]
main_stocks = [t for t in all_list if not t.startswith('688')]

print(f'\n  Total unique: {len(all_list)} stocks')
print(f'  Main board: {len(main_stocks)} | STAR board: {len(star_stocks)}')
print(f'  Sectors covered: {len([n for n,c in SECTORS.items() if any(t in all_tickers for t in [])])}')

# If sector API failed entirely, fallback to hardcoded comprehensive pool
if len(all_list) < 50:
    print(f'\n  Sector API returned too few. Using fallback pool (140+ stocks).')
    fallback = {
        '300308','300502','300394','002281','000988','300570','300620','300548',
        '688048','688498','688608','688595','688313','300757','603083',
        '002371','688012','688082','688120','688072','688037','688200','688596',
        '300604','300666','603690','688559','688138','300456',
        '603501','603986','002049','300782','300661','688256','688521','688536',
        '688099','688110','688766','300458','300672','688018','688019',
        '002079','300223','603160','688368','300327','603893',
        '600584','002156','002185','688981','600703','600460','603005',
        '688396','605358','603290','688187','300623','605111',
        '002916','002463','002938','002436','603228','300476','002384',
        '603920','002579','300657','300735','603186','688183','300852',
        '600601','002134','300739','603989','300632','600522',
        '002409','300236','300346','300102','300708','002129',
        '600171','300576','688300','300684','603650',
        '688041','300474','603019','600667','300212',
        '000725','002456','300433',
        '300373','300613','002916','300476','603228','603386','002579','300739',
        '002134','603920','603989','300852','002552','300686','688020','688981',
    }
    all_list = list(fallback)
    for t in all_list:
        if t not in sector_map: sector_map[t] = ['CPO/半导体/PCB']
    main_stocks = [t for t in all_list if not t.startswith('688')]
    star_stocks = [t for t in all_list if t.startswith('688')]
    print(f'  Fallback pool: {len(all_list)} stocks')

# Step 2: Use K-line close prices (real-time API is down after hours)
print(f'\n[Step 2] K-lines for {len(all_list)} stocks...')
klines = update_batch(all_list, start_date='2026-03-01')
print(f'  Got {len(klines)} K-lines')

# Step 3: Score
print(f'\n[Step 3] Scoring...')
results = []

for ticker, kdf in klines.items():
    if len(kdf) < 20: continue
    c = kdf['close'].values; v = kdf['volume'].values
    h = kdf['high'].values; l = kdf['low'].values; o = kdf['open'].values

    price = float(c[-1])
    chg = float(c[-1]/c[-2]-1)*100 if len(c)>=2 else 0
    vol_r = float(v[-1]/np.mean(v[-5:])) if np.mean(v[-5:])>0 else 1
    amp = float((h[-1]-l[-1])/o[-1]*100) if o[-1]>0 else 0
    today_low = float(l[-1]); today_open = float(o[-1])

    c_live = np.append(c, price)
    ma5 = float(np.mean(c_live[-5:])); ma10 = float(np.mean(c_live[-10:]))
    ma20 = float(np.mean(c_live[-20:])); ma60 = float(np.mean(c_live[-min(60,len(c_live)):]))

    ret5d = float(price/c[-min(5,len(c))]-1) if len(c)>=5 else 0
    high20 = float(max(np.max(h[-20:]), price))
    pullback = (high20-price)/high20 if high20>0 else 0
    is_star = ticker.startswith('688')
    sectors = sector_map.get(ticker, [])

    # Veto
    vetoes = []
    if ret5d > 0.20: vetoes.append('X1追高')
    if ma5 < ma10: vetoes.append('X9死叉')
    if chg < -9.5: vetoes.append('跌停')
    if vetoes: continue

    # Core score
    score = 0; core = {}
    c1 = ma5 > ma20 > ma60 and price > ma5
    if c1: score += 25; core['C1趋势']=True
    else: core['C1趋势']=False

    c2 = ret5d < 0.15
    if c2: score += 25; core['C2非追高']=True
    else: core['C2非追高']=False

    c3 = 0.5 < vol_r < 3.0
    if c3: score += 25; core['C3量能']=True
    else: core['C3量能']=False

    c4 = 0.02 < pullback < 0.20
    if c4: score += 25; core['C4回调']=True
    else: core['C4回调']=False

    # Bonus
    bonus = 0
    leaders = {'300308','300502','300394','002371','603501','002049','688256','002916','603986','688981'}
    if ticker in leaders: bonus += 10
    if len(sectors) >= 3: bonus += 10  # multi-sector coverage = hot money magnet

    dist_ma10 = abs(price/ma10-1) if ma10>0 else 0
    near_ma10 = 0 < dist_ma10 < 0.04 and price > ma10
    if near_ma10: bonus += 10

    s10 = today_low > 0 and today_low < ma10 and price > ma10 and amp > 3
    if s10: bonus += 10

    ret3d = float(price/c[-min(3,len(c))]-1) if len(c)>=3 else 0
    b6 = ret3d < 0.03 and chg > 2 and vol_r > 1.3
    if b6: bonus += 10

    score += bonus

    # Entry signals
    sig_dict = {'closes':list(c),'opens':list(o),'highs':list(h),'lows':list(l),'volumes':list(v)}
    sigs = detect_entry_signals(sig_dict, ticker)
    sig_names = [s.name for s in sigs]
    if s10 and '机构洗盘V转' not in sig_names: sig_names.append('机构洗盘V转')

    if score >= 60:
        results.append({
            'ticker':ticker,'price':price,'score':score,'chg':round(chg,1),
            'ma5':round(ma5,2),'ma10':round(ma10,2),'ma20':round(ma20,2),
            'ret5d':round(ret5d,3),'pullback':round(pullback,2),
            'vol_r':round(vol_r,2),'amp':round(amp,2),
            'core':core,'bonus':bonus,'is_leader':ticker in leaders,
            'is_star':is_star,'near_ma10':near_ma10,'s10':s10,'b6':b6,
            'sectors':sectors[:3],'signals':sig_names,
            'position':'full' if score>=80 else 'half',
        })

results.sort(key=lambda r: r['score'], reverse=True)
top = results[:15]

print(f'\nScored: {len(klines)} | Passed: {len(results)} ({len(results)/max(len(klines),1)*100:.0f}%)')
print(f'\n{"="*70}')
print(f'  TOP 15 | CPO + Semiconductor + PCB (FULL SCREEN)')
print(f'  {datetime.now():%Y-%m-%d %H:%M} | Observed: {len(all_list)} stocks')
print(f'{"="*70}')

for i, r in enumerate(top):
    pos = 'FULL' if r['position']=='full' else 'HALF'
    core_s = ''.join(['+' if v else '-' for v in r['core'].values()])
    sigs = ','.join(r['signals'][:3])
    leader_m = ' [龙头]' if r['is_leader'] else ''
    star_m = ' [STAR]' if r['is_star'] else ''
    ma10_m = ' [MA10]' if r['near_ma10'] else ''
    s10_m = ' [V转]' if r['s10'] else ''
    b6_m = ' [弱转强]' if r['b6'] else ''
    sectors_s = '/'.join(r['sectors'][:2])

    print(f"\n#{i+1} [{pos}]{leader_m}{star_m} {r['ticker']} @{r['price']:.2f} - {r['score']}pts{ma10_m}{s10_m}{b6_m}")
    print(f"  {r['chg']:+.1f}% | 5d:{r['ret5d']:+.1%} | 量比:{r['vol_r']:.2f} | 回调:{r['pullback']:.0%} | {sectors_s}")
    print(f"  MA5:{r['ma5']:.2f} MA10:{r['ma10']:.2f} MA20:{r['ma20']:.2f} | Core:{core_s} | {sigs}")

full_n = sum(1 for r in results if r['position']=='full')
half_n = sum(1 for r in results if r['position']=='half')
leader_n = sum(1 for r in results if r['is_leader'])
print(f'\n{"="*70}')
print(f'Summary: {len(results)} passed | {full_n} FULL | {half_n} HALF | {leader_n} leaders')
print(f'Observed: {len(all_list)} stocks | Sector API: {len([n for n in SECTORS if any(t in all_tickers for t in [])])} sectors queried')
