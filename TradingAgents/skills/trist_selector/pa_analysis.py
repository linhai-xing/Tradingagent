"""
Full PA analysis for 603439 (贵州三力) and 600758 (辽宁能源)
"""
import os, sys, json, numpy as np
sys.path.insert(0, os.path.dirname(__file__))

import baostock as bs
from data_cache import update_one
from datetime import datetime

bs.login()

for ticker in ['603439', '600758']:
    df = update_one(ticker, start_date='2026-01-01', bs_session=bs)
    c = df['close'].values.astype(float)
    o = df['open'].values.astype(float)
    h = df['high'].values.astype(float)
    l = df['low'].values.astype(float)
    v = df['volume'].values.astype(float)
    turns = [float(df.iloc[j].get('turn', 0)) for j in range(len(df))]
    n = len(c)

    # 8/24 candle
    target_idx = n - 1
    cur_c = c[target_idx]
    cur_o = o[target_idx]
    cur_h = h[target_idx]
    cur_l = l[target_idx]
    total_range = cur_h - cur_l

    body = abs(cur_c - cur_o)
    upper_shadow = cur_h - max(cur_c, cur_o)
    lower_shadow = min(cur_c, cur_o) - cur_l
    is_bullish = cur_c > cur_o

    close_pos = (cur_c - cur_l) / total_range
    body_ratio = body / total_range
    upper_shadow_ratio = upper_shadow / total_range
    lower_shadow_ratio = lower_shadow / total_range

    # MA
    ma5 = float(np.mean(c[-5:]))
    ma10 = float(np.mean(c[-10:]))
    ma20 = float(np.mean(c[-20:]))
    ma60 = float(np.mean(c[-60:]))

    # EMA20
    def calc_ema(vals, period):
        if len(vals) < period:
            return np.full(len(vals), float(np.mean(vals)))
        alpha = 2 / (period + 1)
        ema = np.zeros(len(vals))
        ema[0] = vals[0]
        for i in range(1, len(vals)):
            ema[i] = alpha * vals[i] + (1 - alpha) * ema[i-1]
        return ema

    ema20 = calc_ema(c, 20)
    ema20_val = float(ema20[-1])

    # MA gap
    ma_gap_bars = 0
    for i in range(n-1, max(n-60, 0), -1):
        if not (l[i] <= ema20[i] <= h[i]):
            ma_gap_bars += 1
        else:
            break

    # Trend bars
    trend_bar_count = 0
    for i in range(max(n-10, 0), n):
        bar_range = h[i] - l[i]
        if bar_range > 0 and abs(c[i] - o[i]) / bar_range >= 0.60:
            trend_bar_count += 1
    trend_bar_ratio = trend_bar_count / min(10, n)

    # Bar overlap
    overlap_count = 0
    lookback = min(20, n-1)
    for i in range(n - lookback + 1, n):
        ov_max = min(h[i-1], h[i])
        ov_min = max(l[i-1], l[i])
        if ov_max > ov_min:
            overlap_count += 1
    bar_overlap_ratio = overlap_count / max(lookback - 1, 1)

    # 20-day range
    low_20d = float(np.min(l[-20:]))
    high_20d = float(np.max(h[-20:]))
    range_20d = high_20d - low_20d
    pos_in_20d = (cur_c - low_20d) / range_20d if range_20d > 0 else 0.5
    range_amplitude = range_20d / low_20d if low_20d > 0 else 0.99

    # Returns
    ret_1d = float(c[-1] / c[-2] - 1) if n >= 2 else 0
    ret_5d = float(c[-1] / c[-6] - 1) if n >= 6 else 0
    ret_10d = float(c[-1] / c[-11] - 1) if n >= 11 else 0
    ret_20d = float(c[-1] / c[-21] - 1) if n >= 21 else 0

    # RSI14
    delta = np.diff(c[-15:])
    gains = delta[delta > 0]
    losses = -delta[delta < 0]
    avg_gain = float(np.mean(gains)) if len(gains) > 0 else 0
    avg_loss = float(np.mean(losses)) if len(losses) > 0 else 0.0001
    rsi14 = float(100 - 100 / (1 + avg_gain / avg_loss)) if avg_loss > 0 else 50

    # Chain
    chain = 0
    for i in range(n-1, max(n-10, 0), -1):
        if c[i] / c[i-1] - 1 > 0.095:
            chain += 1
        else:
            break

    # Volume
    vol_ma5 = float(np.mean(v[-5:]))
    vol_ratio = float(v[-1] / vol_ma5) if vol_ma5 > 0 else 1
    avg_turnover_5d = float(np.mean(turns[-5:]))
    turnover_8_24 = float(turns[-1])

    # 3d amplitude
    amp_3d = float(np.mean([(h[-i] - l[-i]) / o[-i] for i in range(1, min(4, n+1)) if o[-i] > 0]))

    # ATR5
    tr_vals = []
    for i in range(max(n-6, 1), n):
        tr = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
        tr_vals.append(tr)
    atr5 = float(np.mean(tr_vals)) if tr_vals else 0
    atr5_pct = float(atr5 / c[-1]) if c[-1] > 0 else 0

    # Open gap
    open_gap_pct = float((o[-1] - c[-2]) / c[-2] * 100) if n >= 2 else 0

    # Prior bearish
    prior_bearish = 0
    for i in range(n-2, max(n-7, -1), -1):
        if c[i] < o[i]:
            prior_bearish += 1
        else:
            break

    # Overlap with prev
    prev_h = float(h[-2])
    prev_l = float(l[-2])
    ov_max = min(prev_h, cur_h)
    ov_min = max(prev_l, cur_l)
    overlap_ratio = max(0, (ov_max - ov_min)) / total_range if total_range > 0 else 0
    is_inside = cur_h < prev_h and cur_l > prev_l
    is_outside = cur_h > prev_h and cur_l < prev_l

    # Candle type
    if body_ratio < 0.15:
        candle_type = '十字星'
    elif lower_shadow_ratio > 0.5 and body_ratio < 0.4:
        candle_type = '锤子线'
    elif upper_shadow_ratio > 0.5 and body_ratio < 0.4:
        candle_type = '倒锤子'
    elif body_ratio >= 0.70:
        candle_type = '强趋势阳线' if is_bullish else '强趋势阴线'
    elif is_bullish:
        candle_type = '阳线'
    else:
        candle_type = '阴线'

    # Swing points
    swing_highs = []
    swing_lows = []
    for i in range(2, min(30, n)):
        idx = n - 1 - i
        if idx < 2:
            continue
        if h[idx] > h[idx-1] and h[idx] > h[idx+1]:
            swing_highs.append(idx)
        if l[idx] < l[idx-1] and l[idx] < l[idx+1]:
            swing_lows.append(idx)

    # H-count
    recent_pullbacks = 0
    if len(swing_highs) > 0:
        last_high = swing_highs[0]
        for sl in swing_lows:
            if sl > last_high:
                recent_pullbacks += 1

    # Wedge
    wedge_type = 'none'
    if len(swing_highs) >= 3:
        h1v, h2v, h3v = h[swing_highs[0]], h[swing_highs[1]], h[swing_highs[2]]
        if h1v > h2v > h3v:
            wedge_type = 'rising_wedge'
        elif h1v < h2v < h3v:
            wedge_type = 'falling_wedge'

    # S/R
    sr_score = 0
    if abs(cur_l - ma20) / ma20 < 0.03:
        sr_score += 2
    if abs(cur_l - ma10) / ma10 < 0.03:
        sr_score += 2
    if abs(cur_l - ma5) / ma5 < 0.03:
        sr_score += 1
    if len(swing_lows) > 0 and abs(cur_l - l[swing_lows[0]]) / l[swing_lows[0]] < 0.02:
        sr_score += 2

    dist_ma20 = (cur_l - ma20) / ma20 * 100
    dist_ma10 = (cur_l - ma10) / ma10 * 100

    # ===== OUTPUT =====
    print(f'\n===== {ticker} =====')
    print(f'Signal Candle (8/24): {candle_type}')
    print(f'C={cur_c:.2f} O={cur_o:.2f} H={cur_h:.2f} L={cur_l:.2f}')
    print(f'close_pos={close_pos:.0%} body={body_ratio:.0%} lower_shadow={lower_shadow_ratio:.0%} upper_shadow={upper_shadow_ratio:.0%}')
    print(f'overlap={overlap_ratio:.0%} is_inside={is_inside} is_outside={is_outside} prior_bearish={prior_bearish}')
    print(f'MA5={ma5:.2f} MA10={ma10:.2f} MA20={ma20:.2f} MA60={ma60:.2f}')
    print(f'EMA20={ema20_val:.2f} MA_gap_bars={ma_gap_bars}')
    print(f'trend_bar_ratio={trend_bar_ratio:.0%} bar_overlap_ratio={bar_overlap_ratio:.0%}')
    print(f'20d_range={low_20d:.2f}-{high_20d:.2f} pos_in_20d={pos_in_20d:.0%} amplitude={range_amplitude:.0%}')
    print(f'ret_1d={ret_1d:.1%} ret_5d={ret_5d:.1%} ret_10d={ret_10d:.1%} ret_20d={ret_20d:.1%}')
    print(f'RSI14={rsi14:.1f} vol_ratio={vol_ratio:.2f} turnover_8_24={turnover_8_24:.2f}% avg_turnover_5d={avg_turnover_5d:.2f}%')
    print(f'ATR5%={atr5_pct:.1%} open_gap%={open_gap_pct:.2f}%')
    print(f'H_count={recent_pullbacks} wedge_type={wedge_type} sr_score={sr_score}')
    print(f'Lowest swing lows: {[float(l[i]) for i in swing_lows[:3]]}')
    print(f'dist_ma20={dist_ma20:.2f}% dist_ma10={dist_ma10:.2f}%')

bs.logout()
print('\nDone')