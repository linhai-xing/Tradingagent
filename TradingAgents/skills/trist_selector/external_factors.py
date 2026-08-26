"""
External market risk factor module for Trist Selector v3.0.
Fetches US/Japan/Korea semiconductor stock data via yfinance,
computes deduction scores for A-share stocks based on sector correlation.
"""
import os, json, time
from typing import Optional

import yfinance as yf

RULES_PATH = os.path.join(os.path.dirname(__file__), "rules.json")
CORRELATION_PATH = os.path.join(os.path.dirname(__file__), "correlation_map.json")

# Cache: refresh once per hour
_cache = {"timestamp": 0, "quotes": {}, "valid_until": 0}


def _load_rules() -> dict:
    with open(RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_correlation() -> dict:
    with open(CORRELATION_PATH, encoding="utf-8") as f:
        return json.load(f)


def fetch_external_quotes(force_refresh: bool = False) -> dict:
    """
    Fetch last 5 trading days of OHLCV for tracked external symbols.
    Returns dict: {symbol: {"close": [float x5], "change_2d": float, "change_1d": float}}
    Cached: refreshes at most once per hour (3600s) unless force_refresh=True.
    """
    now = time.time()
    if not force_refresh and _cache["quotes"] and (now - _cache["timestamp"]) < 3600:
        return _cache["quotes"]

    rules = _load_rules()
    symbols = list(rules["external"]["tracking_symbols"].keys())

    result = {}
    try:
        for sym in symbols:
            try:
                ticker = yf.Ticker(sym)
                hist = ticker.history(period="5d")
                if len(hist) >= 2:
                    closes = hist["Close"].tolist()
                    chg_1d = (closes[-1] / closes[-2] - 1) * 100 if len(closes) >= 2 else 0
                    chg_2d = (closes[-1] / closes[-3] - 1) * 100 if len(closes) >= 3 else chg_1d
                    result[sym] = {
                        "close": closes,
                        "change_1d": round(chg_1d, 2),
                        "change_2d": round(chg_2d, 2),
                        "consecutive_down": _count_consecutive_down(hist),
                    }
                time.sleep(0.3)  # rate limit
            except Exception:
                result[sym] = {"error": "fetch_failed", "change_1d": 0, "change_2d": 0, "consecutive_down": 0}
    except Exception:
        pass

    _cache["quotes"] = result
    _cache["timestamp"] = now
    return result


def _count_consecutive_down(hist) -> int:
    """Count consecutive down days from most recent."""
    closes = hist["Close"].tolist()
    count = 0
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] < closes[i - 1]:
            count += 1
        else:
            break
    return count


def get_sector_correlation(sector_name: str) -> float:
    """
    Get correlation coefficient for a sector name.
    Returns 1.0 (high), 0.7 (medium), 0.5 (low), or default 0.7.
    Performs substring matching — e.g. "半导体设备" matches "半导体".
    """
    corr = _load_correlation()
    default = corr.get("default_coefficient", 0.7)

    for level in ["high", "medium", "low"]:
        for keyword in corr[level]["sectors"]:
            if keyword in sector_name:
                return corr[level]["coefficient"]
    return default


def compute_external_score(sector_name: str = "") -> tuple:
    """
    Compute external risk deduction score.

    Args:
        sector_name: Stock's industry/sector name for correlation adjustment

    Returns:
        (score: int, reasons: list[str], details: dict)
        score is 0-10, 10 = no risk, 0 = maximum risk
    """
    rules = _load_rules()
    ext_rules = rules["external"]
    deductions = ext_rules["deductions"]
    max_score = ext_rules["max_score"]

    quotes = fetch_external_quotes()
    if not quotes:
        return (max_score, ["外围数据获取失败，默认满分"], {"raw_deduction": 0, "correlation": 0})

    correlation = get_sector_correlation(sector_name) if sector_name else 0.7
    raw_deduction = 0
    reasons = []

    # Check SMH (semiconductor ETF) — broadest signal
    smh = quotes.get("SMH", {})
    smh_2d = smh.get("change_2d", 0)
    if smh_2d < -10:
        raw_deduction += deductions["smh_2d_drop_10pct"]
        reasons.append(f"SMH 2日跌{smh_2d:.1f}% (>10%)")
    elif smh_2d < -5:
        raw_deduction += deductions["smh_2d_drop_5pct"]
        reasons.append(f"SMH 2日跌{smh_2d:.1f}% (>5%)")

    # Check NVDA single-day
    nvda = quotes.get("NVDA", {})
    nvda_1d = nvda.get("change_1d", 0)
    if nvda_1d < -5:
        raw_deduction += deductions["nvda_single_day_drop_5pct"]
        reasons.append(f"NVDA单日跌{nvda_1d:.1f}%")

    # Check 3+ symbols dropping >3% same day
    drop_count = sum(1 for q in quotes.values() if q.get("change_1d", 0) < -3)
    if drop_count >= 3:
        raw_deduction += deductions["three_or_more_drop_3pct"]
        reasons.append(f"{drop_count}只外围标的同日跌>3%")

    # Check consecutive decline
    consec_count = sum(1 for q in quotes.values() if q.get("consecutive_down", 0) >= 3)
    if consec_count >= 1:
        raw_deduction += deductions["consecutive_3d_decline"]
        reasons.append(f"{consec_count}只外围标的连续3日阴线")

    # Apply correlation coefficient
    adjusted_deduction = round(raw_deduction * correlation)
    final_score = max(max_score - adjusted_deduction, ext_rules["min_score"])

    details = {
        "raw_deduction": raw_deduction,
        "correlation": correlation,
        "adjusted_deduction": adjusted_deduction,
        "final_score": final_score,
        "quotes_summary": {s: {"chg_1d": q.get("change_1d", 0), "chg_2d": q.get("change_2d", 0)}
                           for s, q in quotes.items()},
    }

    return (final_score, reasons, details)
