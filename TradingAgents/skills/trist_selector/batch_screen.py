"""
Batch full-market screener — 200 stocks at a time.
Usage: python batch_screen.py
"""
import sys, os, json, time
from datetime import datetime
import pandas as pd, numpy as np

sys.path.insert(0, os.path.dirname(__file__))

from data_cache import update_batch as cache_batch
from scoring import TristScorer, build_market_context
from entry_signals import detect_entry_signals, get_entry_recommendation

OUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUT_DIR, exist_ok=True)
BATCH_SIZE = 200

# ── Step 1: Load stock list via baostock (reliable, no rate limit) ──
print(f"[{datetime.now():%H:%M}] Step 1: Loading stock list via baostock...")
import baostock as bs; bs.login()
rs = bs.query_stock_basic(); rows = []
while (rs.error_code == '0') and rs.next(): rows.append(rs.get_row_data())
bs.logout()

ncols = len(rows[0]) if rows else 0
cols = ['code','code_name','ipo_date','col4','status','col6'][:ncols]
df = pd.DataFrame(rows, columns=cols)
df['ticker'] = df['code'].str.split('.').str[-1]
df['name'] = df['code_name'] if 'code_name' in df.columns else ''

# Filter: only real stocks (6 digits after dot), exclude indices/sectors
# sh.000xxx = indices, sz.399xxx = indices, 8xxxxx = BSE
df = df[df['code'].str.match(r'^[a-z]{2}\.\d{6}$')]  # format sh.xxxxxx or sz.xxxxxx
df = df[~df['code'].str.match(r'^sh\.000')]           # Shanghai indices
df = df[~df['code'].str.match(r'^sz\.399')]           # Shenzhen indices
df = df[~df['code'].str.match(r'^[a-z]{2}\.8')]      # BSE
df = df[~df['code'].str.match(r'^sh\.688')]           # STAR board
df = df[~df['name'].str.contains('ST|退', na=False)]  # ST stocks
# Exclude ETFs/LOFs (51xxxx, 56xxxx, 58xxxx, 159xxx)
df = df[~df['code'].str.match(r'^(sh\.5[168]|sz\.159)')]

print(f"  Total A-shares (excl STAR): {len(df)}")

# Coarse filter: only name-based (ST exclusion)
df = df[~df['name'].str.contains('ST|退', na=False)]
# Stratified sample: ~50 from each main board for diversity
np.random.seed(42)
sh60 = df[df['code'].str.startswith('sh.60')]
sz00 = df[df['code'].str.startswith('sz.00')]
sz30 = df[df['code'].str.startswith('sz.30')]
sz002 = df[df['code'].str.startswith('sz.002')]
samples = []
for group, n in [(sh60, 60), (sz00, 60), (sz30, 50), (sz002, 40)]:
    if len(group) > n:
        idx = np.random.choice(len(group), n, replace=False)
        samples.append(group.iloc[idx])
    elif len(group) > 0:
        samples.append(group)
df = pd.concat(samples)
print(f'  Stratified sample: {len(df)} stocks (sh60:{len(sh60)}, sz00:{len(sz00)}, sz30:{len(sz30)}, sz002:{len(sz002)})')
candidates = df.to_dict('records')
print(f"  Candidates (excluding ST): {len(candidates)}")

# ── Step 2: Pull K-lines batch by batch ──
print(f"\n[{datetime.now():%H:%M}] Step 2: Pulling K-lines in batches of {BATCH_SIZE}...")
all_tickers = [c['ticker'] for c in candidates]
all_klines = {}

for i in range(0, len(all_tickers), BATCH_SIZE):
    batch = all_tickers[i:i+BATCH_SIZE]
    batch_num = i // BATCH_SIZE + 1
    total_batches = (len(all_tickers) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"  Batch {batch_num}/{total_batches}: {len(batch)} tickers...")
    klines = cache_batch(batch, start_date="2026-01-01")
    all_klines.update(klines)
    print(f"    Got {len(klines)} K-lines (total: {len(all_klines)})")
    if i + BATCH_SIZE < len(all_tickers):
        time.sleep(3)

# ── Step 3: Build market context ──
print(f"\n[{datetime.now():%H:%M}] Step 3: Building market context...")
ctx = build_market_context()
print(f"  Limit-up: {ctx['limit_up_count']} | Max chain: {ctx['max_chain_height']}")
print(f"  Sector groups: {len(ctx['sector_leaderboard'])}")
print(f"  LHB entries: {len(ctx['lhb_data'])}")

# ── Step 4: Score all ──
print(f"\n[{datetime.now():%H:%M}] Step 4: Scoring {len(all_klines)} stocks...")
scorer = TristScorer(market_context=ctx)
results = []

processed = 0
for ticker, kline_df in all_klines.items():
    if len(kline_df) < 20:
        continue

    try:
        c = kline_df['close'].values; o = kline_df['open'].values
        h = kline_df['high'].values; l = kline_df['low'].values
        v = kline_df['volume'].values

        price = float(c[-1])
        ma5 = float(np.mean(c[-5:]))
        ma10 = float(np.mean(c[-10:]))
        ma20 = float(np.mean(c[-20:]))
        ma60 = float(np.mean(c[-min(60,len(c)):]))
        ret_1d = float(c[-1]/c[-2]-1) if len(c)>=2 else 0
        ret_3d = float(c[-1]/c[-min(4,len(c))]-1) if len(c)>=4 else 0
        ret_5d = float(c[-1]/c[-min(6,len(c))]-1) if len(c)>=6 else 0
        ret_10d = float(c[-1]/c[-min(11,len(c))]-1) if len(c)>=11 else 0
        ret_20d = float(c[-1]/c[-min(21,len(c))]-1) if len(c)>=21 else ret_5d*4

        vol_ma5 = np.mean(v[-5:]); vol_ratio = float(v[-1]/vol_ma5) if vol_ma5>0 else 1
        prev_vol_ratio = float(v[-2]/vol_ma5) if len(v)>=2 and vol_ma5>0 else 1
        prev_ret = float(c[-2]/c[-3]-1) if len(c)>=3 else 0

        # RSI
        delta = np.diff(c[-15:])
        gain = np.mean(delta[delta>0]) if len(delta[delta>0])>0 else 0
        loss = np.mean(-delta[delta<0]) if len(delta[delta<0])>0 else 0.0001
        rsi14 = float(100-100/(1+gain/loss))

        # Amplitude
        amp_3d = float(np.mean([(h[-i]-l[-i])/o[-i] for i in range(1,min(4,len(c)+1)) if o[-i]>0]))
        high_20d = float(np.max(h[-20:]))

        # Limit-up chain
        chain = 0
        for i in range(len(c)-1, max(len(c)-8, 0), -1):
            if c[i]/c[i-1]-1 > 0.095: chain += 1
            else: break

        indicators = {
            'ticker': ticker, 'price': price, 'ma5': ma5, 'ma10': ma10,
            'ma20': ma20, 'ma60': ma60, 'pre_5d_return': ret_5d,
            'pre_3d_return': ret_3d, 'pre_10d_return': ret_10d,
            'pre_20d_return': ret_20d, 'vol_ratio': vol_ratio,
            'prev_day_vol_ratio': prev_vol_ratio, 'prev_day_ret': prev_ret,
            'today_ret': ret_1d, 'avg_turnover_5d': float(np.mean(v[-5:])/1e6),
            'avg_daily_volume_5d': float(np.mean(v[-5:])),
            'avg_amplitude_3d': amp_3d, 'high_20d': high_20d,
            'rsi14': rsi14, 'consecutive_limit_up_days': chain,
            'prev_day_limit_up': prev_ret > 0.095,
            'has_bad_news_3d': False,
        }

        # Entry signals
        kline_dict = {k: list(v) for k, v in {
            'closes': c, 'opens': o, 'highs': h, 'lows': l, 'volumes': v
        }.items()}
        signals = detect_entry_signals(kline_dict, ticker)

        candidate = next((x for x in candidates if x['ticker'] == ticker), {})
        indicators['name'] = candidate.get('name', '')

        result = scorer.score(indicators, {})
        result.entry_signals = [s.name for s in signals]

        if not result.vetoed and result.total_score >= 60:
            results.append(result)
    except Exception as e:
        pass

    processed += 1
    if processed % 50 == 0:
        print(f"  ... {processed} scored, {len(results)} passed")

print(f"  Scored: {processed}, Passed (>=60 + no veto): {len(results)}")

# ── Step 5: Rank and output ──
results.sort(key=lambda r: r.total_score, reverse=True)
top = results[:10]

print(f"\n{'='*70}")
print(f"  TRIST SELECTOR - TOP 10 | {datetime.now():%Y-%m-%d %H:%M}")
print(f"{'='*70}")

for i, r in enumerate(top):
    pos = {'full': '[FULL]', 'half': '[HALF]', 'observe': '[WATCH]'}.get(r.position, '?')
    core_str = ''.join(['+' if v else '-' for v in r.core_details.values()])
    sig_str = ','.join(r.entry_signals[:3]) if r.entry_signals else '-'

    print(f"\n  #{i+1} {pos} {r.name}({r.ticker}) - {r.total_score} pts @ {r.price}")
    print(f"     Core: {core_str} | Signals: {sig_str}")
    if r.emotion_phase:
        print(f"     Emotion: {r.emotion_phase} | Leader: {r.leader_level} | Sector rank: {r.sector_rank}")

# Save
output = {
    'date': datetime.now().isoformat(),
    'top10': [
        {
            'rank': i+1, 'ticker': r.ticker, 'name': r.name, 'price': r.price,
            'score': r.total_score, 'position': r.position, 'position_pct': r.position_pct,
            'core': {k: v for k, v in r.core_details.items()},
            'bonus': {k: v for k, v in r.bonus_details.items()},
            'signals': r.entry_signals, 'emotion': r.emotion_phase,
            'leader': r.leader_level, 'vetoed': r.vetoed,
        }
        for i, r in enumerate(top)
    ],
    'stats': {'candidates': len(candidates), 'scored': processed, 'passed': len(results)}
}

out_path = os.path.join(OUT_DIR, f"top10_{datetime.now():%Y%m%d_%H%M}.json")
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n  Saved: {out_path}")
