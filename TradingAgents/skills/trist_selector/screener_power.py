"""Electric Power Sector Top 5 Scanner"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
from datetime import datetime
from screener import load_stock_list, pull_kline_batch, compute_indicators, screen_single

# ── Power sector stock name keywords ──
POWER_KEYWORDS = [
    "电力", "电", "发电", "水电", "火电", "核电", "风电", "光伏",
    "能源", "热电", "电网", "供电", "节能", "绿电", "新能源",
    "输电", "配电", "变电", "蓄能", "抽水"
]

def is_power_stock(name):
    """Check if stock name suggests power sector."""
    for kw in POWER_KEYWORDS:
        if kw in name:
            return True
    return False

def run_power_scan(output_top_n=5):
    print("=" * 60)
    print(f"  Electric Power Sector Top 5")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # Step 1: Load all stocks
    df = load_stock_list()
    print(f"\n[Step 1] Loaded {len(df)} stocks")

    # Filter by name
    if "name" in df.columns:
        df = df[df["name"].apply(is_power_stock)]
        print(f"  After power sector filter: {len(df)} stocks")
    else:
        print("  ERROR: no name column")
        return

    # Exclude ST
    df = df[~df["name"].str.contains("ST|退", na=False)]
    print(f"  After ST exclusion: {len(df)}")

    tickers = df["ticker"].tolist()
    if not tickers:
        print("  No power stocks found!")
        return

    # Show candidates
    ticker_to_name = dict(zip(df["ticker"], df["name"]))
    print(f"  Candidates: {', '.join([f'{t}({ticker_to_name[t]})' for t in tickers[:20]])}...")

    # Step 2: Pull K-lines
    print(f"\n[Step 2] Pulling K-lines for {len(tickers)} power stocks...")
    klines = pull_kline_batch(tickers)

    # Step 3: Trend + MA alignment filter
    print(f"\n[Step 3] Filtering for MA alignment + trend...")
    candidates = []
    for ticker, kline_df in klines.items():
        if len(kline_df) < 30:
            continue
        try:
            ind = compute_indicators(kline_df)
            ma5 = ind.get("ma5", 0)
            ma10 = ind.get("ma10", 0)
            ma20 = ind.get("ma20", 0)
            price = float(kline_df["close"].values[-1])

            if ma5 > ma10 > ma20 > 0 and price > ma5:
                # Count trend days
                c_arr = kline_df["close"].values
                td = 0
                for i in range(max(0, len(c_arr)-20), len(c_arr)):
                    if i >= 20:
                        m5 = np.mean(c_arr[i-4:i+1])
                        m10 = np.mean(c_arr[i-9:i+1])
                        m20 = np.mean(c_arr[i-19:i+1])
                        if m5 > m10 > m20 > 0: td += 1
                candidates.append((ticker, ma5, ma10, ma20, price, td))
        except Exception:
            continue

    candidates.sort(key=lambda x: x[5], reverse=True)
    print(f"  MA aligned: {len(candidates)}/{len(klines)}")

    if not candidates:
        print("\n  No MA-aligned power stocks found! Showing ALL power stocks with scores:")
        candidates = []
        for ticker, kline_df in klines.items():
            if len(kline_df) < 20: continue
            price = float(kline_df["close"].values[-1])
            ind = compute_indicators(kline_df)
            candidates.append((ticker, ind.get("ma5",0), ind.get("ma10",0),
                              ind.get("ma20",0), price, 0))

    # Step 4: Score
    print(f"\n[Step 4] Scoring {len(candidates)} power stocks...")
    results = []
    for ticker, ma5, ma10, ma20, price, td in candidates:
        name = ticker_to_name.get(ticker, "")
        kline_df = klines.get(ticker)
        if kline_df is None: continue
        r = screen_single(ticker, name, price, kline_df)
        r.ma5 = ma5; r.ma10 = ma10; r.ma20 = ma20; r.trend_days = td
        results.append(r)

    # Sort
    passed = [r for r in results if not r.vetoed and r.total_score >= 54]
    below = [r for r in results if not r.vetoed and r.total_score < 54]
    vetoed = [r for r in results if r.vetoed]
    passed.sort(key=lambda x: x.total_score, reverse=True)
    below.sort(key=lambda x: x.total_score, reverse=True)

    print(f"\n{'='*60}")
    print(f"  POWER SECTOR RESULTS")
    print(f"  >=54分(半仓+): {len(passed)} | 观察: {len(below)} | 禁区: {len(vetoed)}")
    print(f"{'='*60}")

    # Top 5 from passed or below
    display = passed[:output_top_n] if passed else below[:output_top_n]
    pos_label = {"full": "FULL", "half": "HALF", "observe": "OBS"}

    for i, r in enumerate(display):
        print(f"\n  #{i+1} [{pos_label.get(r.position,'?')}] {r.name}({r.ticker}) — {r.total_score}分 @{r.price}")
        print(f"    MA: MA5({getattr(r,'ma5',0):.2f})>MA10({getattr(r,'ma10',0):.2f})>MA20({getattr(r,'ma20',0):.2f}) "
              f"| 趋势持续{getattr(r,'trend_days',0)}日")
        if hasattr(r, 'pa_details') and r.pa_details:
            items = [f"{k}:{v:+d}" for k, v in sorted(r.pa_details.items())]
            print(f"    PA: {' | '.join(items)}")
        print(f"    Mkt:{r.market_state} | Sig:{r.signal_bar_quality}({r.signal_bar_type}) "
              f"| H{r.h_count}/L{r.l_count} | Wedge:{r.wedge_type} | SR:{r.sr_confluence}重")
        if r.entry_signals:
            print(f"    Entry: {', '.join(r.entry_signals[:3])}")

    # Also show any >=54 stocks not in top 5
    if len(passed) > output_top_n:
        print(f"\n  Also passed (>=54):")
        for r in passed[output_top_n:]:
            print(f"    {r.name}({r.ticker}) {r.total_score}分 @{r.price} "
                  f"| MA5({getattr(r,'ma5',0):.2f})>MA10({getattr(r,'ma10',0):.2f})")

    # Show below threshold with highest scores
    if below and not display:
        pass  # already displayed
    elif below and len(passed) < output_top_n:
        print(f"\n  Below 54 but best in sector:")
        for r in below[:output_top_n - len(passed)]:
            print(f"    {r.name}({r.ticker}) {r.total_score}分 @{r.price} "
                  f"| MA5({getattr(r,'ma5',0):.2f})>MA10({getattr(r,'ma10',0):.2f})")

    # Save
    import json
    out_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(out_dir, exist_ok=True)
    out = {"scan_date": datetime.now().strftime("%Y-%m-%d"), "sector": "power",
           "summary": {"passed": len(passed), "below": len(below), "vetoed": len(vetoed)},
           "top5": []}
    for r in display:
        out["top5"].append({"ticker": r.ticker, "name": r.name, "score": r.total_score,
                           "price": r.price, "position": r.position})
    path = os.path.join(out_dir, f"power_{datetime.now().strftime('%Y%m%d')}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved: {path}")


if __name__ == "__main__":
    run_power_scan()
