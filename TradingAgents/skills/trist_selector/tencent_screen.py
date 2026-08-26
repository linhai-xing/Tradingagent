"""
Emergency screener: uses cached K-lines + Tencent real-time quotes.
Runs when eastmoney/akshare APIs are blocked.

Flow:
  1. Load all cached tickers (1985 stocks)
  2. Compute indicators from cached K-lines
  3. Pre-filter: MA5 > MA10 > MA20, price > MA20, not limit-down
  4. Sort by 5d momentum, take top 300
  5. Fetch Tencent real-time quotes (with names) for candidates
  6. Run full PA scoring (PA1-PA13 + B1-B9 + external)
  7. Output top 5 (no veto, score >= 54)
"""
import noproxy
import os, sys, json, time
from datetime import datetime
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

from direct_api import _get_tencent_quote
from data_cache import _load_cache
from screener import compute_indicators, load_discipline_state
from scoring import TristScorer, build_market_context
from entry_signals import detect_entry_signals, get_entry_recommendation

CACHE_DIR = os.path.join(os.path.dirname(__file__), "data_cache")
OUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUT_DIR, exist_ok=True)

# ── Config ──
TOP_N_MOMENTUM = 300   # top by 5d momentum after trend filter
SCORE_COUNT = 200       # max stocks to fully score
TENCENT_DELAY = 0.12    # seconds between Tencent API calls

print("=" * 60)
print(f"  Trist Selector v4.0 — Tencent Fallback Screen")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"  Data: {len([f for f in os.listdir(CACHE_DIR) if f.endswith('.csv')])} cached K-lines + Tencent实时价格")
print("=" * 60)

# ── Step 1: Load cached tickers ──
tickers = sorted([f.replace('.csv', '') for f in os.listdir(CACHE_DIR) if f.endswith('.csv')])
print(f"\n[1] Cached tickers: {len(tickers)}")

# ── Step 2: Compute indicators & pre-filter ──
print(f"[2] Computing indicators & trend filtering...")
trending = []
veto_count = 0
no_data_count = 0

for i, t in enumerate(tickers):
    df = _load_cache(t)
    if len(df) < 20:
        no_data_count += 1
        continue

    # Exclude STAR board (688xxx) — too volatile for this screener
    if t.startswith('688'):
        continue

    ind = compute_indicators(df)
    if not ind:
        no_data_count += 1
        continue

    # Trend filter using the SAME MAs that scoring uses
    ma5 = ind.get('ma5', 0)
    ma10 = ind.get('ma10', 0)
    ma20 = ind.get('ma20', 0)
    price = float(df["close"].values[-1])

    if not (ma5 > ma10 > ma20 and price > ma20):
        veto_count += 1
        continue

    # Additional sanity: not limit-down today
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

    if (i + 1) % 500 == 0:
        print(f"  Processed {i+1}/{len(tickers)}, trending: {len(trending)}")

print(f"  Trending (MA aligned): {len(trending)} | No data: {no_data_count} | Filtered out: {veto_count}")

# ── Step 3: Sort by 5d momentum ──
trending.sort(key=lambda x: x['ret_5d'], reverse=True)
candidates = trending[:TOP_N_MOMENTUM]
print(f"[3] Top {len(candidates)} by 5d momentum (range: {candidates[0]['ret_5d']:.1%} ~ {candidates[-1]['ret_5d']:.1%})")

# ── Step 4: Fetch Tencent real-time quotes ──
print(f"[4] Fetching Tencent实时价格+名称 for {len(candidates)} stocks...")
valid = []
for i, stock in enumerate(candidates):
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
            # Keep the stock with cached price but mark it
            stock['rt_price'] = stock['cached_price']
            stock['rt_name'] = ''
            stock['rt_change_pct'] = 0
            valid.append(stock)
    except Exception:
        stock['rt_price'] = stock['cached_price']
        stock['rt_name'] = ''
        stock['rt_change_pct'] = 0
        valid.append(stock)

    if (i + 1) % 50 == 0:
        print(f"  Quotes: {i+1}/{len(candidates)}")
    time.sleep(TENCENT_DELAY)

print(f"  Valid quotes: {len([s for s in valid if s.get('rt_name')])} with names")

# ── Step 5: Run full PA scoring ──
score_n = min(SCORE_COUNT, len(valid))
print(f"[5] Full PA scoring for {score_n} stocks...")

# Build market context once (may fail gracefully)
market_ctx = build_market_context()
print(f"  Market: limit_up={market_ctx.get('limit_up_count', '?')}, "
      f"max_chain={market_ctx.get('max_chain_height', '?')}")
scorer = TristScorer(market_context=market_ctx)
discipline_state = load_discipline_state()

results = []
for i, stock in enumerate(valid[:score_n]):
    t = stock['ticker']
    ind = stock['indicators'].copy()

    # Update with Tencent real-time data
    ind['ticker'] = t
    ind['name'] = stock.get('rt_name', f'股票{t}')
    ind['price'] = stock.get('rt_price', stock['cached_price'])
    ind['sector'] = ''
    ind['is_realtime'] = True

    # Override turnover with Tencent if available (more accurate)
    if stock.get('rt_turnover', 0) > 0:
        ind['avg_turnover_5d'] = stock['rt_turnover']
    if stock.get('rt_change_pct', 0) != 0:
        ind['today_ret'] = stock['rt_change_pct'] / 100

    result = scorer.score(ind, {})

    # Entry signals from full K-line
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

    if (i + 1) % 50 == 0:
        print(f"  Scored: {i+1}/{score_n}")

# ── Step 6: Filter, sort, output ──
passed = [r for r in results if not r.vetoed and r.total_score >= 54]
vetoed = [r for r in results if r.vetoed]
passed.sort(key=lambda x: x.total_score, reverse=True)

top5 = passed[:5]

print(f"\n{'='*60}")
print(f"  RESULTS: {len(passed)} passed, {len(vetoed)} vetoed")
print(f"{'='*60}")

pos_emoji = {"full": "\033[1;32m满仓\033[0m", "half": "\033[1;33m半仓\033[0m", "observe": "观察"}

for i, r in enumerate(top5):
    name = getattr(r, 'rt_name', '') or r.name
    rt_pct = getattr(r, 'rt_change_pct', 0)
    rt_tag = f" 实时:{rt_pct:+.1f}%" if rt_pct != 0 else ""

    print(f"\n  #{i+1} [{pos_emoji.get(r.position, '?')}] {name}({r.ticker}) — {r.total_score}分 @{r.price:.2f}{rt_tag}")
    if hasattr(r, 'pa_details') and r.pa_details:
        pa_items = []
        for k, v in r.pa_details.items():
            if v != 0:
                sign = "+" if v > 0 else ""
                pa_items.append(f"{k}:{sign}{v}")
        print(f"    PA: {' | '.join(pa_items)}")
        print(f"    市场:{r.market_state} | 信号K线:{r.signal_bar_quality}({r.signal_bar_type})")
        print(f"    H{r.h_count}/L{r.l_count} | 楔形:{r.wedge_type} | SR共振:{r.sr_confluence}重")
    if r.bonus_details:
        bonus_items = [f"{k}=+{v}" for k, v in r.bonus_details.items() if v and v is not False]
        if bonus_items:
            print(f"    强化: {' '.join(bonus_items)}")
    if r.entry_signals:
        print(f"    入场信号: {', '.join(r.entry_signals[:5])}")
    if r.forbidden_hits:
        print(f"    禁区: {r.forbidden_hits}")
    print(f"    仓位:{r.position_pct*100:.0f}% | 外围:{r.external_score}/10")

# ── Also show veto reasons summary ──
if vetoed:
    veto_reasons = {}
    for r in vetoed:
        for hit in r.forbidden_hits:
            code = hit.split(':')[0] if ':' in hit else hit[:4]
            veto_reasons[code] = veto_reasons.get(code, 0) + 1
    print(f"\n  Veto breakdown: {dict(sorted(veto_reasons.items(), key=lambda x: -x[1]))}")

# ── Save JSON ──
output = {
    "date": datetime.now().strftime("%Y-%m-%d"),
    "version": "v4.0-tencent-fallback",
    "source": "cached_kline + tencent_realtime",
    "candidates": len(candidates),
    "scored": len(results),
    "top5": [
        {
            "rank": i+1,
            "ticker": r.ticker,
            "name": getattr(r, 'rt_name', '') or r.name,
            "price": getattr(r, 'rt_price', r.price) if hasattr(r, 'rt_price') else r.price,
            "change_pct": getattr(r, 'rt_change_pct', 0) if hasattr(r, 'rt_change_pct') else 0,
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
            "pa_details": r.pa_details,
            "bonus_details": r.bonus_details,
            "entry_signals": r.entry_signals,
            "external_score": r.external_score,
            "forbidden_hits": r.forbidden_hits,
        }
        for i, r in enumerate(top5)
    ],
    "stats": {
        "total_cached": len(tickers),
        "trending": len(trending),
        "candidates_scored": len(results),
        "passed": len(passed),
        "vetoed": len(vetoed),
        "top_score": top5[0].total_score if top5 else 0,
    }
}

out_path = os.path.join(OUT_DIR, f"top5_{datetime.now().strftime('%Y%m%d')}_tencent.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n  Saved: {out_path}")
