"""
Power Sector Screen v4.0 — 电力板块专场
火电+水电+核电+绿电+电网设备
"""
import noproxy
import os, sys, json, time
from datetime import datetime
import pandas as pd
import numpy as np
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
# 电力板块全场 (火电+水电+核电+绿电+电网)
# 板块代码参考: BK0425(电力行业) BK0482(绿色电力)
# ═══════════════════════════════════════════════════════════

POOL = {
    # ── 火电 ──
    '600396',  # 华电辽能 ★重点
    '600011', '600023', '600027', '600795', '601991',  # 五大发电
    '000539', '000543', '600886', '600578',  # 地方火电
    '600021', '000690', '000720', '000767',  # 更多火电

    # ── 水电 ──
    '600900',  # 长江电力(龙头)
    '600674', '600025', '000883',

    # ── 核电 ──
    '601985', '003816',

    # ── 绿电/新能源 ──
    '600905', '601016', '600163', '000862',

    # ── 电网/电力设备 ──
    '600406', '601877', '000400',

    # ── 地方电力 ──
    '600509', '600644', '600101', '600452', '600982', '000600',

    # ── 其他电力相关 ──
    '600483',  # 福能股份
    '600089',  # 特变电工
}

tickers = sorted(set(POOL))
cached = [t for t in tickers if os.path.exists(os.path.join(CACHE_DIR, f'{t}.csv'))]
missing = [t for t in tickers if t not in cached]

print("=" * 65)
print("  Trist Selector v4.0 — 电力板块 定向筛选")
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

    # Allow potential reversals - only filter deep downtrends
    if not (ma5 > ma10 > ma20 and price > ma20):
        if price < ma20 * 0.80:  # >20% below MA20
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
    if (i + 1) % 15 == 0: print(f"  Quotes: {i+1}/{len(trending)}")
    time.sleep(TENCENT_DELAY)

named = [s for s in valid if s.get('rt_name')]
print(f"  Valid: {len(named)} with names / {len(valid)} total")

# ── Step 3: Market context ──
print(f"\n[3/5] Building market context...")
market_ctx = build_market_context()
print(f"  涨停: {market_ctx.get('limit_up_count', '?')} | 最高连板: {market_ctx.get('max_chain_height', '?')}")

# ── Step 4: Full PA scoring ──
print(f"\n[4/5] Full PA scoring (PA1-PA13 + B1-B9)...")
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

    if stock.get('rt_turnover', 0) > 0: ind['avg_turnover_5d'] = stock['rt_turnover']
    if stock.get('rt_change_pct', 0) != 0: ind['today_ret'] = stock['rt_change_pct'] / 100

    result = scorer.score(ind, {})
    df = _load_cache(t)
    kline_dict = {
        "closes": df["close"].tolist(), "opens": df["open"].tolist(),
        "highs": df["high"].tolist(), "lows": df["low"].tolist(),
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

    if (i + 1) % 15 == 0: print(f"  Scored: {i+1}/{len(valid)}")

# ── Step 5: Output ──
passed = [r for r in results if not r.vetoed and r.total_score >= 40]
vetoed = [r for r in results if r.vetoed]
passed.sort(key=lambda x: x.total_score, reverse=True)

print(f"\n{'='*65}")
print(f"  RESULTS: {len(passed)} passed | {len(vetoed)} vetoed")
print(f"{'='*65}")

# ── 600396 special highlight ──
r396 = None
for r in passed:
    if r.ticker == '600396':
        r396 = r
        break

show_n = min(20, len(passed))
for i, r in enumerate(passed[:show_n]):
    name = getattr(r, 'rt_name', '') or r.name
    rt_pct = getattr(r, 'rt_change_pct', 0)
    rt_tag = f" 实时:{rt_pct:+.1f}%" if rt_pct != 0 else ""

    # Highlight 600396
    prefix = ">>>" if r.ticker == '600396' else "  "

    if r.total_score >= 72:
        tag = "[满仓]"
    elif r.total_score >= 54:
        tag = "[半仓]"
    else:
        tag = "[观察]"

    print(f"\n{prefix} #{i+1} {tag} {name}({r.ticker}) — {r.total_score}分 @{r.price:.2f}{rt_tag}")
    if r.pa_details:
        pa_items = [f"{k}:{v:+d}" for k, v in r.pa_details.items() if v != 0]
        print(f"    PA: {' | '.join(pa_items)}")
    print(f"    市场:{r.market_state} | K线:{r.signal_bar_quality}({r.signal_bar_type}) | H{r.h_count}/L{r.l_count} | 楔形:{r.wedge_type or '无'} | SR:{r.sr_confluence}重")
    if r.bonus_details:
        bonus_items = [f"{k}=+{v}" for k, v in r.bonus_details.items() if v and v is not False]
        if bonus_items: print(f"    强化: {' '.join(bonus_items)}")
    if r.entry_signals: print(f"    入场信号: {', '.join(r.entry_signals[:4])}")
    if r.forbidden_hits: print(f"    禁区: {r.forbidden_hits}")
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

# ── 600396 detailed deep dive ──
if r396:
    print(f"\n{'='*65}")
    print(f"  >>> 华电辽能 600396 深度分析 <<<")
    print(f"{'='*65}")
    print(f"  评分: {r396.total_score} | 仓位: {r396.position}")

    # Get detailed K-line data
    df = _load_cache('600396')
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values

    # Key levels
    ma5 = r396.price / (1 + float(closes[-5:].mean())/r396.price - 1) if len(closes) >= 5 else 0
    # Better way to compute MA from cache data
    close_series = pd.Series(closes)
    _ma5 = close_series.rolling(5).mean().values[-1]
    _ma10 = close_series.rolling(10).mean().values[-1]
    _ma20 = close_series.rolling(20).mean().values[-1]
    _ma60 = close_series.rolling(60).mean().values[-1] if len(close_series) >= 60 else 0

    # ATR
    df['tr'] = df.apply(lambda r: max(r['high']-r['low'], abs(r['high']-pd.Series(closes).shift(1).fillna(r['close'])), abs(r['low']-pd.Series(closes).shift(1).fillna(r['close']))), axis=1)
    _atr5 = df['tr'].tail(5).mean()
    _atr14 = df['tr'].tail(14).mean()

    # Recent
    recent = df.tail(5)
    print(f"\n  近5日K线:")
    for _, row in recent.iterrows():
        print(f"    {row.name} O:{row['open']:.2f} H:{row['high']:.2f} L:{row['low']:.2f} C:{row['close']:.2f} V:{row['volume']:.0f}")

    print(f"\n  均线: MA5={_ma5:.2f} MA10={_ma10:.2f} MA20={_ma20:.2f} MA60={_ma60:.2f}")
    print(f"  现价 vs MA20: {(r396.price/_ma20-1)*100:+.1f}%")
    print(f"  ATR5={_atr5:.2f} ATR14={_atr14:.2f}")

    # Price action assessment
    if _ma5 > _ma10 > _ma20 and r396.price > _ma20:
        trend_assessment = "多头排列 — 趋势确认"
    elif r396.price > _ma20:
        trend_assessment = "站上MA20 — 反弹进行中"
    elif r396.price > _ma5:
        trend_assessment = "站上MA5 — 短线止跌"
    else:
        trend_assessment = "空头排列 — 等待确认"

    print(f"  趋势评估: {trend_assessment}")

    # Al Brooks signals
    last_3_closes = closes[-3:]
    last_3_opens = df['open'].values[-3:]
    print(f"\n  最近3日收盘: {last_3_closes}")
    print(f"  PA评分明细: {r396.pa_details}")

    print(f"\n  入场建议:")
    if r396.total_score >= 54:
        print(f"    → 评分达标，可以入场（信号K线确认后）")
    else:
        print(f"    → 评分{',已达半仓标准' if r396.total_score >= 54 else '不足(<54)，观察等待'}")

# ── Save JSON ──
output = {
    "date": datetime.now().strftime("%Y-%m-%d"),
    "sector": "电力(火电+水电+核电+绿电+电网)",
    "pool_size": len(tickers),
    "cached": len(cached),
    "scored": len(results),
    "passed": len(passed),
    "vetoed": len(vetoed),
    "rankings": [
        {
            "rank": i+1, "ticker": r.ticker,
            "name": getattr(r, 'rt_name', '') or r.name,
            "price": r.rt_price if hasattr(r, 'rt_price') else r.price,
            "change_pct": r.rt_change_pct if hasattr(r, 'rt_change_pct') else 0,
            "score": r.total_score, "position": r.position,
            "market_state": r.market_state,
            "signal_bar": r.signal_bar_quality, "signal_type": r.signal_bar_type,
            "h_count": r.h_count, "l_count": r.l_count,
            "wedge": r.wedge_type, "sr": r.sr_confluence,
            "entry_signals": r.entry_signals,
            "forbidden_hits": r.forbidden_hits,
        } for i, r in enumerate(passed[:20])
    ],
    "focus_600396": {
        "ticker": "600396", "name": "华电辽能",
        "score": r396.total_score if r396 else 0,
        "position": r396.position if r396 else 0,
    }
}
out_path = os.path.join(OUT_DIR, f"power_sector_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n  Saved: {out_path}")
