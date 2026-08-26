"""
Trend-filtered Top 5 screener — only stocks with MA5 > MA10 > MA20 (bullish alignment).
Usage: python screener_trend.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
from datetime import datetime
from screener import (
    load_stock_list, coarse_filter, pull_kline_batch,
    compute_indicators, screen_single,
)

def run_trend_screen(output_top_n=5):
    print("=" * 60)
    print(f"  Trist Selector v4.0 — TREND FILTER (MA5>MA10>MA20)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # Step 1: Load + coarse filter (same as full screen)
    df = load_stock_list()
    df = coarse_filter(df)
    tickers = df["ticker"].tolist()

    if len(tickers) > 500:
        print(f"\n  [Limit] Too many candidates ({len(tickers)}), sampling top 300 by turnover...")
        df = df.sort_values("turnover", ascending=False).head(300)
        tickers = df["ticker"].tolist()

    # Step 2: Pull K-lines
    print(f"\n[Step 2] Pulling K-lines for {len(tickers)} candidates...")
    klines = pull_kline_batch(tickers)

    # Step 3: Trend filter first (MA5 > MA10 > MA20, price > MA5)
    print(f"\n[Step 3] Filtering for MA5 > MA10 > MA20 bullish alignment...")
    trend_tickers = []
    ticker_to_name = dict(zip(df["ticker"], df["name"]))

    for ticker, kline_df in klines.items():
        if len(kline_df) < 20:
            continue
        try:
            ind = compute_indicators(kline_df)
            ma5 = ind.get("ma5", 0)
            ma10 = ind.get("ma10", 0)
            ma20 = ind.get("ma20", 0)
            price = ind.get("price", 0) or float(kline_df["close"].values[-1])

            if ma5 > ma10 > ma20 > 0 and price > ma5:
                trend_tickers.append((ticker, ma5, ma10, ma20, price))
        except Exception:
            continue

    print(f"  Trend-aligned stocks: {len(trend_tickers)}/{len(klines)}")

    if not trend_tickers:
        print("\n  ⚠️  No stocks with MA5 > MA10 > MA20 found today!")
        print("  Market is likely in a broad correction / trading range.")
        return

    # Step 4: Score only trend-aligned stocks
    print(f"\n[Step 4] Scoring {len(trend_tickers)} trend-aligned stocks...")
    results = []

    for ticker, ma5, ma10, ma20, price in trend_tickers:
        name = ticker_to_name.get(ticker, "")
        kline_df = klines[ticker]
        r = screen_single(ticker, name, price, kline_df)
        # Attach MA values for display
        r.ma5 = ma5
        r.ma10 = ma10
        r.ma20 = ma20
        results.append(r)

    # Step 5: Sort and pick top N
    passed = [r for r in results if not r.vetoed and r.total_score >= 54]
    vetoed = [r for r in results if r.vetoed]
    passed.sort(key=lambda x: x.total_score, reverse=True)

    print(f"\n{'='*60}")
    print(f"  TREND RESULTS: {len(passed)} passed (≥54), {len(vetoed)} vetoed")
    print(f"  (out of {len(trend_tickers)} trend-aligned stocks)")
    print(f"{'='*60}")

    top5 = passed[:output_top_n]

    for i, r in enumerate(top5):
        pos_label = { "full": "满仓", "half": "半仓", "observe": "观察" }
        print(f"\n  #{i+1} [{pos_label.get(r.position, '?')}] {r.name}({r.ticker}) — {r.total_score}分 @{r.price}")
        print(f"    趋势: MA5({getattr(r,'ma5',0):.2f}) > MA10({getattr(r,'ma10',0):.2f}) > MA20({getattr(r,'ma20',0):.2f})")

        if hasattr(r, 'pa_details') and r.pa_details:
            items = [f"{k}:{v:+d}" for k, v in sorted(r.pa_details.items())]
            print(f"    PA: {' | '.join(items)}")

        print(f"    市场:{r.market_state} | 信号K线:{r.signal_bar_quality}({r.signal_bar_type})")
        print(f"    H{r.h_count}/L{r.l_count} | 楔形:{r.wedge_type} | SR共振:{r.sr_confluence}重")

        if hasattr(r, 'bonus_details') and r.bonus_details:
            bonus_hits = [k for k, v in r.bonus_details.items() if v]
            if bonus_hits:
                print(f"    强化: {', '.join(bonus_hits)}")

        if r.entry_signals:
            print(f"    入场: {', '.join(r.entry_signals[:4])}")

        print(f"    仓位:{r.position_pct:.0f}% | 外围:{r.external_score}/10")

    # Also show stocks < 54 but trend-aligned (for awareness)
    below = [r for r in results if not r.vetoed and r.total_score < 54]
    below.sort(key=lambda x: x.total_score, reverse=True)

    if below:
        print(f"\n  {'─'*50}")
        print(f"  [Below] Trend-aligned but <54 score ({len(below)} stocks):")
        for r in below[:5]:
            print(f"    {r.name}({r.ticker}) — {r.total_score}分 @{r.price} "
                  f"| MA5:{getattr(r,'ma5',0):.2f} > MA10:{getattr(r,'ma10',0):.2f} > MA20:{getattr(r,'ma20',0):.2f}")

    # Save
    import json
    out_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(out_dir, exist_ok=True)
    out = []
    for r in top5:
        out.append({
            "rank": out.index(r) + 1 if r in out else len(out) + 1,
            "ticker": r.ticker, "name": r.name, "score": r.total_score,
            "price": r.price, "position": r.position,
            "ma5": getattr(r, 'ma5', 0), "ma10": getattr(r, 'ma10', 0), "ma20": getattr(r, 'ma20', 0),
            "pa_details": r.pa_details, "market_state": r.market_state,
            "signal_bar": f"{r.signal_bar_quality}({r.signal_bar_type})",
            "entry_signals": r.entry_signals[:5],
        })
    path = os.path.join(out_dir, f"trend_top5_{datetime.now().strftime('%Y%m%d')}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved: {path}")


if __name__ == "__main__":
    run_trend_screen()
