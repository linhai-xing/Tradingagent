"""
Targeted Sector Screen v4.0
"""
import noproxy
import os, sys, json, time
from datetime import datetime
import pandas as pd
import numpy as np

# Fix Windows GBK encoding
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(__file__))

from direct_api import _get_tencent_quote
from data_cache import _load_cache
from screener import compute_indicators, load_discipline_state
from scoring import TristScorer, build_market_context
from entry_signals import detect_entry_signals, get_entry_recommendation

CACHE_DIR = os.path.join(os.path.dirname(__file__), "data_cache")
OUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUT_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════
# Comprehensive sector pool: 存储 + 芯片 + 光通信 + 半导体
# Based on sector_full.py BK codes:
#   BK1113 存储芯片 | BK1036 半导体 | BK1136 光通信模块
#   BK1150 CPO概念 | BK1098 AI芯片 | BK1163 先进封装
#   BK0429 PCB | BK1028 第三代半导体
# ═══════════════════════════════════════════════════════════

POOL = {
    # ── 存储芯片 (BK1113) ──
    '002049', '688256', '688525', '688110', '688766', '300458',
    '300672', '300223', '603160', '688368', '300327', '600171',
    '002185', '688187', '300623', '688019', '300782',

    # ── CPO / 光通信 (BK1150, BK1136) ──
    '300308', '300502', '300394', '002281', '000988', '300570',
    '300620', '300548', '688048', '688498', '688608', '688595',
    '688313', '300757', '603083',

    # ── 半导体设备 (BK1036) ──
    '002371', '688012', '688082', '688120', '688072', '688037',
    '688200', '688596', '300604', '300666', '603690', '688559',
    '688138', '300456',

    # ── IC设计 (BK1036, BK1098) ──
    '603501', '603986', '300661', '688521', '688536',
    '688099', '688018', '002079', '603893', '688041',

    # ── 封测/Foundry (BK1163) ──
    '600584', '002156', '688981', '600703', '600460', '603005',
    '688396', '605358', '603290', '605111',

    # ── PCB ──
    '002916', '002463', '002938', '002436', '603228', '300476',
    '002384', '603920', '002579', '300657', '300735', '603186',
    '688183', '300852', '600601', '002134', '300739', '603989',
    '300632', '600522',

    # ── 半导体材料 (BK1028) ──
    '002409', '300236', '300346', '300102', '300708', '002129',
    '300576', '688300', '300684', '603650',

    # ── AI/算力 ──
    '300474', '603019', '600667', '300212',

    # ── LED/显示 ──
    '000725', '002456', '300433',

    # ── 存储模组/分销 ──
    '300042', '300475', '001309', '600745',

    # ── 半导体检测 ──
    '688279', '300456',
}

# Deduplicate
tickers = sorted(set(POOL))
# Filter to only cached tickers
cached = [t for t in tickers if os.path.exists(os.path.join(CACHE_DIR, f'{t}.csv'))]
missing = [t for t in tickers if t not in cached]

print("=" * 65)
print(f"  Trist Selector v4.0 — 存储/芯片/光通信/半导体 定向筛选")
print(f"  触发: 美股存储芯片光通信半导体大涨 → 国内联动")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"  股票池: {len(tickers)} stocks | 已缓存: {len(cached)} | 缺失: {len(missing)}")
print("=" * 65)

TENCENT_DELAY = 0.12

# ── Step 1: Compute indicators & trend pre-filter ──
print(f"\n[1/5] Computing indicators & trend filtering...")
trending = []
veto_count = 0
no_data_count = 0

for i, t in enumerate(cached):
    df = _load_cache(t)
    if len(df) < 20:
        no_data_count += 1
        continue

    ind = compute_indicators(df)
    if not ind:
        no_data_count += 1
        continue

    ma5 = ind.get('ma5', 0)
    ma10 = ind.get('ma10', 0)
    ma20 = ind.get('ma20', 0)
    price = float(df["close"].values[-1])

    # Lighter trend filter for sector screen (allow potential reversals)
    # Only filter extreme downtrends
    if not (ma5 > ma10 > ma20 and price > ma20):
        # Still include if near MA (potential reversal setup)
        if price < ma20 * 0.85:  # >15% below MA20 = deep downtrend, skip
            veto_count += 1
            continue

    today_ret = ind.get('today_ret', 0)
    if today_ret < -0.095:
        veto_count += 1
        continue

    trending.append({
        'ticker': t,
        'indicators': ind,
        'cached_price': price,
        'ret_5d': ind.get('pre_5d_return', 0),
        'ret_20d': ind.get('pre_20d_return', 0),
        'ma5': ma5,
        'ma20': ma20,
        'turnover': ind.get('avg_turnover_5d', 0),
        'vol_ratio': ind.get('vol_ratio', 1),
    })

print(f"  Trending: {len(trending)} | No data: {no_data_count} | Filtered: {veto_count}")

# ── Step 2: Fetch Tencent real-time quotes ──
print(f"\n[2/5] Fetching Tencent实时价格 for {len(trending)} stocks...")
valid = []
for i, stock in enumerate(trending):
    t = stock['ticker']
    try:
        rt = _get_tencent_quote(t)
        if rt and rt.get('price', 0) > 0:
            stock['rt_price'] = rt['price']
            stock['rt_name'] = rt.get('name', '')
            stock['rt_change_pct'] = rt.get('change_pct', 0)
            stock['rt_turnover'] = rt.get('turnover', 0)
            stock['rt_volume'] = rt.get('volume', 0)
            stock['rt_amplitude'] = rt.get('amplitude', 0)
            stock['rt_high'] = rt.get('high', 0)
            stock['rt_low'] = rt.get('low', 0)
            stock['rt_open'] = rt.get('open', 0)
            stock['rt_prev_close'] = rt.get('prev_close', 0)
            valid.append(stock)
        else:
            stock['rt_price'] = stock['cached_price']
            stock['rt_name'] = ''
            stock['rt_change_pct'] = 0
            valid.append(stock)
    except Exception:
        stock['rt_price'] = stock['cached_price']
        stock['rt_name'] = ''
        stock['rt_change_pct'] = 0
        valid.append(stock)

    if (i + 1) % 20 == 0:
        print(f"  Quotes: {i+1}/{len(trending)}")
    time.sleep(TENCENT_DELAY)

named = [s for s in valid if s.get('rt_name')]
print(f"  Valid quotes: {len(named)} with names / {len(valid)} total")

# ── Step 3: Market context ──
print(f"\n[3/5] Building market context...")
market_ctx = build_market_context()
print(f"  涨停: {market_ctx.get('limit_up_count', '?')} | 最高连板: {market_ctx.get('max_chain_height', '?')}")

# ── Step 4: Full PA scoring ──
print(f"\n[4/5] Full PA scoring (PA1-PA13 + B1-B9 + external)...")
scorer = TristScorer(market_context=market_ctx)
discipline_state = load_discipline_state()

results = []
for i, stock in enumerate(valid):
    t = stock['ticker']
    ind = stock['indicators'].copy()

    ind['ticker'] = t
    ind['name'] = stock.get('rt_name', f'股票{t}')
    ind['price'] = stock.get('rt_price', stock['cached_price'])
    ind['sector'] = ''
    ind['is_realtime'] = True

    if stock.get('rt_turnover', 0) > 0:
        ind['avg_turnover_5d'] = stock['rt_turnover']
    if stock.get('rt_change_pct', 0) != 0:
        ind['today_ret'] = stock['rt_change_pct'] / 100

    result = scorer.score(ind, {})

    # Entry signals
    df = _load_cache(t)
    kline_dict = {
        "closes": df["close"].tolist(),
        "opens": df["open"].tolist(),
        "highs": df["high"].tolist(),
        "lows": df["low"].tolist(),
        "volumes": df["volume"].tolist(),
    }
    signals = detect_entry_signals(kline_dict, t)
    entry_rec = get_entry_recommendation(signals)
    result.entry_signals = [s.name for s in signals]
    result.entry_recommendation = entry_rec
    result.rt_price = stock.get('rt_price', 0)
    result.rt_change_pct = stock.get('rt_change_pct', 0)
    result.rt_name = stock.get('rt_name', '')
    results.append(result)

    if (i + 1) % 30 == 0:
        print(f"  Scored: {i+1}/{len(valid)}")

# ── Step 5: Filter, sort, output ──
passed = [r for r in results if not r.vetoed and r.total_score >= 40]
vetoed = [r for r in results if r.vetoed]
passed.sort(key=lambda x: x.total_score, reverse=True)

# Show all candidates (not just top 5)
print(f"\n{'='*65}")
print(f"  RESULTS: {len(passed)} passed | {len(vetoed)} vetoed")
print(f"{'='*65}")

pos_emoji = {"full": "\033[1;32m满仓\033[0m", "half": "\033[1;33m半仓\033[0m", "observe": "观察"}

# Show top 15 (or all passed if fewer)
show_n = min(20, len(passed))
for i, r in enumerate(passed[:show_n]):
    name = getattr(r, 'rt_name', '') or r.name
    rt_pct = getattr(r, 'rt_change_pct', 0)
    rt_tag = f" 实时:{rt_pct:+.1f}%" if rt_pct != 0 else ""

    # Determine signal type description
    signal_desc = {
        "bullish": "[看涨]", "bearish": "[看跌]", "neutral": "[中性]",
        "bullish_pin": "[锤子线]", "bearish_pin": "[倒锤子]",
        "bullish_engulf": "[看涨吞没]", "bearish_engulf": "[看跌吞没]",
        "inside_bar": "[内包线]", "strong_trend": "[强趋势]"
    }.get(r.signal_bar_type, r.signal_bar_type or '')

    # Position and color
    if r.total_score >= 72:
        tag = "\033[1;32m★满仓\033[0m"
    elif r.total_score >= 54:
        tag = "\033[1;33m●半仓\033[0m"
    else:
        tag = "○观察"

    print(f"\n  #{i+1} {tag} {name}({r.ticker}) — {r.total_score}分 @{r.price:.2f}{rt_tag}")
    if hasattr(r, 'pa_details') and r.pa_details:
        pa_items = []
        for k, v in r.pa_details.items():
            if v != 0:
                sign = "+" if v > 0 else ""
                pa_items.append(f"{k}:{sign}{v}")
        print(f"    PA: {' | '.join(pa_items)}")
        print(f"    市场背景:{r.market_state} | 信号K线:{r.signal_bar_quality}({signal_desc})")
        print(f"    H{r.h_count}/L{r.l_count} | 楔形:{r.wedge_type or '无'} | SR共振:{r.sr_confluence}重")
    if r.bonus_details:
        bonus_items = [f"{k}=+{v}" for k, v in r.bonus_details.items() if v and v is not False]
        if bonus_items:
            print(f"    强化: {' '.join(bonus_items)}")
    if r.entry_signals:
        print(f"    入场信号: {', '.join(r.entry_signals[:5])}")
    if r.forbidden_hits:
        print(f"    ⛔禁区: {r.forbidden_hits}")
    print(f"    仓位:{r.position_pct*100:.0f}% | 外围:{r.external_score}/10")

# ── Veto summary ──
if vetoed:
    print(f"\n  ═══ 禁区剔除 ({len(vetoed)}只) ═══")
    veto_reasons = {}
    for r in vetoed:
        for hit in r.forbidden_hits:
            code = hit.split(':')[0] if ':' in hit else hit[:4]
            veto_reasons[code] = veto_reasons.get(code, 0) + 1
    for code, count in sorted(veto_reasons.items(), key=lambda x: -x[1]):
        print(f"    {code}: {count}只")

# ── Reverse candidates (low score but potential reversal) ──
print(f"\n{'='*65}")
print(f"  POTENTIAL REVERSAL CANDIDATES (评分<54但有反转潜力)")
print(f"{'='*65}")

# Find stocks with low score but potential reversal signals
reversal_candidates = []
for r in passed:
    if r.total_score < 54:
        # Check for reversal signals
        has_pin = 'pin' in str(r.signal_bar_type).lower() if r.signal_bar_type else False
        has_engulf = 'engulf' in str(r.signal_bar_type).lower() if r.signal_bar_type else False
        has_wedge = bool(r.wedge_type)
        has_sr = r.sr_confluence >= 2
        reversal_score = (3 if has_pin else 0) + (3 if has_engulf else 0) + (3 if has_wedge else 0) + (2 if has_sr else 0)

        if reversal_score >= 3:
            reversal_candidates.append((r, reversal_score))

reversal_candidates.sort(key=lambda x: -x[1])
for r, rev_score in reversal_candidates[:10]:
    name = getattr(r, 'rt_name', '') or r.name
    rt_pct = getattr(r, 'rt_change_pct', 0)
    signal_desc2 = {
        "bullish_pin": "[锤子线]", "bearish_pin": "[倒锤子]",
        "bullish_engulf": "[看涨吞没]", "bearish_engulf": "[看跌吞没]",
        "inside_bar": "[内包线]"
    }.get(r.signal_bar_type, r.signal_bar_type or '')

    print(f"  {name}({r.ticker}) 反转潜力:{rev_score}/8 | "
          f"评分:{r.total_score} | "
          f"信号:{signal_desc2} | "
          f"楔形:{r.wedge_type or '无'} | "
          f"SR:{r.sr_confluence}重 | "
          f"实时:{rt_pct:+.1f}%")

# ── Save JSON ──
output = {
    "date": datetime.now().strftime("%Y-%m-%d"),
    "trigger": "美股存储芯片光通信半导体大涨",
    "version": "v4.0-sector-targeted",
    "source": "cached_kline + tencent_realtime",
    "sectors": ["存储芯片", "半导体", "光通信/CPO", "AI芯片", "PCB", "先进封装"],
    "pool_size": len(tickers),
    "cached": len(cached),
    "scored": len(results),
    "passed": len(passed),
    "vetoed": len(vetoed),
    "rankings": [
        {
            "rank": i+1,
            "ticker": r.ticker,
            "name": getattr(r, 'rt_name', '') or r.name,
            "price": r.rt_price if hasattr(r, 'rt_price') else r.price,
            "change_pct": r.rt_change_pct if hasattr(r, 'rt_change_pct') else 0,
            "score": r.total_score,
            "pa_score": r.pa_score,
            "bonus_score": r.bonus_score,
            "position": r.position,
            "position_pct": r.position_pct,
            "market_state": r.market_state,
            "signal_bar": r.signal_bar_quality,
            "signal_type": r.signal_bar_type,
            "h_count": r.h_count,
            "l_count": r.l_count,
            "wedge": r.wedge_type,
            "sr": r.sr_confluence,
            "entry_signals": r.entry_signals,
            "forbidden_hits": r.forbidden_hits,
        }
        for i, r in enumerate(passed[:20])
    ],
    "reversal_candidates": [
        {
            "ticker": r.ticker,
            "name": getattr(r, 'rt_name', '') or r.name,
            "score": r.total_score,
            "reversal_potential": rev_score,
            "signal": r.signal_bar_type,
            "wedge": r.wedge_type,
            "sr": r.sr_confluence,
        }
        for r, rev_score in reversal_candidates[:10]
    ],
}

out_path = os.path.join(OUT_DIR, f"sector_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n  Saved: {out_path}")
