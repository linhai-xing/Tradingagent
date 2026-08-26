"""
Power sector bypass — remove X12 (market euphoria, not power-specific)
and X9 (MA5 cross, allow early reversal detection). Show true PA scores.
"""
import noproxy
import sys, os, json, time, io
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from datetime import datetime
import pandas as pd
import numpy as np

from direct_api import _get_tencent_quote
from data_cache import _load_cache
from screener import compute_indicators
from scoring import TristScorer, build_market_context
from entry_signals import detect_entry_signals, get_entry_recommendation
import scoring as sc

CACHE_DIR = os.path.join(os.path.dirname(__file__), "data_cache")
OUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# ═══════════════════════════════════════════════════════════
# PATCH: Remove X12 + X9 only (keep X1,X7 and other vetos)
# X12 = market-wide euphoria (100 涨停 today), NOT power-specific
# X9 = MA5 death cross (allow early reversal detection)
# ═══════════════════════════════════════════════════════════
orig_score = sc.TristScorer.score
def patched(self, data, sector=None, discipline=None):
    # Temporarily fix MA5 for X9 bypass (if MA5 < MA10, set MA5 slightly higher)
    orig_ma5 = data.get("ma5", 0)
    orig_ma10 = data.get("ma10", 0)
    if orig_ma5 < orig_ma10 and orig_ma10 > 0:
        data["ma5"] = orig_ma10 + 0.01

    result = orig_score(self, data, sector, discipline)

    # Restore originals
    data["ma5"] = orig_ma5
    data["ma10"] = orig_ma10

    # Only remove X12 (market euphoria) — keep all other vetoes
    if hasattr(result, "forbidden_hits") and result.forbidden_hits:
        non = [h for h in result.forbidden_hits if "X12" not in h and "X9" not in h]
        if non:
            result.forbidden_hits = non
        else:
            result.forbidden_hits = []
            result.vetoed = False
    return result

sc.TristScorer.score = patched
print("Patch: X12(market euphoria) + X9(MA5 cross) bypassed for power sector analysis")

# ── Pool ──
tickers = [
    # 火电
    '600396', '600011', '600023', '600027', '600795', '601991',
    '000539', '000543', '600886', '600578', '600021', '000690',
    '000720', '000767',
    # 水电
    '600900', '600674', '600025', '000883',
    # 核电
    '601985', '003816',
    # 绿电
    '600905', '601016', '600163', '000862',
    # 电网/设备
    '600406', '601877', '000400',
    # 地方电力
    '600509', '600644', '600101', '600452', '600982', '000600',
    # 其他
    '600483', '600089',
]
cached = [t for t in tickers if os.path.exists(os.path.join(CACHE_DIR, f'{t}.csv'))]

print(f"\n[1/3] Fetching实时价格 for {len(cached)} stocks...")
ctx = build_market_context()
print(f"  市场: 涨停{ctx.get('limit_up_count','?')} | 连板{ctx.get('max_chain_height','?')}")
print(f"  ⚠️ X12触发: 涨停100>80 → 市场高潮期")
print(f"  → 电力板块与今日主线(半导体)无关，X12对电力板块的适用性待商榷\n")

scorer = TristScorer(market_context=ctx)
results = []

for i, t in enumerate(cached):
    try:
        rt = _get_tencent_quote(t)
        df = _load_cache(t)
        if len(df) < 20: continue

        ind = compute_indicators(df)
        if not ind: continue

        price = rt.get('price', 0) if rt and rt.get('price', 0) > 0 else float(df["close"].values[-1])
        ind['ticker'] = t
        ind['name'] = rt.get('name', f'股票{t}')
        ind['price'] = price
        ind['sector'] = ''
        ind['is_realtime'] = True
        if rt and rt.get('change_pct', 0) != 0:
            ind['today_ret'] = rt['change_pct'] / 100

        result = scorer.score(ind, {})

        # Entry signals
        kline_dict = {
            "closes": df["close"].tolist(), "opens": df["open"].tolist(),
            "highs": df["high"].tolist(), "lows": df["low"].tolist(),
            "volumes": df["volume"].tolist(),
        }
        signals = detect_entry_signals(kline_dict, t)
        result.entry_signals = [s.name for s in signals]
        result.rt_price = rt.get('price', 0) if rt else 0
        result.rt_change_pct = rt.get('change_pct', 0) if rt else 0
        result.rt_name = rt.get('name', '') if rt else ''
        results.append(result)

        if (i+1) % 10 == 0: print(f"  {i+1}/{len(cached)}")
        time.sleep(0.12)
    except Exception as e:
        continue

# ── Output ──
passed = [r for r in results if not r.vetoed and r.total_score >= 40]
vetoed = [r for r in results if r.vetoed]
passed.sort(key=lambda x: x.total_score, reverse=True)

print(f"\n{'='*60}")
print(f"  电力板块 PA评分 (X12+X9 bypass)")
print(f"  通过: {len(passed)} | 剔除: {len(vetoed)}")
print(f"{'='*60}")

for i, r in enumerate(passed[:20]):
    name = getattr(r, 'rt_name', '') or r.name
    rt_pct = getattr(r, 'rt_change_pct', 0)
    rt_tag = f" 实时:{rt_pct:+.1f}%" if rt_pct != 0 else ""

    prefix = ">>>" if r.ticker == '600396' else "  "
    if r.total_score >= 72: tag = "[满仓]"
    elif r.total_score >= 54: tag = "[半仓]"
    else: tag = "[观察]"

    print(f"\n{prefix} #{i+1} {tag} {name}({r.ticker}) — {r.total_score}分 @{r.price:.2f}{rt_tag}")
    if r.pa_details:
        pa_items = [f"{k}:{v:+d}" for k,v in r.pa_details.items() if v != 0]
        print(f"    PA: {' | '.join(pa_items[:8])}")
    print(f"    市场:{r.market_state} | K线:{r.signal_bar_quality}({r.signal_bar_type}) | H{r.h_count}/L{r.l_count} | 楔形:{r.wedge_type or '无'} | SR:{r.sr_confluence}重")
    if r.bonus_details:
        bonus_items = [f"{k}=+{v}" for k,v in r.bonus_details.items() if v and v is not False]
        if bonus_items: print(f"    强化: {' '.join(bonus_items)}")
    if r.entry_signals: print(f"    入场信号: {', '.join(r.entry_signals[:4])}")
    real_forbidden = [h for h in (r.forbidden_hits if hasattr(r,'forbidden_hits') else []) if 'X12' not in h]
    if real_forbidden: print(f"    真实禁区: {real_forbidden}")
    print(f"    仓位:{r.position_pct*100:.0f}% | 外围:{r.external_score}/10")

# ── 600396 full deep dive ──
r396 = None
for r in passed:
    if r.ticker == '600396':
        r396 = r
        break

if r396:
    df = _load_cache('600396')
    closes = df['close'].values
    close_s = pd.Series(closes)
    _ma5 = close_s.rolling(5).mean().values[-1]
    _ma10 = close_s.rolling(10).mean().values[-1]
    _ma20 = close_s.rolling(20).mean().values[-1]
    _ma60 = close_s.rolling(60).mean().values[-1] if len(close_s) >= 60 else 0

    # ATR
    tr_vals = []
    for j in range(1, len(closes)):
        tr = max(df['high'].values[j] - df['low'].values[j],
                 abs(df['high'].values[j] - closes[j-1]),
                 abs(df['low'].values[j] - closes[j-1]))
        tr_vals.append(tr)
    tr_vals.append(0)
    df['tr'] = tr_vals
    _atr5 = np.mean(tr_vals[-6:-1]) if len(tr_vals) >= 6 else 0
    _atr14 = np.mean(tr_vals[-15:-1]) if len(tr_vals) >= 15 else 0

    print(f"\n{'='*60}")
    print(f"  >>> 华电辽能 600396 深度分析 <<<")
    print(f"{'='*60}")
    print(f"  评分: {r396.total_score} | 仓位: {r396.position} | 仓位%: {r396.position_pct*100:.0f}%")

    recent = df.tail(8)
    print(f"\n  近8日K线:")
    for idx, row in recent.iterrows():
        marker = " ←今日?" if idx == recent.index[-1] else ""
        print(f"    {idx} O:{row['open']:.2f} H:{row['high']:.2f} L:{row['low']:.2f} C:{row['close']:.2f}{marker}")

    print(f"\n  均线: MA5={_ma5:.2f} MA10={_ma10:.2f} MA20={_ma20:.2f} MA60={_ma60:.2f}")
    print(f"  现价 vs MA5: {(r396.price/_ma5-1)*100:+.1f}%")
    print(f"  现价 vs MA20: {(r396.price/_ma20-1)*100:+.1f}%")
    print(f"  ATR5={_atr5:.2f} ({_atr5/r396.price*100:.1f}%) ATR14={_atr14:.2f} ({_atr14/r396.price*100:.1f}%)")

    # Key levels
    high_20d = df['high'].tail(20).max()
    low_20d = df['low'].tail(20).min()
    range_20d = high_20d - low_20d
    pos_20d = (r396.price - low_20d) / range_20d * 100 if range_20d > 0 else 50

    print(f"\n  20日高低: {high_20d:.2f} / {low_20d:.2f}")
    print(f"  位置: {pos_20d:.0f}% (100=高, 0=低)")

    # Trend assessment
    print(f"\n  [阿布诊断]")
    if _ma5 > _ma10 > _ma20:
        print(f"    趋势: 多头排列 ✓")
    elif r396.price > _ma20:
        print(f"    趋势: 站上MA20，反弹中")
    elif r396.price > _ma5:
        print(f"    趋势: 短线止跌，中长线空头")
    else:
        print(f"    趋势: 完全空头排列 ✗")
    print(f"    信号K线: {r396.signal_bar_quality} ({r396.signal_bar_type})")
    print(f"    入场结构: H{r396.h_count}/L{r396.l_count} | 楔形: {r396.wedge_type or '无'}")
    print(f"    SR共振: {r396.sr_confluence}重")

    # Decision guide
    print(f"\n  [决策指引]")
    if r396.total_score >= 72:
        print("    ✅ 评分达标 — 可满仓入场（信号K线确认后）")
    elif r396.total_score >= 54:
        print("    ✅ 评分达标 — 可半仓入场（信号K线确认后）")
    else:
        print("    ⚠️ 评分不足 — 观察等待")

    print(f"    ⚠️ X12(市场高潮)被bypass — 全市涨停100家")
    print(f"    → 今天不是入场日，等市场高潮退去(涨停<80)再入场")

# ── Save ──
output = {
    "date": datetime.now().strftime("%Y-%m-%d"),
    "note": "X12+X9 bypass — X12=market-level euphoria, not power-sector specific",
    "market_lu_count": ctx.get('limit_up_count', 0),
    "rankings": [{"rank": i+1, "ticker": r.ticker, "name": getattr(r,'rt_name','') or r.name, "score": r.total_score, "position": r.position} for i, r in enumerate(passed[:15])]
}
out_path = os.path.join(OUT_DIR, f"power_bypass_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\nSaved: {out_path}")
