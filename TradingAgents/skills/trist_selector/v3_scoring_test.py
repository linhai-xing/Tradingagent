"""Temporary script: apply v3 scoring to 603823"""
import csv

# Load all cached data
with open(r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector\data_cache\603823.csv', 'r') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

dates = [r['date'] for r in rows]
closes = [float(r['close']) for r in rows]
highs = [float(r['high']) for r in rows]
lows = [float(r['low']) for r in rows]
volumes = [float(r['volume']) for r in rows]

# Add latest data (cached data already has through 7/10)
closes.append(66.00); dates.append('2026-07-13')
closes.append(63.72); dates.append('2026-07-14')

today_open = 65.34
today_high = 66.50
today_low = 59.40
today_close = 63.72
today_vol = 12321381
prev_close = 66.00

print('=== 603823 百合花 v3.0 Scoring ===')
print(f'7/14 real-time: {today_close:.2f} ({((today_close/prev_close)-1)*100:+.1f}%)')
print(f'Intraday: O={today_open:.2f} H={today_high:.2f} L={today_low:.2f}')
print()

# MAs
for p in [5, 10, 20]:
    ma = sum(closes[-p:]) / p
    diff = (today_close / ma - 1) * 100
    print(f'MA{p}: {ma:.2f} | price vs MA{p}: {diff:+.1f}%')

ma5 = sum(closes[-5:]) / 5
ma10 = sum(closes[-10:]) / 10
ma20 = sum(closes[-20:]) / 20
ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else sum(closes[-len(closes):]) / len(closes)

today_ret = (today_close / prev_close - 1)
ret5d = (today_close / closes[-6] - 1)
vol_ratio = today_vol / (sum(volumes[-6:-1]) / 5) if len(volumes) >= 6 else 1
avg_turnover = 6.5  # approximate from known values

print()
print('=' * 50)
print('  CORE (max 60)')
print('=' * 50)

core_score = 0

# C1: Trend (v3.1 — price > MA10 means trend intact)
c1 = today_close > ma10 > 0
if c1: core_score += 10
gt = ">" if c1 else "<"
print(f'C1 Trend      ({10 if c1 else 0}/10): price({today_close:.1f}) {gt} MA10({ma10:.1f})')

# C2: No chase
c2 = ret5d < 0.15
if c2: core_score += 10
print(f'C2 No Chase   ({10 if c2 else 0}/10): 5d return {ret5d*100:.1f}% vs 15%')

# C3: Volume
c3 = 0.02 <= avg_turnover/100 <= 0.20 and 0.5 <= vol_ratio <= 3.0
if c3: core_score += 10
print(f'C3 Volume     ({10 if c3 else 0}/10): turnover ~{avg_turnover:.1f}%, vol_ratio ~{vol_ratio:.1f}')

# C4: Sector
c4 = True  # from screener
if c4: core_score += 10
print(f'C4 Sector     ({10 if c4 else 0}/10): sector rank top 40%')

# C5: Emotion
lu_count = 35
if lu_count <= 30:
    c5_score = 10; phase = 'Ice'
elif lu_count <= 50:
    c5_score = 10; phase = 'Diverge'
elif lu_count <= 80:
    c5_score = 5; phase = 'Consensus'
else:
    c5_score = 0; phase = 'Euphoria'
core_score += c5_score
print(f'C5 Emotion    ({c5_score}/10): {phase} (LU={lu_count})')

# C6: Leader
c6_score = 5  # follower
core_score += c6_score
print(f'C6 Leader     ({c6_score}/10): follower (top 5, not leader)')

print(f'\n  Core subtotal: {core_score}/60')

print()
print('=' * 50)
print('  BONUS (max 40)')
print('=' * 50)

bonus_score = 0

# B2: Divergence reversal (6)
b2 = False
if b2: bonus_score += 6
print(f'B2 Divergence ({6 if b2 else 0}/6): prev day not bearish')

# B6: Weak-to-strong (6)
b6 = False  # today is -3.45%, not positive
if b6: bonus_score += 6
print(f'B6 Weak2Strong({6 if b6 else 0}/6): today {today_ret*100:.1f}% (need >3%)')

# B8: Seat match (5)
b8 = False
if b8: bonus_score += 5
print(f'B8 Elite Seat ({5 if b8 else 0}/5): no LHB data')

# B1: Leader rank (4)
b1 = False
if b1: bonus_score += 4
print(f'B1 Leader ID  ({4 if b1 else 0}/4): not sector top 3')

# B4: Reasonable pullback (4)
h20 = max(highs[-20:])
pb = (h20 - today_close) / h20
b4 = 0.03 <= pb <= 0.12
if b4: bonus_score += 4
print(f'B4 Pullback   ({4 if b4 else 0}/4): 20d high {h20:.1f}, pullback {pb*100:.1f}% (3-12%)')

# B7: First board (4)
ret20d = (today_close / closes[-21] - 1)
b7 = ret20d < 0.20
if b7: bonus_score += 4
print(f'B7 FirstBoard ({4 if b7 else 0}/4): 20d ret {ret20d*100:.1f}% vs 20%')

# B9: Big capital (4)
b9 = True  # daily amount ~7.8B > 5B
if b9: bonus_score += 4
print(f'B9 BigCapital ({4 if b9 else 0}/4): daily amount 7.8B > 5B')

# B3: Research (4)
b3 = False
if b3: bonus_score += 4
print(f'B3 Research   ({4 if b3 else 0}/4): no recent reports')

# B5: Earnings (3)
b5 = False
if b5: bonus_score += 3
print(f'B5 Earnings   ({3 if b5 else 0}/3): no earnings data')

print(f'\n  Bonus subtotal: {bonus_score}/40')

total = core_score + bonus_score
position = 'FULL' if total >= 80 else 'HALF' if total >= 60 else 'OBSERVE'

print()
print('=' * 50)
print(f'  TOTAL: {total}/100 => {position}')
print('=' * 50)

# Forbidden check
print()
print('--- Forbidden Check ---')
fb = []
if ma5 < ma10:
    fb.append(f'X9: MA5({ma5:.1f}) < MA10({ma10:.1f}) death cross')
if ret5d > 0.20:
    fb.append(f'X1: 5d return {ret5d*100:.1f}% > 20%')
if today_low > today_high * 1.1:
    fb.append('X7: limit-up next day')

if fb:
    print('FORBIDDEN TRIGGERED:')
    for f in fb:
        print(f'  X {f}')
    print('=> VETOED (score = 0)')
else:
    print('No forbidden zones triggered')

# Entry signals
print()
print('--- Entry Signals ---')
sig = []
if today_low < ma10 and today_close > ma10:
    sig.append('S5: Tail-close stabilization (pierced MA10 intraday, closed above)')
if today_close > today_open:
    sig.append('S8: First-yin dip buy (closed positive)')
if today_low < ma10 * 0.95:
    sig.append('S1: Near doji/shakeout pattern')

if sig:
    for s in sig:
        print(f'  + {s}')
else:
    print('  No entry signals triggered')
