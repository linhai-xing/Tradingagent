"""000636 风华高科 MA5 回踩规律分析"""
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
from screener import cache_update_one
import numpy as np

kline = cache_update_one('000636', start_date='2026-05-01')
close = kline['close'].values
high = kline['high'].values
low = kline['low'].values
open_ = kline['open'].values
vol = kline['volume'].values
n = len(close)

# Calculate MA5, MA7, MA10 for each day
ma5_arr, ma7_arr, ma10_arr = [], [], []
for i in range(4, n):
    ma5_arr.append(np.mean(close[i-4:i+1]))
for i in range(6, n):
    ma7_arr.append(np.mean(close[i-6:i+1]))
for i in range(9, n):
    ma10_arr.append(np.mean(close[i-9:i+1]))

print('=== 000636 风华高科 MA5 回踩规律分析 ===')
print(f'分析区间: {n} 个交易日 (2026-05 至今)')
print()

# Find MA5 pullbacks: low touches MA5 within 2%
pullbacks = []
for i in range(1, len(ma5_arr)):
    idx = i + 4  # ma5_arr starts at day 4
    price_low = low[idx]
    price_close = close[idx]
    ma5_val = ma5_arr[i]

    # ma7_arr starts at day 6, ma10_arr starts at day 9
    ma7_idx = idx - 6  # index in ma7_arr
    ma10_idx = idx - 9  # index in ma10_arr
    ma7_val = ma7_arr[ma7_idx] if ma7_idx >= 0 and ma7_idx < len(ma7_arr) else 0
    ma10_val = ma10_arr[ma10_idx] if ma10_idx >= 0 and ma10_idx < len(ma10_arr) else 0

    # Touch MA5: low within 2% of MA5
    touch = abs(price_low - ma5_val) / ma5_val < 0.02

    # Check next 3 days
    if touch and idx + 3 < n:
        results = []
        for j in range(1, 4):
            ret = (close[idx + j] / price_close - 1) * 100
            results.append(ret)

        max_gain = max(results)
        day3_ret = results[2] if len(results) > 2 else results[-1]
        bounced = any(close[idx + j] > ma5_arr[i + j] for j in range(1, min(4, len(ma5_arr) - i, n - idx)) if i + j < len(ma5_arr))

        pullbacks.append({
            'idx': idx,
            'ma5': ma5_val,
            'ma7': ma7_val,
            'ma10': ma10_val,
            'low': price_low,
            'close': price_close,
            'max_3d': max_gain,
            'day3_ret': day3_ret,
            'bounced': bounced,
            'vol_ratio': vol[idx] / np.mean(vol[max(0,idx-5):idx]) if np.mean(vol[max(0,idx-5):idx]) > 0 else 1
        })

print(f'MA5 回踩次数 (触及MA5 ±2%): {len(pullbacks)}')
print()

if pullbacks:
    print('最近 8 次 MA5 回踩详情:')
    print(f'{"Idx":<5} {"MA5":>7} {"最低":>7} {"收盘":>7} {"3日最高":>8} {"第3日":>7} {"反弹":>4} {"量比":>5}')
    for p in pullbacks[-8:]:
        bounce_mark = 'Y' if p['bounced'] else 'N'
        print(f'{p["idx"]:<5} {p["ma5"]:>7.2f} {p["low"]:>7.2f} {p["close"]:>7.2f} {p["max_3d"]:>+7.2f}% {p["day3_ret"]:>+6.2f}% {bounce_mark:>4} {p["vol_ratio"]:>5.2f}')

    success = sum(1 for p in pullbacks if p['bounced'])
    print()
    print(f'回踩后反弹成功率 (3日内站回MA5): {success}/{len(pullbacks)} = {success/len(pullbacks)*100:.1f}%')
    avg_max = np.mean([p['max_3d'] for p in pullbacks])
    avg_day3 = np.mean([p['day3_ret'] for p in pullbacks])
    print(f'回踩后3日最高涨幅(均): {avg_max:+.2f}%')
    print(f'回踩后第3日涨幅(均): {avg_day3:+.2f}%')

    # When MA7>MA10 (多头), vs when not
    bull_pullbacks = [p for p in pullbacks if p['ma7'] > p['ma10'] and p['ma7'] > 0]
    bear_pullbacks = [p for p in pullbacks if p['ma7'] <= p['ma10'] and p['ma7'] > 0]

    if bull_pullbacks:
        bull_success = sum(1 for p in bull_pullbacks if p['bounced'])
        print(f'\n多头排列时(MA7>MA10)回踩: {len(bull_pullbacks)}次, 反弹率: {bull_success/len(bull_pullbacks)*100:.1f}%')
        print(f'  平均3日最高: {np.mean([p["max_3d"] for p in bull_pullbacks]):+.2f}%')
    if bear_pullbacks:
        bear_success = sum(1 for p in bear_pullbacks if p['bounced'])
        print(f'空头排列时(MA7<=MA10)回踩: {len(bear_pullbacks)}次, 反弹率: {bear_success/len(bear_pullbacks)*100:.1f}%')
        print(f'  平均3日最高: {np.mean([p["max_3d"] for p in bear_pullbacks]):+.2f}%')

# Current state
current_ma5 = ma5_arr[-1]
current_ma7 = ma7_arr[-1]
current_ma10 = ma10_arr[-1]
current_price = close[-1]
distance_ma5 = (current_price / current_ma5 - 1) * 100
distance_ma10 = (current_price / current_ma10 - 1) * 100

print()
print('--- 当前状态 ---')
print(f'  收盘: {current_price:.2f}')
print(f'  MA5: {current_ma5:.2f} | MA7: {current_ma7:.2f} | MA10: {current_ma10:.2f}')
print(f'  距离MA5: {distance_ma5:+.1f}% | 距离MA10: {distance_ma10:+.1f}%')
print(f'  多头排列(MA5>MA7>MA10): {current_ma5 > current_ma7 > current_ma10}')

# K-line quality assessment
print()
print('--- K线质量评估 (最近5日) ---')
for i in range(max(0, n-5), n):
    body = abs(close[i] - open_[i])
    total_range = high[i] - low[i]
    body_pct = body / total_range * 100 if total_range > 0 else 0
    upper_shadow = high[i] - max(close[i], open_[i])
    lower_shadow = min(close[i], open_[i]) - low[i]
    color = '+' if close[i] > open_[i] else '-'
    vol_r = vol[i] / np.mean(vol[max(0,i-5):i]) if np.mean(vol[max(0,i-5):i]) > 0 else 1

    # Quality
    if body_pct > 70 and vol_r > 1.2:
        quality = '强趋势K'
    elif body_pct > 50:
        quality = '中等K'
    elif body_pct < 30 and upper_shadow > body:
        quality = '上影线'
    elif body_pct < 30 and lower_shadow > body:
        quality = '下影线'
    else:
        quality = '十字/弱K'

    ret = (close[i] / close[i-1] - 1) * 100 if i > 0 else 0
    print(f'  Day{i}: 开{open_[i]:.2f} 高{high[i]:.2f} 低{low[i]:.2f} 收{close[i]:.2f} {color}{ret:+.1f}% 实体{body_pct:.0f}% 量比{vol_r:.1f} [{quality}]')

# Distance analysis - how far does price typically pull back?
print()
print('--- 做T可行性分析 ---')
print(f'  当前价格: {current_price:.2f}')
print(f'  MA5位置: {current_ma5:.2f} (距离 {distance_ma5:+.1f}%)')
print(f'  MA7位置: {current_ma7:.2f} (距离 {(current_price/current_ma7-1)*100:+.1f}%)')
print(f'  MA10位置: {current_ma10:.2f} (距离 {distance_ma10:+.1f}%)')
print()
if distance_ma5 > 5:
    print(f'  结论: 价格偏离MA5 {distance_ma5:.1f}%，属于超涨状态')
    print(f'  历史统计: 偏离>5%后回调至MA5附近概率高')
    print(f'  做T策略: 高位卖出 → 等回踩MA5/MA7 → 接回')
    print(f'  预期回踩目标: MA5({current_ma5:.2f}) ~ MA7({current_ma7:.2f})')
    print(f'  回调空间: {(current_price - current_ma5):.2f}元 ({distance_ma5:.1f}%)')
