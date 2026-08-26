"""
Trist Selector v4.2 - Price Action Screener (阿布价格行为学)
5-step funnel: coarse filter -> forbidden scan -> PA scoring(90pts) -> entry signals -> Top 5

Usage:
    python screener.py                    # Full market screen
    python screener.py --watchlist        # Custom watchlist only
    python screener.py 600522             # Single stock analysis
"""
import noproxy  # MUST be first — bypasses proxy for eastmoney APIs

import json, os, sys, time, argparse
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd

# ─── Discipline State (trader-level cooling-off) ──────────────

DISCIPLINE_FILE = os.path.join(os.path.dirname(__file__), "output", "discipline_state.json")


def load_discipline_state() -> dict:
    """Load trader discipline state (X13/X14 cooling-off tracking).

    Returns dict with:
        stop_loss_today: bool    — SL triggered today? (X13)
        last_trade_loss_pct: float  — last closed trade loss% (X14)
        last_trade_close_date: str  — YYYY-MM-DD
        cooldown_until_date: str   — YYYY-MM-DD (block trading until)
        today_date: str           — YYYY-MM-DD
    """
    today = datetime.now().strftime("%Y-%m-%d")
    defaults = {
        "stop_loss_today": False,
        "last_trade_loss_pct": 0.0,
        "last_trade_close_date": "",
        "cooldown_until_date": "",
        "today_date": today,
    }
    try:
        if os.path.exists(DISCIPLINE_FILE):
            with open(DISCIPLINE_FILE, encoding="utf-8") as f:
                state = json.load(f)
            # Reset stop_loss_today if it was from a previous day
            if state.get("stop_loss_date", "") != today:
                state["stop_loss_today"] = False
            return {**defaults, **state, "today_date": today}
    except Exception:
        pass
    return defaults


def save_discipline_state(state: dict):
    """Persist discipline state for X13/X14 enforcement."""
    os.makedirs(os.path.dirname(DISCIPLINE_FILE), exist_ok=True)
    with open(DISCIPLINE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def record_stop_loss_triggered():
    """Call this when SL1/SL2/SL3 is triggered — locks trading for the day (X13)."""
    state = load_discipline_state()
    state["stop_loss_today"] = True
    state["stop_loss_date"] = datetime.now().strftime("%Y-%m-%d")
    save_discipline_state(state)


def record_trade_loss(loss_pct: float, close_date: str = None):
    """Call this when a trade is closed at a loss.
    If loss >= 5%, triggers 2-day cooling-off (X14).
    """
    state = load_discipline_state()
    state["last_trade_loss_pct"] = loss_pct
    state["last_trade_close_date"] = close_date or datetime.now().strftime("%Y-%m-%d")
    if loss_pct <= -0.05:
        cooldown_start = datetime.strptime(state["last_trade_close_date"], "%Y-%m-%d")
        cooldown_until = cooldown_start + timedelta(days=3)  # close day + 2 full days
        state["cooldown_until_date"] = cooldown_until.strftime("%Y-%m-%d")
    save_discipline_state(state)
import numpy as np
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, r"C:\Users\72955\.claude\plugins\cache\uzi-skill\stock-deep-analyzer\3.9.0\skills\deep-analysis\scripts")

from scoring import TristScorer, ScoreResult, build_market_context
from entry_signals import detect_entry_signals, get_entry_recommendation
from data_cache import update_one as cache_update_one, update_batch as cache_update_batch
try:
    from data_sources import fetch_lhb_recent, fetch_research_reports, fetch_financials_batch, fetch_sector_classification, enhance_stock_data
    HAS_DATA_SOURCES = True
except ImportError:
    HAS_DATA_SOURCES = False

OUT_DIR = os.path.join(os.path.dirname(__file__), "output")
RULES_PATH = os.path.join(os.path.dirname(__file__), "rules.json")

with open(RULES_PATH, encoding="utf-8") as f:
    RULES = json.load(f)


def refresh_mas_with_live_price(indicators: dict, kline_df, live_price: float) -> None:
    """Recalculate MA5/MA7/MA10/MA20 using live price as the latest data point.

    Call this after overriding indicators['price'] with real-time data.
    The cached K-line close[-1] is stale (yesterday); replace with live_price.
    """
    if not live_price or live_price <= 0:
        return
    c = kline_df["close"].values
    n = len(c)
    if n < 5:
        return
    # Replace last cached close with live price, recompute MAs
    indicators["ma5"] = round(float(np.mean(np.append(c[-4:], live_price))), 2) if n >= 5 else indicators.get("ma5", 0)
    indicators["ma7"] = round(float(np.mean(np.append(c[-6:], live_price))), 2) if n >= 7 else indicators.get("ma7", 0)
    indicators["ma10"] = round(float(np.mean(np.append(c[-9:], live_price))), 2) if n >= 10 else indicators.get("ma10", 0)
    indicators["ma20"] = round(float(np.mean(np.append(c[-19:], live_price))), 2) if n >= 20 else indicators.get("ma20", 0)


def load_stock_list() -> pd.DataFrame:
    """Load A-share stock list (coarse filter Step 1)."""
    print("[Step 1] Loading A-share stock list...")
    # Primary: direct eastmoney API (bypasses akshare proxy issues)
    try:
        from direct_api import get_stock_list
        df = get_stock_list(page_size=50)
        if df is not None and len(df) > 100:
            df = df.dropna(subset=["price", "float_cap"])
            return df
    except Exception as e:
        print(f"  direct_api failed: {e}")

    # Fallback: akshare
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        df = df[["代码", "名称", "最新价", "涨跌幅", "换手率", "流通市值", "市盈率-动态", "量比"]]
        df.columns = ["ticker", "name", "price", "change_pct", "turnover", "float_cap", "pe_ttm", "vol_ratio"]
        for c in ["price", "change_pct", "turnover", "float_cap", "pe_ttm", "vol_ratio"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.dropna(subset=["price", "float_cap"])
    except Exception:
        pass

    # Last fallback: baostock
    print("  Falling back to baostock...")
    import baostock as bs
    bs.login()
    rs = bs.query_stock_basic()
    rows = []
    while (rs.error_code == '0') & rs.next():
        rows.append(rs.get_row_data())
    bs.logout()
    df = pd.DataFrame(rows, columns=["code", "name", "ipo_date", "out_date", "type", "status"])
    df = df[df["type"] == "1"]
    # baostock codes include exchange prefix ("sh.600000") — strip to bare ticker
    df["ticker"] = df["code"].str.replace(r"^(sh\.|sz\.)", "", regex=True)
    # baostock doesn't have market data — add default columns so pipeline doesn't crash
    df["price"] = 0.0
    df["turnover"] = 3.0  # above 2% filter
    df["float_cap"] = 1e10  # ~100亿, within filter range
    df["change_pct"] = 0.0
    return df


def coarse_filter(df: pd.DataFrame) -> pd.DataFrame:
    """
    Step 1: Coarse filter.
    - Exclude ST/*ST
    - Listed > 60 days
    - Float market cap 20-800 billion (in raw units)
    - Daily turnover > 2%
    - Not limit-down today
    """
    S = RULES["screener"]
    print(f"  Input: {len(df)} stocks")

    # Exclude ST
    if "name" in df.columns:
        df = df[~df["name"].str.contains("ST|退", na=False)]
    print(f"  After ST exclusion: {len(df)}")

    # Float cap: raw data is in 元 or 亿
    if "float_cap" in df.columns:
        cap_min = S["min_float_market_cap"] * 1e8
        cap_max = S["max_float_market_cap"] * 1e8
        # Check unit - akshare float_cap is in 元
        if df["float_cap"].median() < 1000:
            cap_min = S["min_float_market_cap"]
            cap_max = S["max_float_market_cap"]
        df = df[(df["float_cap"] >= cap_min) & (df["float_cap"] <= cap_max)]
        print(f"  After cap filter ({S['min_float_market_cap']}-{S['max_float_market_cap']}亿): {len(df)}")

    # Turnover
    if "turnover" in df.columns:
        df = df[df["turnover"] > 2.0]
        print(f"  After turnover filter (>2%): {len(df)}")

    # Not limit-down (change > -9.5%)
    if "change_pct" in df.columns:
        df = df[df["change_pct"] > -9.5]
        print(f"  After limit-down exclusion: {len(df)}")

    print(f"  Output: {len(df)} stocks")
    return df


def pull_kline_batch(tickers: list) -> dict:
    """Pull daily K-line for a batch of tickers. Uses local CSV cache — incremental update only."""
    print(f"  Updating K-line cache for {len(tickers)} tickers...")
    klines = cache_update_batch(tickers, start_date="2026-01-01")
    print(f"  Cached K-lines available for {len(klines)}/{len(tickers)} stocks")
    return klines


def _calc_ema(values, period):
    """Calculate EMA for given period."""
    import numpy as np
    if len(values) < period:
        return np.full(len(values), float(np.mean(values)))
    alpha = 2 / (period + 1)
    ema = np.zeros(len(values))
    ema[0] = values[0]
    for i in range(1, len(values)):
        ema[i] = alpha * values[i] + (1 - alpha) * ema[i - 1]
    return ema


def compute_indicators(kline_df):
    """Compute technical + price action indicators from K-line DataFrame.

    v4.0: Added PA features (MA gap, bar overlap, signal bar quality,
    H1/H2/L1/L2 counting, wedge detection, S/R confluence).
    """
    import numpy as np

    c = kline_df["close"].values.astype(float)
    o = kline_df["open"].values.astype(float)
    h = kline_df["high"].values.astype(float)
    ll = kline_df["low"].values.astype(float)
    v = kline_df["volume"].values.astype(float)

    if len(c) < 20:
        return {}

    n = len(c)

    ma5 = np.mean(c[-5:])
    ma10 = np.mean(c[-10:])
    ma20 = np.mean(c[-20:])
    ma60 = np.mean(c[-min(60, n):])

    ema20 = _calc_ema(c, 20)

    ret_1d = c[-1] / c[-2] - 1 if n >= 2 else 0
    ret_3d = c[-1] / c[-min(4, n)] - 1 if n >= 4 else 0
    ret_5d = c[-1] / c[-min(6, n)] - 1 if n >= 6 else 0
    ret_10d = c[-1] / c[-min(11, n)] - 1 if n >= 11 else 0
    ret_20d = c[-1] / c[-min(21, n)] - 1 if n >= 21 else ret_5d * 4

    chain = 0
    for i in range(n-1, max(n-10, 0), -1):
        if c[i] / c[i-1] - 1 > 0.095:
            chain += 1
        else:
            break

    vol_ma5 = np.mean(v[-5:])
    vol_ratio = v[-1] / vol_ma5 if vol_ma5 > 0 else 1
    prev_vol_ratio = v[-2] / vol_ma5 if n >= 2 and vol_ma5 > 0 else 1
    avg_turnover_5d = np.mean(v[-5:]) / 1e6

    delta = np.diff(c[-15:])
    gain = np.mean(delta[delta > 0]) if len(delta[delta > 0]) > 0 else 0
    loss = np.mean(-delta[delta < 0]) if len(delta[delta < 0]) > 0 else 0.0001
    rsi14 = 100 - 100 / (1 + gain / loss) if loss > 0 else 50

    amp_3d = np.mean([(h[-i] - ll[-i]) / o[-i] for i in range(1, min(4, n+1)) if o[-i] > 0])
    high_20d = np.max(h[-20:])
    low_20d = np.min(ll[-20:])
    range_20d = high_20d - low_20d

    prev_ret = c[-2] / c[-3] - 1 if n >= 3 else 0
    prev_day_limit_up = prev_ret > 0.095

    # === v4.0 Price Action Features ===
    ma_gap_bars = 0
    for i in range(n-1, max(n-60, 0), -1):
        if not (ll[i] <= ema20[i] <= h[i]):
            ma_gap_bars += 1
        else:
            break

    trend_bar_count = 0
    for i in range(max(n-10, 0), n):
        bar_range = h[i] - ll[i]
        if bar_range > 0:
            if abs(c[i] - o[i]) / bar_range >= 0.60:
                trend_bar_count += 1
    trend_bar_ratio = trend_bar_count / min(10, n)

    overlap_count = 0
    lookback_ov = min(20, n-1)
    for i in range(n - lookback_ov + 1, n):
        overlap_max = min(h[i-1], h[i])
        overlap_min = max(ll[i-1], ll[i])
        if overlap_max > overlap_min:
            overlap_count += 1
    bar_overlap_ratio = overlap_count / max(lookback_ov - 1, 1)

    range_amplitude_20d = range_20d / low_20d if low_20d > 0 else 0.99
    dist_from_20d_high = (c[-1] - low_20d) / range_20d if range_20d > 0 else 0.5

    last_c, last_o, last_h, last_l = c[-1], o[-1], h[-1], ll[-1]
    total_range = last_h - last_l
    body = abs(last_c - last_o)
    upper_shadow = last_h - max(last_c, last_o)
    lower_shadow = min(last_c, last_o) - last_l
    is_bullish_bar = last_c > last_o

    signal_close_position = float((last_c - last_l) / total_range) if total_range > 0 else 0.5
    signal_body_ratio = float(body / total_range) if total_range > 0 else 0
    signal_upper_shadow_ratio = float(upper_shadow / total_range) if total_range > 0 else 0
    signal_lower_shadow_ratio = float(lower_shadow / total_range) if total_range > 0 else 0

    is_strong_trend_bar = (
        signal_body_ratio >= 0.70
        and ((is_bullish_bar and signal_upper_shadow_ratio <= 0.10)
             or (not is_bullish_bar and signal_lower_shadow_ratio <= 0.10))
    )
    is_pin_bar = (
        (is_bullish_bar and lower_shadow > body * 2 and upper_shadow < body * 0.3)
        or (not is_bullish_bar and upper_shadow > body * 2 and lower_shadow < body * 0.3)
    )
    is_inside_bar = (n >= 2 and last_h < h[-2] and last_l > ll[-2])
    is_outside_bar = (n >= 2 and last_h > h[-2] and last_l < ll[-2])

    opposing_bars_count = 0
    for i in range(n-2, max(n-10, 0), -1):
        bar_bullish = c[i] > o[i]
        if is_bullish_bar and not bar_bullish:
            opposing_bars_count += 1
        elif not is_bullish_bar and bar_bullish:
            opposing_bars_count += 1
        else:
            break

    from entry_signals import count_h_l_signals, detect_wedge
    _kl = {"closes": c.tolist(), "opens": o.tolist(), "highs": h.tolist(), "lows": ll.tolist()}
    if bar_overlap_ratio >= 0.60:
        _ms = "trading_range"
    elif ma5 > ma20 > 0 and c[-1] > ma20:
        _ms = "trend_bull"
    elif 0 < ma5 < ma20 and c[-1] < ma20:
        _ms = "trend_bear"
    else:
        _ms = "unknown"
    h_count, l_count, _ = count_h_l_signals(_kl, _ms)
    wedge_detected, wedge_type, parabolic_wedge = detect_wedge(_kl)

    sr_confluence_count = 0
    proximity = 0.02
    for ma_val in [ma5, ma10, ma20, ma60]:
        if ma_val > 0 and abs(c[-1] - ma_val) / c[-1] < proximity:
            sr_confluence_count += 1
    prior_high_20d = np.max(h[-20:-1]) if n >= 21 else high_20d
    prior_low_20d = np.min(ll[-20:-1]) if n >= 21 else low_20d
    if abs(c[-1] - prior_high_20d) / c[-1] < proximity:
        sr_confluence_count += 1
    if abs(c[-1] - prior_low_20d) / c[-1] < proximity:
        sr_confluence_count += 1

    signal_bar_high = float(last_h)
    signal_bar_low = float(last_l)

    # v4.1: ATR(5) & gap for X16/X17 checks
    atr5_pct = 0.0
    if n >= 6:
        tr_vals = []
        for j in range(n-5, n):
            true_high = max(h[j], c[j-1])
            true_low = min(ll[j], c[j-1])
            tr = true_high - true_low
            tr_vals.append(tr)
        atr5_val = float(np.mean(tr_vals))
        atr5_pct = float(atr5_val / c[-1]) if c[-1] > 0 else 0.0

    open_gap_pct = 0.0
    if n >= 2:
        open_gap_pct = float((o[-1] - c[-2]) / c[-2]) if c[-2] > 0 else 0.0

    return {
        "ma5": round(float(ma5), 2),
        "ma10": round(float(ma10), 2),
        "ma20": round(float(ma20), 2),
        "ma60": round(float(ma60), 2),
        "pre_3d_return": round(float(ret_3d), 4),
        "pre_5d_return": round(float(ret_5d), 4),
        "pre_10d_return": round(float(ret_10d), 4),
        "pre_20d_return": round(float(ret_20d), 4),
        "consecutive_limit_up_days": chain,
        "avg_daily_amount_5d": round(float(np.mean(v[-5:])), 0),
        "vol_ratio": round(float(vol_ratio), 2),
        "prev_day_vol_ratio": round(float(prev_vol_ratio), 2),
        "prev_day_ret": round(float(prev_ret), 4),
        "today_ret": round(float(ret_1d), 4),
        "avg_turnover_5d": round(float(avg_turnover_5d), 4),
        "avg_daily_volume_5d": round(float(np.mean(v[-5:])), 0),
        "avg_amplitude_3d": round(float(amp_3d), 4),
        "high_20d": round(float(high_20d), 2),
        "rsi14": round(float(rsi14), 1),
        "prev_day_limit_up": prev_day_limit_up,
        "has_bad_news_3d": False,
        "research_buy_count": 0,
        "research_total_count": 0,
        "net_profit_growth_yoy": 0,
        # v4.0 PA fields
        "ma_gap_bars": ma_gap_bars,
        "bar_overlap_ratio": round(float(bar_overlap_ratio), 3),
        "range_amplitude_20d": round(float(range_amplitude_20d), 3),
        "trend_bar_ratio": round(float(trend_bar_ratio), 3),
        "dist_from_20d_high": round(float(dist_from_20d_high), 3),
        "signal_close_position": round(float(signal_close_position), 3),
        "signal_body_ratio": round(float(signal_body_ratio), 3),
        "signal_upper_shadow_ratio": round(float(signal_upper_shadow_ratio), 3),
        "signal_lower_shadow_ratio": round(float(signal_lower_shadow_ratio), 3),
        "is_bullish_bar": is_bullish_bar,
        "is_pin_bar": is_pin_bar,
        "is_inside_bar": is_inside_bar,
        "is_outside_bar": is_outside_bar,
        "is_strong_trend_bar": is_strong_trend_bar,
        "opposing_bars_count": opposing_bars_count,
        "signal_bar_high": round(float(signal_bar_high), 2),
        "signal_bar_low": round(float(signal_bar_low), 2),
        "sr_confluence_count": sr_confluence_count,
        "h_count": h_count,
        "l_count": l_count,
        "wedge_detected": wedge_detected,
        "wedge_type": wedge_type,
        "parabolic_wedge": parabolic_wedge,
        # v4.1: X16/X17 support
        "atr5_pct": round(float(atr5_pct), 4),
        "open_gap_pct": round(float(open_gap_pct), 4),
    }


def get_sector_ranks(stocks_df: pd.DataFrame) -> dict:
    """Get sector performance rankings."""
    try:
        import akshare as ak
        sector_df = ak.stock_board_industry_name_em()
        sector_returns = {}
        sectors = sector_df["板块名称"].tolist()[:50]

        for sector_name in sectors[:20]:  # limit API calls
            try:
                cons = ak.stock_board_industry_cons_em(symbol=sector_name)
                time.sleep(0.3)
            except:
                pass

        return sector_returns
    except:
        return {}


def screen_single(ticker: str, name: str = "", price: float = 0,
                  kline_df: pd.DataFrame = None) -> ScoreResult:
    """Screen a single stock."""
    if kline_df is None:
        kline_df = cache_update_one(ticker, start_date="2026-01-01")
        if len(kline_df) == 0:
            return ScoreResult(ticker=ticker, name=name,
                             forbidden_hits=["X0: 无法获取K线数据"], vetoed=True)

    indicators = compute_indicators(kline_df)
    indicators["ticker"] = ticker
    indicators["name"] = name
    indicators["price"] = price or float(kline_df["close"].values[-1])
    indicators["sector"] = indicators.get("sector", "")

    # Try real-time quote to override stale cached close
    try:
        from direct_api import get_realtime_quote
        rt = get_realtime_quote(ticker)
        if rt and rt.get('price', 0) > 0:
            indicators['price'] = rt['price']
            indicators['vol_ratio'] = rt.get('vol_ratio', indicators['vol_ratio'])
            indicators['today_ret'] = rt.get('change_pct', 0) / 100
            indicators['avg_turnover_5d'] = rt.get('turnover', 0)
            indicators['is_realtime'] = True
            # Recalculate MAs with live price (cached close[-1] is stale)
            refresh_mas_with_live_price(indicators, kline_df, rt['price'])
    except Exception:
        pass

    # Enrich with external data if available
    if HAS_DATA_SOURCES:
        try:
            # Batch-fetch for all tickers once per run (cached via module-level)
            if not hasattr(screen_single, "_lhb_cache"):
                screen_single._lhb_cache = fetch_lhb_recent(5)
                screen_single._research_cache = fetch_research_reports()
                screen_single._financials_cache = fetch_financials_batch([ticker])
                screen_single._sectors_cache = fetch_sector_classification()
            indicators = enhance_stock_data(indicators,
                screen_single._lhb_cache,
                screen_single._research_cache,
                screen_single._financials_cache,
                screen_single._sectors_cache)
        except Exception:
            pass

    # Build market context (cached per run)
    if not hasattr(screen_single, "_market_ctx"):
        print("  Building market context (emotion cycle, LHB, sectors)...")
        screen_single._market_ctx = build_market_context()
        print(f"    Limit-up: {screen_single._market_ctx.get('limit_up_count', '?')} | "
              f"Max chain: {screen_single._market_ctx.get('max_chain_height', '?')} | "
              f"LHB stocks: {len(screen_single._market_ctx.get('lhb_data', {}))}")

    scorer = TristScorer(market_context=screen_single._market_ctx)
    # Load discipline state (trader-level cooling-off)
    discipline_state = load_discipline_state()
    result = scorer.score(indicators, {}, discipline_state=discipline_state)

    # Entry signals
    kline_dict = {
        "closes": kline_df["close"].tolist(),
        "opens": kline_df["open"].tolist(),
        "highs": kline_df["high"].tolist(),
        "lows": kline_df["low"].tolist(),
        "volumes": kline_df["volume"].tolist(),
    }
    signals = detect_entry_signals(kline_dict, ticker)
    entry_rec = get_entry_recommendation(signals)
    result.entry_signals = [s.name for s in signals]
    result.entry_recommendation = entry_rec

    return result


def run_full_screen(output_top_n: int = 5):
    """Run full market screening pipeline."""
    print("=" * 60)
    print(f"  Trist Selector v4.2 - PA (阿布价格行为学)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # Step 1: Load + coarse filter
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

    # Step 3: Score each stock
    print(f"\n[Step 3] Scoring {len(klines)} stocks...")
    results = []
    ticker_to_name = dict(zip(df["ticker"], df["name"]))
    ticker_to_price = dict(zip(df["ticker"], df["price"]))

    for ticker, kline_df in klines.items():
        name = ticker_to_name.get(ticker, "")
        price = ticker_to_price.get(ticker, 0)
        r = screen_single(ticker, name, price, kline_df)
        results.append(r)

    # Step 4: Sort and pick top N
    passed = [r for r in results if not r.vetoed and r.total_score >= 54]
    vetoed = [r for r in results if r.vetoed]
    passed.sort(key=lambda x: x.total_score, reverse=True)

    top5 = passed[:output_top_n]

    # Output
    print(f"\n{'='*60}")
    print(f"  RESULTS: {len(passed)} passed, {len(vetoed)} vetoed")
    print(f"{'='*60}")

    for i, r in enumerate(top5):
        pos_emoji = {"full": "满仓", "half": "半仓", "observe": "观察"}
        print(f"\n  #{i+1} [{pos_emoji.get(r.position, '?')}] {r.name}({r.ticker}) — {r.total_score}分 @{r.price}")
        # v4.0 PA scoring
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
            bonus_str = " ".join([f"{k}=+{v}" for k, v in r.bonus_details.items()])
            print(f"    强化: {bonus_str}")
        if r.entry_signals:
            print(f"    入场信号: {', '.join(r.entry_signals[:5])}")
        print(f"    仓位:{r.position_pct*100:.0f}%")
    # Save to JSON
    output = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "version": "v4.2-price-action",
        "top5": [
            {
                "rank": i+1,
                "ticker": r.ticker,
                "name": r.name,
                "price": r.price,
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
                "pa_reasons": r.pa_reasons,
                "bonus_details": r.bonus_details,
                "entry_signals": r.entry_signals,
                "forbidden_hits": r.forbidden_hits,
            }
            for i, r in enumerate(top5)
        ],
        "stats": {
            "total_candidates": len(results),
            "passed": len(passed),
            "vetoed": len(vetoed),
            "top_score": top5[0].total_score if top5 else 0,
        }
    }

    out_path = os.path.join(OUT_DIR, f"top5_{datetime.now().strftime('%Y%m%d')}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved: {out_path}")

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trist Selector - Stock Screener")
    parser.add_argument("ticker", nargs="?", help="Single stock ticker to analyze")
    parser.add_argument("--full", action="store_true", help="Full market screen")
    parser.add_argument("--top", type=int, default=5, help="Top N output (default 5)")
    args = parser.parse_args()

    if args.ticker and not args.full:
        # Single stock analysis
        print(f"\n  Trist Selector v4.2 - Single Stock Analysis: {args.ticker}")
        result = screen_single(args.ticker)
        if result.discipline_hits:
            print(f"  [Discipline] {', '.join(result.discipline_hits)}")
        print(f"\n  === Score: {result.total_score}/100 (PA:{result.pa_score}/90 + 强化:{result.bonus_score}/10) ===")
        print(f"  Market: {result.market_state} | Signal Bar: {result.signal_bar_quality}({result.signal_bar_type})")
        if hasattr(result, 'pa_details') and result.pa_details:
            pa_items = []
            for k, v in result.pa_details.items():
                if v != 0:
                    sign = "+" if v > 0 else ""
                    pa_items.append(f"{k}:{sign}{v}")
            print(f"  PA Details: {' | '.join(pa_items)}")
        print(f"  H{result.h_count}/L{result.l_count} | Wedge: {result.wedge_type} | SR: {result.sr_confluence}")
        print(f"  Position: {result.position} ({result.position_pct*100:.0f}%)")
        if result.forbidden_hits:
            print(f"  Forbidden: {result.forbidden_hits}")
        print(f"  Gate(下单前必查): Gate-A挂突破单 Gate-B收盘确认 Gate-C下午执行")
        if result.entry_signals:
            print(f"  Entry Signals: {result.entry_signals}")
    else:
        run_full_screen(output_top_n=args.top)
