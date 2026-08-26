"""Bypass all vetos and score"""
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
from screener import compute_indicators, cache_update_one
from scoring import TristScorer, build_market_context
import scoring as sc

orig_score = sc.TristScorer.score
def patched(self, data, sector=None, discipline=None):
    orig_ma5 = data.get("ma5",0); orig_ma10 = data.get("ma10",0)
    if orig_ma5 < orig_ma10 and orig_ma10 > 0: data["ma5"] = orig_ma10 + 0.01
    if data.get("pre_5d_return",0) > 0.20: data["pre_5d_return"] = 0.15
    if data.get("prev_day_limit_up", False): data["prev_day_limit_up"] = False
    result = orig_score(self, data, sector, discipline)
    data["ma5"] = orig_ma5; data["ma10"] = orig_ma10
    if hasattr(result, "forbidden_hits") and result.forbidden_hits:
        result.forbidden_hits = []; result.vetoed = False
    return result
sc.TristScorer.score = patched

ctx = build_market_context()

for ticker, name in [("603002", "宏和科技"), ("600396", "华电辽能")]:
    kline = cache_update_one(ticker, start_date="2026-01-01")
    ind = compute_indicators(kline)
    ind["ticker"] = ticker; ind["name"] = name
    ind["price"] = float(kline["close"].values[-1])
    r = TristScorer(market_context=ctx).score(ind, {})
    ma5 = ind.get("ma5",0); ma10 = ind.get("ma10",0); ma20 = ind.get("ma20",0)
    print(f"\n{'='*50}")
    print(f'{name} {ticker} @ {r.price:.2f}')
    print(f'MA5:{ma5:.2f} MA10:{ma10:.2f} MA20:{ma20:.2f} 多头={ma5>ma10>ma20}')
    print(f'Score: {r.total_score}/100 (选股:{r.pa_score}/70 强化:{r.bonus_score}/20 外围:{r.external_score}/10)')
    print(f'Position: {r.position}')
    if r.pa_details:
        items = [f'{k}:{v:+d}' for k,v in sorted(r.pa_details.items())]
        sep = " | "
        print(f"PA: {sep.join(items)}")
    print(f'Mkt:{r.market_state} Sig:{r.signal_bar_quality}({r.signal_bar_type})')
    print(f'H{r.h_count}/L{r.l_count} Wedge:{r.wedge_type} SR:{r.sr_confluence}重')
    if r.entry_signals: print("Entry: " + ", ".join(r.entry_signals[:5]))
    if hasattr(r,'bonus_details'):
        hits = [k for k,v in r.bonus_details.items() if v]
        if hits: print("Bonus: " + ", ".join(hits))
