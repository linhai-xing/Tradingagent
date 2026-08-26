"""通富微电 entry analysis"""
import sys, os, numpy as np
sys.path.insert(0, r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector')

cache = r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector\data_cache\002156.csv'
if os.path.exists(cache): os.remove(cache)

from data_cache import update_one
from direct_api import get_realtime_quote

rt = get_realtime_quote('002156')
df = update_one('002156', start_date='2026-03-01')
c = df['close'].values; h = df['high'].values; l = df['low'].values
v = df['volume'].values; o = df['open'].values; dates = df['date'].values

price = rt['price'] if rt else float(c[-1])
today_h = rt.get('high', 0); today_low = rt.get('low', 0); today_o = rt.get('open', 0)
prev_close = rt.get('prev_close', 0); change_today = rt.get('change_pct', 0)
turnover = rt.get('turnover', 0); amp = rt.get('amplitude', 0)

c_live = np.append(c, price)
ma5 = float(np.mean(c_live[-5:])); ma10 = float(np.mean(c_live[-10:])); ma20 = float(np.mean(c_live[-20:]))
high20 = float(max(np.max(h[-20:]), price))
pullback = (high20 - price) / high20

vol_ma5 = float(np.mean(v[-5:])); vol_ma20 = float(np.mean(v[-20:]))
vol_trend = 'up' if vol_ma5 > vol_ma20 * 1.2 else ('down' if vol_ma5 < vol_ma20 * 0.8 else 'flat')

pivot = (today_h + today_low + price) / 3
r1 = 2 * pivot - today_low; s1 = 2 * pivot - today_h

# V-reversal history
v_patterns = []
for i in range(20, len(c)):
    ma10_i = np.mean(c[i-10:i])
    if l[i] < ma10_i and c[i] > ma10_i:
        ret5 = float(c[min(i+5, len(c)-1)] / c[i] - 1) * 100 if i+5 < len(c) else 0
        v_patterns.append({'date': str(dates[i])[:10], 'pnl': ret5})

print('通富微电 (002156) Entry Analysis')
print('=' * 55)
print(f'Price: {price:.2f} | Today: {change_today:+.1f}% | Range: {amp:.1f}%')
print(f'Prev close: {prev_close:.2f} | Open: {today_o:.2f} | High: {today_h:.2f} | Low: {today_low:.2f}')
print(f'Turnover: {turnover:.1f}% | Volume trend: {vol_trend}')
print()

print('=== Key Levels ===')
print(f'  MA5:  {ma5:.2f}  (short-term resistance)')
print(f'  MA10: {ma10:.2f}  (core support, S10 V-reversal baseline)')
print(f'  MA20: {ma20:.2f}  (mid-term trend)')
print(f'  20d High: {high20:.2f}  (pullback: {pullback:.0%})')
print(f'  Pivot: {pivot:.2f} | R1: {r1:.2f} | S1: {s1:.2f}')
print()

print('=== Entry Scenarios ===')
print()

# Scenario A: Pullback to MA10
buf_a = (price - ma10) / price * 100
print(f'[A] Pullback to MA10 ({ma10:.2f}) -- RECOMMENDED')
print(f'  Setup: Open flat/down, shrink volume to MA10 area ({ma10:.2f})')
print(f'  Buffer from current: {buf_a:.1f}%')
print(f'  Entry zone: {ma10*0.98:.2f} - {ma10*1.01:.2f}')
print(f'  Stop loss: {ma10*0.97:.2f} (-3% below MA10)')
print(f'  Position: HALF first, add if confirms')
print()

# Scenario B: High open, MA5 retest
buf_b = (ma5 - price) / price * 100
print(f'[B] Gap up + MA5 ({ma5:.2f}) retest')
print(f'  Setup: Gap up above MA5, then pull back to MA5 without breaking')
print(f'  Distance to MA5: {buf_b:+.1f}%')
print(f'  Entry: {ma5*0.995:.2f} (MA5 support confirmed)')
print(f'  Stop loss: {price*0.97:.2f} (-3% from current)')
print(f'  Position: FULL (trend confirmed)')
print()

# Scenario C: Gap down to MA20
buf_c = (price - ma20) / price * 100
print(f'[C] Gap down to MA20 ({ma20:.2f}) -- DO NOT CHASE')
print(f'  Setup: Gap down with volume to MA20')
print(f'  Distance: {buf_c:.1f}%')
print(f'  Action: WAIT for S10 V-reversal signal before entry')
print(f'  Position: NO BUY until signal confirms')
print()

# V-reversal history
print('=== Historical V-Reversal ===')
wins = [p for p in v_patterns if p['pnl'] > 0]
if v_patterns:
    avg_ret = np.mean([p['pnl'] for p in v_patterns])
    print(f'Last 3mo: {len(v_patterns)} signals, {len(wins)/len(v_patterns)*100:.0f}% win, avg +{avg_ret:.1f}% after 5d')
    for p in v_patterns[-5:]:
        print(f"  {p['date']}: +{p['pnl']:.1f}% after 5d")
else:
    print('No historical V-reversal data')

# Summary
print()
print('=' * 55)
print('SUMMARY')
print(f'Best entry: Scenario A -- pullback to MA10 ({ma10:.2f}) on low volume')
print(f'Stop loss: {ma10*0.97:.2f}')
print(f'Target 1: MA5 ({ma5:.2f}), Target 2: 20d high ({high20:.2f})')
print(f'Risk/reward: {(ma5-price)/price*100:+.1f}% upside to MA5, {(price-ma10*0.97)/price*100:.1f}% risk')
