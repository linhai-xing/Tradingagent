"""Bypass X9 veto — properly patch at the source"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from screener import compute_indicators, cache_update_one
from scoring import TristScorer, build_market_context, ScoreResult
import scoring as sc
import numpy as np

# ── Patch: make _check_forbidden skip X9 by temporarily faking MA values ──
original_score = sc.TristScorer.score

def patched_score(self, stock_data, sector_data=None, discipline_state=None):
    # Save original MA values
    orig_ma5 = stock_data.get("ma5", 0)
    orig_ma10 = stock_data.get("ma10", 0)
    # Fake MA5 > MA10 so X9 never triggers
    if orig_ma5 < orig_ma10 and orig_ma10 > 0:
        stock_data["ma5"] = orig_ma10 + 0.01  # ma5 just above ma10
    else:
        stock_data["ma5"] = orig_ma5
        stock_data["ma10"] = orig_ma10

    result = original_score(self, stock_data, sector_data, discipline_state)

    # Restore original MA values for display accuracy
    stock_data["ma5"] = orig_ma5
    stock_data["ma10"] = orig_ma10

    # Remove X9 and X12 from forbidden_hits
    if hasattr(result, "forbidden_hits") and result.forbidden_hits:
        non_x9x12 = [h for h in result.forbidden_hits if "X9" not in h and "X12" not in h]
        if non_x9x12:
            result.forbidden_hits = non_x9x12
        else:
            result.forbidden_hits = []
            result.vetoed = False

    return result

sc.TristScorer.score = patched_score

# ── Run ──
ctx = build_market_context()

for ticker, name in [("600206", "有研新材"), ("600667", "太极实业")]:
    kline_df = cache_update_one(ticker, start_date="2026-01-01")
    if len(kline_df) == 0:
        print(f"{ticker}: no K-line data")
        continue

    ind = compute_indicators(kline_df)
    ind["ticker"] = ticker
    ind["name"] = name
    ind["price"] = float(kline_df["close"].values[-1])

    # Also fix ma5/ma10 in indicators for scoring computation
    scorer = TristScorer(market_context=ctx)
    result = scorer.score(ind, {}, discipline_state={})

    real_ma5 = ind.get("ma5", 0)  # restored
    real_ma10 = ind.get("ma10", 0)

    print(f"\n=== {name}({ticker}) @ {result.price:.2f} [X9 bypass] ===")
    print(f"  Real MA5:{real_ma5:.2f} MA10:{real_ma10:.2f} (死叉仍在)")
    print(f"  Score: {result.total_score}/100 (PA:{result.pa_score} B:{result.bonus_score} E:{result.external_score})")
    print(f"  Vetoed: {result.vetoed} | Position: {result.position}")
    print(f"  Market: {result.market_state} | Signal: {result.signal_bar_quality}({result.signal_bar_type})")
    if result.pa_details:
        items = [f"{k}:{v:+d}" for k, v in sorted(result.pa_details.items())]
        print(f"  PA: {' | '.join(items)}")
    print(f"  H{result.h_count}/L{result.l_count} | Wedge:{result.wedge_type} | SR:{result.sr_confluence}重")
    if result.forbidden_hits:
        print(f"  Forbidden(still active): {result.forbidden_hits}")
    if result.entry_signals:
        print(f"  Entry: {', '.join(result.entry_signals[:5])}")
    if hasattr(result, "bonus_details") and result.bonus_details:
        hits = [k for k, v in result.bonus_details.items() if v]
        if hits:
            print(f"  Bonus: {', '.join(hits)}")
