"""焦煤板块 Top 5 趋势筛选 — 趋势+换手综合评分"""
import noproxy
import sys, os, json, time
from datetime import datetime
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))

from data_cache import _load_cache, update_one
from screener import compute_indicators, load_discipline_state
from scoring import TristScorer, build_market_context
from entry_signals import detect_entry_signals
from direct_api import _get_tencent_quote

# ── 焦煤板块定义 ──
# B06煤炭开采和洗选业 + C25中焦煤相关
COKE_STOCKS = {
    # B06 煤炭开采和洗选业 (core coal mining)
    '600121': '郑州煤电', '600123': '兰花科创', '600188': '兖矿能源',
    '600348': '华阳股份', '600395': '盘江股份', '600403': '大有能源',
    '600508': '上海能源', '600546': '山煤国际', '600758': '辽宁能源',
    '600925': '苏能股份', '600971': '恒源煤电', '600985': '淮北矿业',
    '601001': '晋控煤业', '601088': '中国神华', '601101': '昊华能源',
    '601225': '陕西煤业', '601666': '平煤股份', '601699': '潞安环能',
    '601898': '中煤能源', '601918': '新集能源', '000552': '甘肃能化',
    '000571': '新大洲A', '000937': '冀中能源', '000983': '山西焦煤',
    '002128': '电投能源',
    # C25 焦化/煤化工 (coking/coal chemical)
    '600740': '山西焦化', '600997': '开滦股份', '600792': '云煤能源',
    '601011': '宝泰隆', '601015': '陕西黑猫', '000723': '美锦能源',
    '603113': '金能科技',
}
print(f"焦煤板块: {len(COKE_STOCKS)} stocks")
print(f"Time: {datetime.now():%Y-%m-%d %H:%M}")
print("=" * 60)

# ── Step 1: Ensure K-line data ──
print("\n[1] Loading K-line data...")
import baostock as bs
bs.login()

klines = {}
for ticker in COKE_STOCKS:
    try:
        df = update_one(ticker, start_date="2026-03-01", bs_session=bs)
        if len(df) >= 20:
            klines[ticker] = df
    except Exception as e:
        pass

bs.logout()
print(f"  Loaded: {len(klines)} stocks with >=20 days data")

# ── Step 2: Real-time quotes from Tencent ──
print("\n[2] Fetching real-time quotes (Tencent)...")
quotes = {}
for ticker in list(klines.keys()):
    try:
        q = _get_tencent_quote(ticker)
        if q and q.get('price', 0) > 0:
            quotes[ticker] = q
    except:
        pass
    time.sleep(0.12)
print(f"  Got: {len(quotes)} real-time quotes")

# ── Step 3: Market context ──
print("\n[3] Building market context...")
ctx = build_market_context()
print(f"  Limit-up: {ctx.get('limit_up_count','?')} | Max chain: {ctx.get('max_chain_height','?')}")

# ── Step 4: Full PA scoring ──
print("\n[4] PA Scoring...")
results = []
for ticker, kdf in klines.items():
    try:
        ind = compute_indicators(kdf)
        rt = quotes.get(ticker, {})
        price = rt.get('price', 0) if rt.get('price', 0) > 0 else float(kdf['close'].values[-1])
        ind['price'] = price
        ind['name'] = COKE_STOCKS.get(ticker, '')
        if rt:
            ind['vol_ratio'] = rt.get('vol_ratio', ind.get('vol_ratio', 1))
            ind['today_ret'] = rt.get('change_pct', 0) / 100 if rt.get('change_pct', 0) else ind.get('today_ret', 0)
            ind['turnover'] = rt.get('turnover', ind.get('turnover', 0))
            ind['amount'] = rt.get('amount', 0)

        scorer = TristScorer(market_context=ctx)
        r = scorer.score(ind, {})

        if r.vetoed:
            continue

        ma5 = ind.get('ma5', 0); ma10 = ind.get('ma10', 0); ma20 = ind.get('ma20', 0)
        ma_bull = ma5 > ma10 > ma20 > 0
        price_above_ma5 = r.price > ma5 if ma5 > 0 else False

        # Trend strength: 5d & 20d momentum
        ret_5d = ind.get('ret_5d', 0)
        ret_20d = ind.get('ret_20d', 0)

        results.append({
            "ticker": ticker, "name": COKE_STOCKS.get(ticker, r.name),
            "price": r.price,
            "score": r.total_score, "pa_score": r.pa_score, "bonus_score": r.bonus_score,
            "ma_bull": ma_bull, "ma5": round(ma5,2), "ma10": round(ma10,2), "ma20": round(ma20,2),
            "price_above_ma5": price_above_ma5,
            "ret_5d": round(ret_5d*100, 2) if ret_5d else 0,
            "ret_20d": round(ret_20d*100, 2) if ret_20d else 0,
            "turnover": ind.get('turnover', 0),
            "vol_ratio": ind.get('vol_ratio', 1),
            "amount": ind.get('amount', 0),
            "market_state": r.market_state,
            "signal_quality": r.signal_bar_quality,
            "signal_type": r.signal_bar_type,
            "h_count": r.h_count, "l_count": r.l_count,
            "wedge": r.wedge_type, "sr": r.sr_confluence,
            "pa_details": r.pa_details, "bonus_details": r.bonus_details,
            "entry_signals": r.entry_signals, "position": r.position,
        })
    except Exception as e:
        continue

print(f"  Scored: {len(results)} stocks")

# ── Step 5: Rank by composite score (trend + turnover weight) ──
print("\n[5] Ranking by Trend+Turnover Composite...")

# Composite: 60% PA score + 20% turnover rank + 20% trend momentum
if results:
    max_turnover = max(r['turnover'] for r in results) if results else 1
    max_ret_20d = max(r['ret_20d'] for r in results) if results else 1
    min_ret_20d = min(r['ret_20d'] for r in results) if results else 0

    for r in results:
        # Normalize components to 0-100
        turnover_norm = (r['turnover'] / max_turnover * 100) if max_turnover > 0 else 0
        ret_range = max_ret_20d - min_ret_20d
        ret_norm = ((r['ret_20d'] - min_ret_20d) / ret_range * 100) if ret_range > 0 else 50
        # Composite
        r['composite'] = round(
            r['score'] * 0.55 +     # PA score weight
            turnover_norm * 0.25 +   # turnover weight
            ret_norm * 0.20,         # trend momentum weight
            1
        )

    # Sort by composite
    results.sort(key=lambda x: x['composite'], reverse=True)
    top5 = results[:5]

    # ── Output ──
    print(f"\n{'='*90}")
    print(f"  焦煤板块 Top 5 — 趋势+换手综合排名")
    print(f"  {datetime.now():%Y-%m-%d %H:%M}")
    print(f"{'='*90}")
    print(f"{'Rank':<5} {'Code':<8} {'Name':<10} {'Price':<8} {'PA':<5} {'Bonus':<5} {'Score':<6} {'Composite':<9} {'MA Bull':<8} {'Turnover':<10} {'5d%':<8} {'20d%':<8} {'Position':<10}")
    print(f"{'-'*90}")

    for i, r in enumerate(top5):
        ma_str = "Y" if r['ma_bull'] else "N"
        pos_str = r['position']
        print(f"{i+1:<5} {r['ticker']:<8} {r['name']:<10} {r['price']:<8.2f} {r['pa_score']:<5} {r['bonus_score']:<5} {r['score']:<6} {r['composite']:<9} {ma_str:<8} {r['turnover']:<10.2f} {r['ret_5d']:<8.1f} {r['ret_20d']:<8.1f} {pos_str:<10}")

    # ── Detailed output for top 5 ──
    print(f"\n{'='*90}")
    print(f"  Top 5 详细PA评分明细")
    print(f"{'='*90}")

    for i, r in enumerate(top5):
        print(f"\n{'─'*70}")
        print(f"  #{i+1} {r['name']} ({r['ticker']}) — 价格:{r['price']:.2f} | 综合:{r['composite']} | PA:{r['score']}")
        print(f"  MA: {r['ma5']:.2f} > {r['ma10']:.2f} > {r['ma20']:.2f} | Bull={r['ma_bull']}")
        print(f"  换手率:{r['turnover']:.2f}% | 量比:{r['vol_ratio']:.2f} | 5d:{r['ret_5d']:.1f}% | 20d:{r['ret_20d']:.1f}%")
        print(f"  市场状态:{r['market_state']} | 信号K线:{r['signal_quality']}({r['signal_type']})")
        print(f"  H/L计数:{r['h_count']}/{r['l_count']} | 楔形:{r['wedge']} | SR共振:{r['sr']}")
        print(f"  仓位建议:{r['position']}")

        # PA details
        pa = r.get('pa_details', {})
        if pa:
            print(f"  PA明细: ", end="")
            pa_items = []
            for k, v in pa.items():
                if isinstance(v, tuple) and len(v) >= 2:
                    pa_items.append(f"{k}={v[0]}/{v[1]}")
            print(", ".join(pa_items))

        # Bonus details
        bonus = r.get('bonus_details', [])
        if bonus:
            print(f"  强化加分: {bonus}")

        # Entry signals
        sigs = r.get('entry_signals', [])
        if sigs:
            print(f"  入场信号: {sigs}")

    # ── Save results ──
    out_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"coke_top5_{datetime.now():%Y%m%d_%H%M}.json")
    # Convert numpy types for JSON serialization
    json_results = []
    for r in results:
        jr = {}
        for k, v in r.items():
            if isinstance(v, (np.integer,)):
                jr[k] = int(v)
            elif isinstance(v, (np.floating,)):
                jr[k] = float(v)
            elif isinstance(v, (np.ndarray,)):
                jr[k] = v.tolist()
            else:
                jr[k] = v
        json_results.append(jr)
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(json_results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to: {out_file}")

    # Print all results for reference
    print(f"\n{'='*90}")
    print(f"  全部 {len(results)} 只焦煤板块股票排名")
    print(f"{'='*90}")
    print(f"{'Rank':<5} {'Code':<8} {'Name':<10} {'Price':<8} {'Score':<6} {'Composite':<9} {'MA Bull':<8} {'Turnover':<10} {'20d%':<8}")
    for i, r in enumerate(results):
        ma_str = "Y" if r['ma_bull'] else "N"
        print(f"{i+1:<5} {r['ticker']:<8} {r['name']:<10} {r['price']:<8.2f} {r['score']:<6} {r['composite']:<9} {ma_str:<8} {r['turnover']:<10.2f} {r['ret_20d']:<8.1f}")

else:
    print("No stocks scored!")