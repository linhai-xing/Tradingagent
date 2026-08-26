"""
Signal->Entry Bar Scanner — 阿布完整入场流程扫描
1. Filter: MA5>MA10>MA20 (trend-aligned, not turnover)
2. Detect: yesterday's bar as signal bar -> today's bar as entry bar
3. Check: GATE-A (breach) + GATE-B (close confirm)
4. Score & rank
Usage: python screener_signal_entry.py
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
from entry_signals import detect_signal_bar, compute_entry_gates, SignalBarResult


def run_signal_entry_scan(output_top_n=20):
    print("=" * 60)
    print(f"  Signal->Entry Bar Scanner (阿布入场流程)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # Step 1: Load stock list (skip coarse_filter turnover filter)
    print("\n[Step 1] Loading stock list (no turnover filter)...")
    df = load_stock_list()
    # Only exclude ST, keep size + limit-down filters
    print(f"  Input: {len(df)} stocks")
    if "name" in df.columns:
        df = df[~df["name"].str.contains("ST|退", na=False)]
        print(f"  After ST exclusion: {len(df)}")
    # Float cap filter
    if "float_cap" in df.columns:
        cap_min, cap_max = 20 * 1e8, 800 * 1e8  # 20-800亿
        if df["float_cap"].median() < 1000:
            cap_min, cap_max = 20, 800
        df = df[(df["float_cap"] >= cap_min) & (df["float_cap"] <= cap_max)]
        print(f"  After cap filter (20-800亿): {len(df)}")
    # Not limit-down
    if "change_pct" in df.columns:
        df = df[df["change_pct"] > -9.5]
        print(f"  After limit-down exclusion: {len(df)}")

    tickers = df["ticker"].tolist()
    print(f"  Candidates: {len(tickers)} stocks (no turnover filter)")

    # Step 2: Pull K-lines (need enough for trend check)
    print(f"\n[Step 2] Pulling K-lines for {len(tickers)} candidates...")
    # Take top 500 by float_cap if too many (avoid timeout on full market)
    if len(tickers) > 500:
        if "float_cap" in df.columns:
            df = df.sort_values("float_cap", ascending=False).head(500)
        else:
            df = df.head(500)
        tickers = df["ticker"].tolist()
        print(f"  Sampled top 500 stocks")
    klines = pull_kline_batch(tickers)

    # Step 3: Trend filter (MA5 > MA10 > MA20, sustained for recent period)
    print(f"\n[Step 3] Filtering for MA5 > MA10 > MA20 trend alignment...")
    trend_stocks = []
    ticker_to_name = dict(zip(df["ticker"], df["name"]))

    for ticker, kline_df in klines.items():
        if len(kline_df) < 30:
            continue
        try:
            ind = compute_indicators(kline_df)
            ma5 = ind.get("ma5", 0)
            ma10 = ind.get("ma10", 0)
            ma20 = ind.get("ma20", 0)
            price = float(kline_df["close"].values[-1])

            # MA alignment at latest bar
            if not (ma5 > ma10 > ma20 > 0 and price > ma5):
                continue

            # Check how many days MA5 > MA10 > MA20 was true (trend persistence)
            closes = kline_df["close"].values
            recent_days = min(20, len(closes))
            trend_days = 0
            for i in range(len(closes) - recent_days, len(closes)):
                if i >= 20:
                    ma5_i = np.mean(closes[i-4:i+1])
                    ma10_i = np.mean(closes[i-9:i+1])
                    ma20_i = np.mean(closes[i-19:i+1])
                    if ma5_i > ma10_i > ma20_i > 0:
                        trend_days += 1

            # Require at least 5 of last 10 days in trend alignment
            if trend_days < min(5, recent_days // 2):
                continue

            trend_stocks.append((ticker, ma5, ma10, ma20, price, trend_days))
        except Exception:
            continue

    print(f"  Trend-aligned (MA5>MA10>MA20, sustained): {len(trend_stocks)}/{len(klines)}")

    if not trend_stocks:
        print("\n  No trend-aligned stocks found!")
        return

    # Step 4: Detect signal bar (yesterday = K_{-2}) + entry bar (today = K_{-1})
    print(f"\n[Step 4] Detecting signal bar (K-2) -> entry bar (K-1) pairs...")
    signal_entry_pairs = []

    for ticker, ma5, ma10, ma20, price, trend_days in trend_stocks:
        name = ticker_to_name.get(ticker, "")
        kline_df = klines[ticker]

        if len(kline_df) < 22:
            continue

        closes = kline_df["close"].values
        opens = kline_df["open"].values
        highs = kline_df["high"].values
        lows = kline_df["low"].values
        volumes = kline_df["volume"].values

        # ── Signal bar: analyze K_{-2} (second-to-last, "yesterday") ──
        # Build kline_data up to K_{-2}
        sig_kline_data = {
            "closes": closes[:-1].tolist(),  # exclude last bar
            "opens": opens[:-1].tolist(),
            "highs": highs[:-1].tolist(),
            "lows": lows[:-1].tolist(),
            "volumes": volumes[:-1].tolist(),
        }

        signal_bar = detect_signal_bar(sig_kline_data)

        if not signal_bar.is_valid:
            continue

        # ── Entry bar: check K_{-1} (last bar, "today") against signal bar ──
        # Use the full dataset but tell compute_entry_gates the signal is K_{-2}
        # We need to manually check GATE-A and GATE-B
        full_kline_data = {
            "closes": closes.tolist(),
            "opens": opens.tolist(),
            "highs": highs.tolist(),
            "lows": lows.tolist(),
            "volumes": volumes.tolist(),
        }

        # GATE-A: did entry bar (K_{-1}) break signal bar high/low?
        entry_high = highs[-1]
        entry_low = lows[-1]
        entry_open = opens[-1]
        entry_close = closes[-1]
        tick_size = 0.01

        if signal_bar.direction == "bullish":
            trigger_price = round(signal_bar.high + tick_size, 2)
            stop_loss = round(signal_bar.low - tick_size, 2)
            gate_a = entry_high >= trigger_price
            gate_b = gate_a and entry_close > entry_open and entry_close > signal_bar.high
        else:
            trigger_price = round(signal_bar.low - tick_size, 2)
            stop_loss = round(signal_bar.high + tick_size, 2)
            gate_a = entry_low <= trigger_price
            gate_b = gate_a and entry_close < entry_open and entry_close < signal_bar.low

        entry_pct = (entry_close - trigger_price) / trigger_price * 100 if trigger_price > 0 else 0

        signal_entry_pairs.append({
            "ticker": ticker,
            "name": name,
            "price": price,
            "ma5": ma5, "ma10": ma10, "ma20": ma20,
            "trend_days": trend_days,
            "sig_quality": signal_bar.quality,
            "sig_type": signal_bar.bar_type,
            "sig_direction": signal_bar.direction,
            "sig_high": signal_bar.high,
            "sig_low": signal_bar.low,
            "sig_close_pos": signal_bar.close_position,
            "sig_body_ratio": signal_bar.body_ratio,
            "sig_opposing": signal_bar.opposing_bars,
            "entry_trigger": trigger_price,
            "entry_stop": stop_loss,
            "gate_a": gate_a,
            "gate_b": gate_b,
            "entry_open": entry_open,
            "entry_high": entry_high,
            "entry_low": entry_low,
            "entry_close": entry_close,
            "entry_pct": entry_pct,
            "kline_df": kline_df,
        })

    print(f"  Valid signal bars found: {len(signal_entry_pairs)}")

    # Separate by gate status
    gate_a_passed = [p for p in signal_entry_pairs if p["gate_a"]]
    gate_b_passed = [p for p in signal_entry_pairs if p["gate_b"]]
    gate_waiting = [p for p in signal_entry_pairs if not p["gate_a"]]

    print(f"  GATE-A triggered (entry bar breached signal): {len(gate_a_passed)}")
    print(f"  GATE-B confirmed (entry bar closed confirming): {len(gate_b_passed)}")
    print(f"  Waiting for trigger: {len(gate_waiting)}")

    # Step 5: Score stocks with triggered gates
    print(f"\n[Step 5] Scoring stocks with GATE-A triggered...")
    scored_pairs = []
    for p in gate_a_passed:
        r = screen_single(p["ticker"], p["name"], p["price"], p["kline_df"])
        p["result"] = r
        p["total_score"] = r.total_score
        scored_pairs.append(p)

    # Also score gate-waiting stocks with excellent signal bars
    for p in gate_waiting:
        if p["sig_quality"] in ("excellent", "good"):
            r = screen_single(p["ticker"], p["name"], p["price"], p["kline_df"])
            p["result"] = r
            p["total_score"] = r.total_score
            scored_pairs.append(p)

    # Step 6: Output
    scored_pairs.sort(key=lambda x: (x["gate_b"], x["gate_a"], x["total_score"]), reverse=True)

    print(f"\n{'='*60}")
    print(f"  SIGNAL->ENTRY BAR RESULTS")
    print(f"  Trend-aligned: {len(trend_stocks)} | Signal bars: {len(signal_entry_pairs)}")
    print(f"  GATE-A: {len(gate_a_passed)} | GATE-B: {len(gate_b_passed)}")
    print(f"{'='*60}")

    # ── Section A: GATE-B confirmed (both triggered and closed confirming) ──
    gate_b_display = [p for p in scored_pairs if p["gate_b"]]
    gate_b_display.sort(key=lambda x: x["total_score"], reverse=True)

    print(f"\n{'─'*55}")
    print(f"  [GATE-B CONFIRMED] Entry bar close confirms direction ({len(gate_b_display)} stocks)")
    print(f"{'─'*55}")

    for i, p in enumerate(gate_b_display[:10]):
        r = p["result"]
        sig_type_cn = {
            "strong_trend": "强趋势K线", "pin_bar": "Pin Bar",
            "inside_bar": "内包线", "outside_bar": "外包线", "standard": "标准K线"
        }.get(p["sig_type"], p["sig_type"])
        dir_cn = "多" if p["sig_direction"] == "bullish" else "空"

        print(f"\n  B#{i+1} [{r.position}] {p['name']}({p['ticker']}) — {r.total_score}分 @{p['price']}")
        print(f"    信号K线: {dir_cn}头{sig_type_cn} | 质量:{p['sig_quality']} | "
              f"收盘位:{p['sig_close_pos']:.0%} | 实体:{p['sig_body_ratio']:.0%}")
        print(f"    入场触发: RMB{p['entry_trigger']} | 止损: RMB{p['entry_stop']}")
        print(f"    入场K线: O{p['entry_open']:.2f} H{p['entry_high']:.2f} "
              f"L{p['entry_low']:.2f} C{p['entry_close']:.2f}")
        print(f"    GATE-A [OK] GATE-B [OK] | 入场偏离:{p['entry_pct']:+.1f}%")
        print(f"    趋势: MA5({p['ma5']:.2f})>MA10({p['ma10']:.2f})>MA20({p['ma20']:.2f}) "
              f"| 持续{p['trend_days']}日")
        if hasattr(r, 'pa_details') and r.pa_details:
            items = [f"{k}:{v:+d}" for k, v in sorted(r.pa_details.items())]
            print(f"    PA: {' | '.join(items)}")
        print(f"    H{r.h_count}/L{r.l_count} | 楔形:{r.wedge_type} | SR:{r.sr_confluence}重")

    # ── Section B: GATE-A only (triggered but not confirmed) ──
    gate_a_only = [p for p in scored_pairs if p["gate_a"] and not p["gate_b"]]
    gate_a_only.sort(key=lambda x: x["total_score"], reverse=True)

    if gate_a_only:
        print(f"\n{'─'*55}")
        print(f"  [GATE-A ONLY] Triggered but not confirmed - reduce position ({len(gate_a_only)} stocks)")
        print(f"{'─'*55}")

        for i, p in enumerate(gate_a_only[:5]):
            r = p["result"]
            print(f"\n  A#{i+1} {p['name']}({p['ticker']}) — {r.total_score}分 @{p['price']} | "
                  f"入场偏离:{p['entry_pct']:+.1f}% | {p['sig_quality']} {p['sig_type']} {p['sig_direction']}")

    # ── Section C: Excellent signal bars waiting for trigger ──
    gate_waiting_scored = [p for p in scored_pairs if not p["gate_a"]]
    gate_waiting_scored.sort(key=lambda x: x["total_score"], reverse=True)

    if gate_waiting_scored:
        print(f"\n{'─'*55}")
        print(f"  [WAITING] Quality signal bars waiting for entry trigger ({len(gate_waiting_scored)} stocks)")
        print(f"{'─'*55}")

        for i, p in enumerate(gate_waiting_scored[:5]):
            r = p["result"]
            sig_type_cn = {
                "strong_trend": "强趋势K线", "pin_bar": "Pin Bar",
                "inside_bar": "内包线", "outside_bar": "外包线", "standard": "标准K线"
            }.get(p["sig_type"], p["sig_type"])
            dir_cn = "多" if p["sig_direction"] == "bullish" else "空"
            print(f"\n  W#{i+1} {p['name']}({p['ticker']}) — {r.total_score}分 @{p['price']}")
            print(f"    信号K线: {dir_cn}头{sig_type_cn} | 质量:{p['sig_quality']} | "
                  f"收盘位:{p['sig_close_pos']:.0%} | 实体:{p['sig_body_ratio']:.0%}")
            print(f"    挂单价: RMB{p['entry_trigger']} | 止损: RMB{p['entry_stop']}")
            print(f"    趋势: MA5({p['ma5']:.2f})>MA10({p['ma10']:.2f})>MA20({p['ma20']:.2f}) "
                  f"| 持续{p['trend_days']}日")

    # Save
    import json
    out_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(out_dir, exist_ok=True)
    out = {
        "scan_date": datetime.now().strftime("%Y-%m-%d"),
        "summary": {
            "trend_aligned": len(trend_stocks),
            "signal_bars": len(signal_entry_pairs),
            "gate_a_triggered": len(gate_a_passed),
            "gate_b_confirmed": len(gate_b_passed),
        },
        "gate_b_confirmed": [],
        "gate_a_only": [],
        "waiting": [],
    }
    for p in gate_b_display[:10]:
        out["gate_b_confirmed"].append({
            "ticker": p["ticker"], "name": p["name"], "score": p["total_score"],
            "price": p["price"], "sig_type": p["sig_type"], "sig_quality": p["sig_quality"],
            "sig_direction": p["sig_direction"],
            "trigger": p["entry_trigger"], "stop": p["entry_stop"],
            "entry_close": p["entry_close"], "entry_pct": p["entry_pct"],
        })
    for p in gate_a_only[:5]:
        out["gate_a_only"].append({
            "ticker": p["ticker"], "name": p["name"], "score": p["total_score"],
            "sig_quality": p["sig_quality"],
        })
    for p in gate_waiting_scored[:5]:
        out["waiting"].append({
            "ticker": p["ticker"], "name": p["name"], "score": p["total_score"],
            "trigger": p["entry_trigger"], "sig_quality": p["sig_quality"],
        })
    path = os.path.join(out_dir, f"signal_entry_{datetime.now().strftime('%Y%m%d')}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved: {path}")


if __name__ == "__main__":
    run_signal_entry_scan()
