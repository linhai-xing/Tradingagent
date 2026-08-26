"""Pharma first-board scanner for Turtle-Rabbit strategy"""
import noproxy
import sys, os, json, time
sys.stdout.reconfigure(encoding='utf-8')
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ── Pharma tickers from baostock C27医药制造业 ──
PHARMA_TICKERS = [
    '600062','600079','600080','600085','600129','600161','600195','600196','600201',
    '600211','600216','600222','600252','600267','600276','600285','600329','600332',
    '600351','600380','600420','600422','600436','600479','600488','600513','600518',
    '600521','600535','600557','600566','600572','600594','600613','600624','600645',
    '600664','600671','600682','600750','600771','600774','600789','600807','600812',
    '600851','600867','600993','601089','601515','603079','603087','603139','603168',
    '603222','603229','603259','603351','603367','603387','603392','603439','603456',
    '603520','603538','603567','603590','603658','603669','603676','603707','603811',
    '603858','603880','603896','603963','603976','603998','605116','605177','605199',
    '605266','605369','605507','688016','688029','688046','688050','688062','688067',
    '688068','688073','688075','688076','688085','688091','688092','688098','688105',
    '688106','688108','688114','688117','688131','688136','688137','688139','688151',
    '688152','688153','688156','688157','688161','688163','688166','688168','688173',
    '688176','688177','688180','688185','688189','688192','688193','688197','688198',
    '688202','688207','688212','688217','688221','688231','688235','688236','688238',
    '688246','688247','688253','688265','688266','688269','688271','688273','688276',
    '688277','688278','688282','688289','688293','688298','688301','688302','688314',
    '688315','688317','688319','688321','688331','688336','688338','688351','688356',
    '688358','688366','688373','688382','688389','688393','688399','688410','688426',
    '688428','688443','688466','688468','688488','688505','688506','688513','688520',
    '688526','688553','688566','688578','688580','688581','688606','688607','688613',
    '688621','688625','688626','688639','688656','688658','688670','688687','688690',
    '688710','688739','688767','688799','689009',
    '000004','000153','000403','000423','000504','000513','000518','000534','000538',
    '000566','000590','000597','000623','000650','000661','000705','000710','000739',
    '000756','000766','000788','000790','000813','000908','000919','000931','000950',
    '000952','000953','000963','000989','000999','001215','001231','001259','001308',
    '001313','001360','001367','002001','002007','002019','002020','002022','002030',
    '002038','002082','002099','002102','002107','002118','002166','002173','002198',
    '002262','002275','002287','002294','002317','002332','002349','002365','002370',
    '002390','002393','002399','002411','002412','002422','002424','002432','002433',
    '002435','002437','002550','002566','002581','002603','002644','002653','002675',
    '002688','002693','002728','002737','002742','002750','002755','002773','002793',
    '002817','002821','002826','002864','002868','002873','002880','002898','002900',
    '002907','002923','002932','002940','003016','003020','300003','300006','300009',
    '300016','300019','300026','300039','300049','300086','300108','300110','300111',
    '300119','300138','300142','300147','300149','300158','300171','300181','300194',
    '300199','300204','300233','300239','300254','300255','300267','300289','300294',
    '300347','300357','300363','300381','300401','300404','300406','300434','300436',
    '300439','300452','300453','300463','300485','300497','300519','300529','300534',
    '300558','300573','300583','300584','300595','300601','300630','300633','300636',
    '300639','300642','300653','300676','300683','300685','300702','300705','300723',
    '300725','300765','300832','300841','300869','300878','300937','300942','300981',
    '301000','301003','301015','301017','301033','301047','301065','301075','301080',
    '301089','301090','301093','301096','301097','301103','301110','301111','301126',
    '301130','301166','301186','301201','301207','301211','301230','301234','301235',
    '301246','301257','301258','301263','301267','301273','301277','301281','301285',
    '301290','301293','301301','301313','301318','301331','301333','301339','301345',
    '301356','301363','301367','301370','301386','301393','301397','301399','301408',
    '301429','301439','301456','301498','301507','301509','301515','301520','301529',
    '301533','301550','301555','301559','301568','301575','301585','301586','301587',
    '301611','301617','301633',
]

print(f"医药板块扫描: {len(PHARMA_TICKERS)} stocks")
print(f"Time: {datetime.now():%Y-%m-%d %H:%M}")
print("=" * 70)

# ── Batch query Tencent API ──
def get_tencent_batch(tickers_batch):
    s = requests.Session()
    s.trust_env = False
    codes = []
    for t in tickers_batch:
        prefix = 'sh' if t.startswith(('6','9')) else 'sz'
        codes.append(f'{prefix}{t}')
    url = f'http://qt.gtimg.cn/q={",".join(codes)}'
    try:
        r = s.get(url, timeout=10)
        r.encoding = 'gbk'
        return r.text
    except Exception as e:
        return ''

def parse_tencent_response(text):
    results = []
    lines = text.strip().split('\n')
    for line in lines:
        if '~' not in line:
            continue
        try:
            parts = line.split('~')
            if len(parts) < 50:
                continue
            # Extract ticker
            var_name = line.split('=')[0] if '=' in line else ''
            if 'sh' in var_name:
                ticker = var_name.split('sh')[1][:6]
            elif 'sz' in var_name:
                ticker = var_name.split('sz')[1][:6]
            else:
                continue
            name = parts[1]
            price = float(parts[3]) if parts[3] else 0
            prev_close = float(parts[4]) if parts[4] else 0
            pct = float(parts[32]) if parts[32] else 0
            turnover = float(parts[38]) if parts[38] else 0
            amount = float(parts[37]) if parts[37] else 0
            vol_ratio = float(parts[49]) if len(parts) > 49 and parts[49] else 1
            high = float(parts[33]) if parts[33] else 0
            low = float(parts[34]) if parts[34] else 0
            open_p = float(parts[5]) if parts[5] else 0
            results.append({
                'ticker': ticker, 'name': name, 'price': price,
                'prev_close': prev_close, 'open': open_p,
                'high': high, 'low': low, 'pct': pct,
                'turnover': turnover, 'amount': amount,
                'vol_ratio': vol_ratio
            })
        except Exception:
            pass
    return results

print("\n[1] Fetching real-time quotes from Tencent...")
all_results = []
batch_size = 60
for i in range(0, len(PHARMA_TICKERS), batch_size):
    batch = PHARMA_TICKERS[i:i+batch_size]
    text = get_tencent_batch(batch)
    results = parse_tencent_response(text)
    all_results.extend(results)
    if (i//batch_size + 1) % 2 == 0:
        print(f"  Progress: {i+len(batch)}/{len(PHARMA_TICKERS)}")
    time.sleep(0.3)

print(f"  Got {len(all_results)} quotes")

# ── Filter for limit-up ──
limit_up = [r for r in all_results if r['pct'] >= 9.5]
limit_up.sort(key=lambda x: x['pct'], reverse=True)

print(f"\n[2] Today's limit-up in pharma: {len(limit_up)} stocks")
print(f"{'Code':<8} {'Name':<10} {'Price':<8} {'Pct%':<8} {'Turnover%':<10} {'VolRatio':<8} {'Amount(亿)':<12}")
print("-" * 70)
for s in limit_up:
    amt_yi = s['amount'] / 100000000 if s['amount'] > 0 else 0
    print(f"{s['ticker']:<8} {s['name']:<10} {s['price']:<8.2f} {s['pct']:<8.2f} {s['turnover']:<10.2f} {s['vol_ratio']:<8.2f} {amt_yi:<12.2f}")

# ── Check if these are first-boards (首板) ──
print(f"\n[3] Checking board history (first-board detection)...")
from data_cache import _load_cache

for s in limit_up:
    ticker = s['ticker']
    try:
        df = _load_cache(ticker)
        if len(df) < 5:
            s['board_history'] = 'unknown'
            continue
        # Check last 5 days for consecutive limit-ups
        recent = df.tail(10)
        closes = recent['close'].values
        prev_closes = np.roll(closes, 1)
        prev_closes[0] = closes[0]
        pct_changes = (closes - prev_closes) / prev_closes * 100

        # Count consecutive limit-up days (>=9.5%)
        board_days = []
        for i in range(len(pct_changes)-1, max(len(pct_changes)-6, -1), -1):
            if pct_changes[i] >= 9.5:
                board_days.append(str(recent.iloc[i]['date'])[:10])
            else:
                break

        s['board_days'] = board_days
        s['is_first_board'] = len(board_days) <= 1
        s['board_count'] = len(board_days)
    except Exception as e:
        s['board_history'] = f'error: {e}'
        s['is_first_board'] = False
        s['board_count'] = 0

print(f"\n{'Code':<8} {'Name':<10} {'Pct%':<8} {'BoardCount':<10} {'FirstBoard':<10} {'History':<30}")
print("-" * 70)
for s in limit_up:
    fb = "YES" if s.get('is_first_board', False) else "NO"
    bd = s.get('board_days', [])
    print(f"{s['ticker']:<8} {s['name']:<10} {s['pct']:<8.2f} {s.get('board_count',0):<10} {fb:<10} {str(bd)[:30]:<30}")

# ── Near limit-up (7-9.5%) ──
near_limit = [r for r in all_results if 7 <= r['pct'] < 9.5]
near_limit.sort(key=lambda x: x['pct'], reverse=True)
if near_limit:
    print(f"\n[4] Pharma stocks near limit-up (7-9.5%): {len(near_limit)}")
    for s in near_limit:
        print(f"  {s['ticker']} {s['name']} price={s['price']:.2f} pct={s['pct']:.2f}% turnover={s['turnover']:.2f}%")

# ── Save ──
out_dir = 'output'
os.makedirs(out_dir, exist_ok=True)
out_file = os.path.join(out_dir, f'pharma_limit_up_{datetime.now():%Y%m%d_%H%M}.json')
with open(out_file, 'w', encoding='utf-8') as f:
    json.dump({'limit_up': limit_up, 'near_limit': near_limit}, f, ensure_ascii=False, indent=2)
print(f"\nSaved to {out_file}")