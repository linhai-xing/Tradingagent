"""
Trist Selector - 医药/煤炭 Signal Candle Scan (8/22-8/24)
Finds: bullish signal candles, MA10>MA20, turnover>=2%, score>=12
"""
import os, json, numpy as np
import baostock as bs
from data_cache import update_one

with open(os.path.join(os.path.dirname(__file__), 'output', 'sector_classification.json'), encoding='utf-8') as f:
    sector_data = json.load(f)

med_stocks = [s for s in sector_data['医药'] if 'ST' not in s['name']]
coal_stocks = [s for s in sector_data['煤炭'] if 'B06' in s['industry'] and 'ST' not in s['name']]
all_targets = med_stocks + coal_stocks
print(f'Total: {len(all_targets)} stocks ({len(med_stocks)} med + {len(coal_stocks)} coal)')

bs.login()
candidates = []

for stock in all_targets:
    ticker = stock['ticker']
    name = stock['name']
    sector = stock['industry']

    try:
        df = update_one(ticker, start_date='2026-06-01', bs_session=bs)
        if len(df) < 60:
            continue
    except Exception:
        continue

    c = df['close'].values.astype(float)
    o = df['open'].values.astype(float)
    h = df['high'].values.astype(float)
    l = df['low'].values.astype(float)
    n = len(c)

    # Check 8/22-8/24
    for target_date in ['2026-08-22', '2026-08-23', '2026-08-24']:
        target_idx = -1
        for j in range(n):
            if target_date in str(df.iloc[j]['date'])[:10]:
                target_idx = j
                break
        if target_idx < 0 or target_idx < 20:
            continue

        cur_c = float(c[target_idx])
        cur_o = float(o[target_idx])
        cur_h = float(h[target_idx])
        cur_l = float(l[target_idx])
        total_range = cur_h - cur_l
        if total_range == 0:
            continue

        body = abs(cur_c - cur_o)
        lower_shadow = min(cur_c, cur_o) - cur_l
        upper_shadow = cur_h - max(cur_c, cur_o)
        is_bullish = cur_c > cur_o
        close_pos = (cur_c - cur_l) / total_range
        body_ratio = body / total_range
        lower_shadow_ratio = lower_shadow / total_range
        upper_shadow_ratio = upper_shadow / total_range

        ma5 = float(np.mean(c[max(0, target_idx-4):target_idx+1]))
        ma10 = float(np.mean(c[max(0, target_idx-9):target_idx+1]))
        ma20 = float(np.mean(c[max(0, target_idx-19):target_idx+1]))

        # Candle type
        if body_ratio < 0.15:
            candle_type = '十字星'
        elif lower_shadow_ratio > 0.5 and body_ratio < 0.4:
            candle_type = '锤子线'
        elif upper_shadow_ratio > 0.5 and body_ratio < 0.4:
            candle_type = '倒锤子'
        elif body_ratio >= 0.7:
            candle_type = '强趋势' + ('阳线' if is_bullish else '阴线')
        elif is_bullish:
            candle_type = '阳线'
        else:
            candle_type = '阴线'

        # Only bullish signal candles
        if candle_type not in ('锤子线', '阳线', '强趋势阳线', '十字星'):
            continue

        # Trend: MA10 > MA20
        if not (ma10 > ma20):
            continue

        # Overlap
        if target_idx > 0:
            prev_h = float(h[target_idx - 1])
            prev_l = float(l[target_idx - 1])
            overlap_max = min(prev_h, cur_h)
            overlap_min = max(prev_l, cur_l)
            overlap_ratio = max(0, (overlap_max - overlap_min)) / total_range if total_range > 0 else 0
            is_inside = cur_h < prev_h and cur_l > prev_l
        else:
            overlap_ratio = 0
            is_inside = False

        turnover = float(df.iloc[target_idx].get('turn', 0))
        if turnover < 2.0:
            continue

        low_20d = float(np.min(l[max(0, target_idx-19):target_idx+1]))
        high_20d = float(np.max(h[max(0, target_idx-19):target_idx+1]))
        range_20d = high_20d - low_20d
        pos_in_range = (cur_c - low_20d) / range_20d if range_20d > 0 else 0.5

        prior_bearish = 0
        for j in range(target_idx - 1, max(target_idx - 6, -1), -1):
            if c[j] < o[j]:
                prior_bearish += 1
            else:
                break

        dist_ma20 = (cur_l - ma20) / ma20 * 100

        # Score
        score = 0
        reasons = []
        if close_pos >= 0.80:
            score += 10
            reasons.append(f'收盘位置极佳({close_pos:.0%})')
        elif close_pos >= 0.67:
            score += 7
            reasons.append(f'收盘位置良好({close_pos:.0%})')
        elif close_pos >= 0.50:
            score += 4
            reasons.append(f'收盘位置一般({close_pos:.0%})')

        if candle_type == '锤子线':
            score += 6
            reasons.append('Pin Bar锤子')
        elif candle_type == '十字星':
            if lower_shadow_ratio > 0.4:
                score += 5
                reasons.append('长下影十字星')
            else:
                score += 3
                reasons.append('十字星')
        elif candle_type == '强趋势阳线':
            score += 8
            reasons.append('强趋势阳线')
        elif candle_type == '阳线':
            score += 5
            reasons.append('阳线')

        if prior_bearish >= 2:
            score += 6
            reasons.append(f'前{prior_bearish}阴回调')
        elif prior_bearish == 1:
            score += 3

        if candle_type == '锤子线':
            score += 6
            reasons.append('Pin Bar特殊K线')
        elif is_inside:
            score += 3
            reasons.append('内包线')
        elif candle_type == '强趋势阳线':
            score += 5
            reasons.append('强趋势K线')

        if score >= 12:
            candidates.append({
                'ticker': ticker, 'name': name, 'sector': sector,
                'date': target_date,
                'price': cur_c, 'turnover': turnover,
                'candle_type': candle_type, 'is_bullish': is_bullish,
                'close_pos': close_pos, 'body_ratio': body_ratio,
                'lower_shadow_ratio': lower_shadow_ratio,
                'upper_shadow_ratio': upper_shadow_ratio,
                'overlap_ratio': overlap_ratio,
                'is_inside': is_inside,
                'pos_in_range': pos_in_range,
                'prior_bearish': prior_bearish,
                'ma5': ma5, 'ma10': ma10, 'ma20': ma20,
                'dist_ma20': dist_ma20,
                'signal_score': score,
                'reasons': reasons,
                'low_20d': low_20d, 'high_20d': high_20d,
            })

bs.logout()

candidates.sort(key=lambda x: x['signal_score'], reverse=True)
print(f'\nResults: {len(candidates)} candidates (score>=12, MA10>MA20, turnover>=2%)')
print('='*70)

for i, cand in enumerate(candidates[:20]):
    if cand['pos_in_range'] < 0.35:
        at_low = '[KEY LOW]'
    elif cand['pos_in_range'] < 0.65:
        at_low = '[MID]'
    else:
        at_low = '[HIGH]'
    print(f"\n{i+1}. [{cand['date']}] {cand['name']}({cand['ticker']}) | {cand['candle_type']} | score={cand['signal_score']} | {at_low}")
    print(f"   price={cand['price']:.2f} turnover={cand['turnover']:.1f}% close_pos={cand['close_pos']:.0%} body={cand['body_ratio']:.0%} lower_shadow={cand['lower_shadow_ratio']:.0%}")
    print(f"   overlap={cand['overlap_ratio']:.0%} inside={cand['is_inside']} 20d_pos={cand['pos_in_range']:.0%} prior_bearish={cand['prior_bearish']}")
    print(f"   MA5={cand['ma5']:.2f} MA10={cand['ma10']:.2f} MA20={cand['ma20']:.2f} dist_MA20={cand['dist_ma20']:.1f}%")
    print(f"   reasons: {', '.join(cand['reasons'])}")

with open(os.path.join(os.path.dirname(__file__), 'output', 'sector_scan_results.json'), 'w', encoding='utf-8') as f:
    json.dump(candidates, f, ensure_ascii=False, indent=2)

print(f'\nSaved {len(candidates)} candidates')