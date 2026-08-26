"""v4.2 Trend-following Top 5 — MA bull alignment + PA score ranking for 右侧趋势交易"""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from screener import compute_indicators, cache_update_one, load_stock_list, coarse_filter
from scoring import TristScorer, build_market_context
import scoring as sc

# ── Load & filter stock pool ──
print("Loading A-share stock pool...")
df = load_stock_list()
print(f"  Input: {len(df)} stocks")
df = coarse_filter(df)
print(f"  After coarse filter: {len(df)} stocks")

# Sort by turnover and take top 300
if "turnover" in df.columns:
    df = df.sort_values("turnover", ascending=False)
tickers = df["ticker"].tolist()[:300]
names = dict(zip(df["ticker"], df.get("name", [""]*len(df)))) if "name" in df.columns else {}
print(f"  Top 300 by turnover")

# ── Market context ──
print("Building market context...")
ctx = build_market_context()
print(f"  Limit-up: {ctx.get('limit_up_count','?')} | Max chain: {ctx.get('max_chain_height','?')}")

# ── Score ──
print(f"\nScoring {len(tickers)} stocks...")
results = []
scored = vetoed = skipped = 0

for i, t in enumerate(tickers):
    try:
        kline = cache_update_one(t, start_date="2026-03-01")
        if len(kline) < 20:
            skipped += 1; continue

        ind = compute_indicators(kline)
        ind.update({"ticker": t, "name": names.get(t, ""),
                     "price": float(kline["close"].values[-1])})

        # Try realtime price override
        try:
            from direct_api import get_realtime_quote
            rt = get_realtime_quote(t)
            if rt and rt.get('price', 0) > 0:
                ind['price'] = rt['price']
                ind['vol_ratio'] = rt.get('vol_ratio', ind.get('vol_ratio', 1))
                ind['today_ret'] = rt.get('change_pct', 0) / 100
        except: pass

        scorer = TristScorer(market_context=ctx)
        r = scorer.score(ind, {})

        if r.vetoed:
            vetoed += 1; continue

        ma5 = ind.get("ma5", 0); ma10 = ind.get("ma10", 0); ma20 = ind.get("ma20", 0)
        ma_bull = ma5 > ma10 > ma20 > 0
        price_above_ma5 = r.price > ma5 if ma5 > 0 else False

        results.append({
            "ticker": t, "name": names.get(t, r.name), "price": r.price,
            "score": r.total_score, "pa_score": r.pa_score, "bonus_score": r.bonus_score,
            "ma_bull": ma_bull, "ma5": round(ma5,2), "ma10": round(ma10,2), "ma20": round(ma20,2),
            "price_above_ma5": price_above_ma5,
            "market_state": r.market_state, "signal_quality": r.signal_bar_quality,
            "signal_type": r.signal_bar_type, "h_count": r.h_count, "l_count": r.l_count,
            "wedge": r.wedge_type, "sr": r.sr_confluence,
            "pa_details": r.pa_details, "bonus_details": r.bonus_details,
            "entry_signals": r.entry_signals, "position": r.position,
        })
        scored += 1
    except:
        skipped += 1; continue

    if (i+1) % 50 == 0:
        print(f"  Progress: {i+1}/{len(tickers)} | scored:{scored} vetoed:{vetoed}")

print(f"\nDone. Scored:{scored} Vetoed:{vetoed} Skipped:{skipped}")

# ── Filter & Rank ──
tier1 = [r for r in results if r["ma_bull"]]
tier1.sort(key=lambda x: x["score"], reverse=True)

# Also score-only rank
all_passed = sorted(results, key=lambda x: x["score"], reverse=True)

# ── Display ──
def print_stock(i, r, label=""):
    print(f"\n  {'─'*60}")
    print(f"  #{i+1} {r['ticker']} {r['name']} @ {r['price']:.2f} {label}")
    print(f"  Score: {r['score']}/100 (PA:{r['pa_score']}/90 + B:{r['bonus_score']}/10)")
    print(f"  MA5:{r['ma5']} MA10:{r['ma10']} MA20:{r['ma20']} | 多头:{r['ma_bull']} | >MA5:{r['price_above_ma5']}")
    print(f"  Market:{r['market_state']} | Signal:{r['signal_quality']}({r['signal_type']})")
    print(f"  H{r['h_count']}/L{r['l_count']} | Wedge:{r['wedge']} | SR:{r['sr']}重")
    if r['pa_details']:
        items = [f"{k}:{v:+d}" for k,v in sorted(r['pa_details'].items()) if v != 0]
        print(f"  PA: {' | '.join(items)}")
    if r['bonus_details']:
        hits = [k for k,v in r['bonus_details'].items() if v]
        if hits: print(f"  Bonus: {', '.join(hits)}")
    if r['entry_signals']:
        print(f"  Entry: {', '.join(r['entry_signals'][:5])}")

print(f"\n{'='*65}")
print(f"  [BULL] TOP 5 -- MA Bull Alignment (MA5>MA10>MA20) [Right-Side Trend]")
print(f"  Found: {len(tier1)} stocks with full bull alignment")
print(f"{'='*65}")

for i, r in enumerate(tier1[:5]):
    print_stock(i, r, ">>BULL<<")

if not tier1:
    print("\n  WARNING: No MA-bull stocks found in top 300 turnover!")

print(f"\n{'='*65}")
print(f"  [ALL] TOP 5 -- Overall Score (all MA states)")
print(f"{'='*65}")

for i, r in enumerate(all_passed[:5]):
    ma_label = "BULL" if r["ma_bull"] else ("partial" if r["ma5"] > r["ma10"] else "bearish")
    print_stock(i, r, ma_label)

print(f"\n{'='*65}")
print(f"  Summary: {len(tier1)} bull-aligned / {scored} scored")
if tier1:
    print(f"  Best bull: {tier1[0]['ticker']} {tier1[0]['name']} — {tier1[0]['score']}/100")
if all_passed:
    print(f"  Best overall: {all_passed[0]['ticker']} {all_passed[0]['name']} — {all_passed[0]['score']}/100")
print(f"{'='*65}")
