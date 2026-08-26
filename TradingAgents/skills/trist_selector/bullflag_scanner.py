"""
Bull Flag Scanner: 涨停→浅回踩不破→温和放量新高
Pattern matching: 002987京北方 style
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

CACHE_DIR = os.path.join(BASE, 'data_cache')
tickers = sorted([f.replace('.csv', '') for f in os.listdir(CACHE_DIR) if f.endswith('.csv')])

print(f'Bull Flag Scanner — 涨停旗形筛选')
print(f'扫描: {len(tickers)}只 | {datetime.now().strftime("%Y-%m-%d %H:%M")}')
print('=' * 60)

results = []

for i, t in enumerate(tickers):
    try:
        df = _load_cache(t)
        if len(df) < 60: continue

        o = df['open'].values; h = df['high'].values
        l_prices = df['low'].values; c = df['close'].values
        vol = df['volume'].values

        # ── 1. 找最近20日内的涨停 ──
        zt_idx = -1
        for j in range(len(c)-2, max(len(c)-22, 0), -1):
            chg = (c[j] - c[j-1]) / c[j-1]
            if chg >= 0.095:  # 涨停 >=9.5%
                zt_idx = j
                break

        if zt_idx < 0: continue  # 没有涨停

        # 距离涨停日天数
        days_since_zt = len(c) - 1 - zt_idx
        if days_since_zt < 3: continue  # 涨停太近
        if days_since_zt > 15: continue  # 涨停太远

        zt_open = o[zt_idx]
        zt_close = c[zt_idx]
        zt_high = h[zt_idx]
        zt_low = l_prices[zt_idx]
        zt_body = zt_close - zt_open
        zt_chg = (zt_close - c[zt_idx-1]) / c[zt_idx-1]

        # ── 2. 涨停后最低价不能跌破涨停开盘价 ──
        post_zt_lows = l_prices[zt_idx+1:]
        min_post = min(post_zt_lows)
        if min_post < zt_open: continue  # 破了开盘价 → 不合格

        max_pullback = (min_post - zt_close) / zt_close * 100
        if max_pullback < -8: continue  # 回踩超过8% → 不够浅

        # ── 3. 当前价格 vs 涨停高点 ──
        current = c[-1]
        above_zt_high = current > zt_high
        near_zt_high = current > zt_close * 0.97  # 在涨停价3%以内

        # ── 4. 均线排列 ──
        ma5 = pd.Series(c).rolling(5).mean().values[-1]
        ma10 = pd.Series(c).rolling(10).mean().values[-1]
        ma20 = pd.Series(c).rolling(20).mean().values[-1]
        if not (ma5 > ma10 > ma20): continue  # 必须多头排列

        # ── 5. 量能分析 ──
        # 涨停前均量
        pre_vol = np.mean(vol[zt_idx-10:zt_idx]) if zt_idx >= 10 else np.mean(vol[:zt_idx])
        zt_vol = vol[zt_idx]
        # 回踩量缩
        pullback_vol = np.mean(vol[zt_idx+1:zt_idx+4]) if zt_idx+4 < len(vol) else np.mean(vol[zt_idx+1:])
        if zt_vol > 0 and pullback_vol / zt_vol > 0.8: continue  # 回踩没有明显缩量

        # 最近3日量能（是否温和放量）
        recent_vol = np.mean(vol[-3:])
        if pullback_vol > 0 and recent_vol / pullback_vol < 0.8: continue  # 没有放量恢复

        # ── 6. 位置（不要在极端高位） ──
        h20 = max(h[-20:]); l20 = min(l_prices[-20:])
        pos20 = (current - l20) / (h20 - l20) * 100 if h20 > l20 else 50
        if pos20 > 97: continue  # 太极端高位

        # ── 7. 过滤ST、风险标的 ──
        if current < 3: continue  # 低价股排除
        if current > 200: continue  # 高价股排除（可能科创板/新股）

        # ── 综合评分 ──
        score = 0
        # 回踩越浅越好
        if max_pullback > -2: score += 3
        elif max_pullback > -4: score += 2
        elif max_pullback > -6: score += 1
        # 创新高加分
        if above_zt_high: score += 3
        elif near_zt_high: score += 1
        # 光头光脚涨停加分
        if zt_open == zt_low and zt_close == zt_high: score += 2
        elif zt_close == zt_high: score += 1
        # 最近3日连阳加分
        if c[-1] > o[-1] and c[-2] > o[-2] and c[-3] > o[-3]: score += 2
        elif c[-1] > o[-1]: score += 1
        # 缩量回踩加分
        if zt_vol > 0 and pullback_vol / zt_vol < 0.6: score += 1
        # 均线斜率加分
        if ma5 > ma10 * 1.02: score += 1  # 均线发散

        results.append({
            'ticker': t,
            'zt_date_idx': zt_idx,
            'days': days_since_zt,
            'zt_chg': zt_chg,
            'pullback': max_pullback,
            'above_high': above_zt_high,
            'current': current,
            'zt_open': zt_open,
            'zt_close': zt_close,
            'zt_high': zt_high,
            'ma5': ma5,
            'ma10': ma10,
            'ma20': ma20,
            'pos20': pos20,
            'score': score,
            'last_close': c[-1],
            'ret_5d': (c[-1]/c[-6]-1)*100 if len(c)>5 else 0,
        })

    except Exception as e:
        continue

    if (i+1) % 500 == 0: print(f'  已处理 {i+1}/{len(tickers)}, 找到 {len(results)}')

# 按评分排序
results.sort(key=lambda x: -x['score'])

print(f'\n找到 {len(results)} 只候选')

# 取前20获取实时行情
print(f'\n获取实时行情...')
for i, r in enumerate(results[:25]):
    try:
        rt = _get_tencent_quote(r['ticker'])
        time.sleep(0.10)
        if rt and rt.get('price', 0) > 0:
            r['name'] = rt.get('name', '')
            r['rt_price'] = rt['price']
            r['rt_change'] = rt.get('change_pct', 0)
        else:
            r['name'] = f'股票{r["ticker"]}'
            r['rt_price'] = r['current']
            r['rt_change'] = 0
    except:
        r['name'] = f'股票{r["ticker"]}'
        r['rt_price'] = r['current']
        r['rt_change'] = 0
    if (i+1) % 10 == 0: print(f'  {i+1}/{min(25,len(results))}')

# 输出
print(f'\n{"="*65}')
print(f'  Bull Flag 筛选结果 (涨停→浅回踩→放量新高)')
print(f'  排序: 综合评分 ↓')
print(f'{"="*65}')

for i, r in enumerate(results[:20]):
    name = r.get('name', '')
    rt_price = r.get('rt_price', r['current'])
    rt_chg = r.get('rt_change', 0)
    above = '★新高' if r['above_high'] else ('接近' if rt_price > r['zt_close']*0.97 else '下方')

    print(f"\n  #{i+1} [{r['score']}分] {name}({r['ticker']}) @{rt_price:.2f} 实时:{rt_chg:+.1f}%")
    print(f"    涨停: {r['days']}天前 +{r['zt_chg']*100:.1f}% | 回踩最深{r['pullback']:.1f}% | {above}")
    print(f"    MA: {r['ma5']:.2f}/{r['ma10']:.2f}/{r['ma20']:.2f} (多头) | 5日:{r['ret_5d']:+.1f}%")
    print(f"    20日位置: {r['pos20']:.0f}%")

# 输出002987对比
print(f"\n{'='*65}")
print(f'  002987 京北方 参考基准:')
print(f'    涨停: +10.7% | 回踩: -3.2% | 新高 | MA多头 | 5日+8.7%')

# 保存
out_path = os.path.join(BASE, 'output', f'bullflag_{datetime.now().strftime("%Y%m%d_%H%M")}.json')
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(results[:20], f, ensure_ascii=False, indent=2)
print(f'\nSaved: {out_path}')
