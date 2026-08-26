"""
Local K-line CSV cache — download once, update incrementally.
Rate-limited: max 300 stocks per batch, sleeps between requests.

Cache location: ./data_cache/{ticker}.csv
"""
import os, time
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

CACHE_DIR = os.path.join(os.path.dirname(__file__), "data_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# ── Rate limit config ──
BATCH_SIZE = 300          # max stocks per batch
SLEEP_BETWEEN_STOCKS = 0.3  # seconds between individual stock requests
SLEEP_BETWEEN_BATCHES = 5.0  # seconds between batches
AKSHARE_SLEEP = 1.0         # seconds between akshare calls (stricter)
MAX_AKSHARE_RETRIES = 3     # retry failed akshare calls


def _ticker_to_bs(ticker: str) -> str:
    return ("sh." if ticker.startswith(("6", "9")) else "sz.") + ticker


def _load_cache(ticker: str) -> pd.DataFrame:
    path = os.path.join(CACHE_DIR, f"{ticker}.csv")
    if os.path.exists(path):
        df = pd.read_csv(path, parse_dates=["date"])
        return df.sort_values("date")
    return pd.DataFrame()


def _save_cache(ticker: str, df: pd.DataFrame):
    path = os.path.join(CACHE_DIR, f"{ticker}.csv")
    df = df.sort_values("date").drop_duplicates(subset=["date"]).reset_index(drop=True)
    df.to_csv(path, index=False)


def update_one(ticker: str, start_date: str = "2020-01-01", bs_session=None) -> pd.DataFrame:
    """
    Update K-line cache for one ticker. Incremental after first download.
    Pass bs_session (baostock login object) to reuse connection.
    """
    cached = _load_cache(ticker)
    bs_code = _ticker_to_bs(ticker)

    if len(cached) > 0:
        last_date = pd.Timestamp(cached["date"].max())
        start = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
        if start >= datetime.now().strftime("%Y-%m-%d"):
            return cached
    else:
        start = start_date

    end = datetime.now().strftime("%Y-%m-%d")

    # Only request if there's actually new data to fetch
    if start >= end:
        return cached

    try:
        own_session = bs_session is None
        if own_session:
            import baostock as bs
            bs.login()
            sess = bs
        else:
            sess = bs_session

        rs = sess.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume,amount,turn,peTTM",
            start_date=start, end_date=end,
            frequency="d", adjustflag="2"
        )

        # Handle baostock error response
        if rs is None or rs.error_code != '0':
            if own_session:
                sess.logout()
            return cached

        rows = []
        while (rs.error_code == '0') & rs.next():
            rows.append(rs.get_row_data())

        if own_session:
            sess.logout()

        if not rows:
            return cached

        cols = ["date","open","high","low","close","volume","amount","turn","peTTM"]
        new_df = pd.DataFrame(rows, columns=cols[:len(rows[0])])
        new_df["date"] = pd.to_datetime(new_df["date"])
        for c in ["open","high","low","close","volume","amount","turn","peTTM"]:
            if c in new_df.columns:
                new_df[c] = pd.to_numeric(new_df[c], errors="coerce")

        merged = pd.concat([cached, new_df], ignore_index=True) if len(cached) > 0 else new_df
        merged = merged.sort_values("date").drop_duplicates(subset=["date"]).reset_index(drop=True)
        _save_cache(ticker, merged)
        return merged

    except Exception:
        return cached if len(cached) > 0 else pd.DataFrame()


def update_batch(tickers: list, start_date: str = "2020-01-01") -> dict:
    """
    Batch update with rate limiting: 300 stocks/batch, 0.3s between stocks, 5s between batches.
    Reuses a single baostock login session for efficiency.
    """
    results = {}
    total = len(tickers)
    import baostock as bs

    for batch_start in range(0, total, BATCH_SIZE):
        batch = tickers[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  Batch {batch_num}/{total_batches}: {len(batch)} stocks...")

        bs.login()
        for i, ticker in enumerate(batch):
            if i > 0:
                time.sleep(SLEEP_BETWEEN_STOCKS)
            try:
                df = update_one(ticker, start_date, bs_session=bs)
                if len(df) >= 20:
                    results[ticker] = df
            except Exception as e:
                pass
        bs.logout()

        if batch_start + BATCH_SIZE < total:
            print(f"    Sleeping {SLEEP_BETWEEN_BATCHES}s between batches...")
            time.sleep(SLEEP_BETWEEN_BATCHES)

    return results


def update_all_a_shares(start_date: str = "2020-01-01") -> int:
    """One-time download of all A-share K-line data to cache (15-30 min)."""
    # Get ticker list via baostock (more reliable than akshare for bulk)
    try:
        import baostock as bs
        bs.login()
        rs = bs.query_stock_basic()
        tickers = []
        while (rs.error_code == '0') & rs.next():
            row = rs.get_row_data()
            if row[3] == "1":
                tickers.append(row[0].split(".")[-1])
        bs.logout()
    except Exception:
        print("Cannot get stock list from baostock, trying akshare...")
        tickers = _get_tickers_akshare()
        if not tickers:
            return 0

    print(f"Downloading {len(tickers)} A-share stocks in batches of {BATCH_SIZE}...")
    print(f"Estimated time: {len(tickers) * SLEEP_BETWEEN_STOCKS / 60:.0f} minutes")
    print(f"Cache dir: {CACHE_DIR}\n")

    count = 0
    for batch_start in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[batch_start:batch_start + BATCH_SIZE]
        results = update_batch(batch, start_date)
        count += len(results)

        done = min(batch_start + BATCH_SIZE, len(tickers))
        print(f"  Progress: {done}/{len(tickers)} ({count} cached)")

        if batch_start + BATCH_SIZE < len(tickers):
            time.sleep(SLEEP_BETWEEN_BATCHES)

    print(f"\nDone. {count} stocks cached in {CACHE_DIR}")
    return count


def _get_tickers_akshare() -> list:
    """Get A-share ticker list from akshare with retries."""
    for attempt in range(MAX_AKSHARE_RETRIES):
        try:
            import akshare as ak
            time.sleep(AKSHARE_SLEEP * (attempt + 1))
            df = ak.stock_zh_a_spot_em()
            return df["代码"].tolist()
        except Exception as e:
            if attempt < MAX_AKSHARE_RETRIES - 1:
                wait = AKSHARE_SLEEP * (2 ** attempt)
                print(f"    akshare retry {attempt+1}/{MAX_AKSHARE_RETRIES} in {wait}s... ({e})")
                time.sleep(wait)
    return []


def get_cache_stats() -> dict:
    """Get cache statistics."""
    stats = {"total_files": 0, "total_size_mb": 0}
    if not os.path.exists(CACHE_DIR):
        return stats
    files = [f for f in os.listdir(CACHE_DIR) if f.endswith(".csv")]
    stats["total_files"] = len(files)
    stats["total_size_mb"] = round(sum(
        os.path.getsize(os.path.join(CACHE_DIR, f)) for f in files
    ) / 1024 / 1024, 2)
    return stats


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "all":
            update_all_a_shares()
        elif cmd == "stats":
            stats = get_cache_stats()
            print(f"Cache: {stats['total_files']} files, {stats['total_size_mb']} MB")
        elif cmd == "update":
            files = [f.replace(".csv", "") for f in os.listdir(CACHE_DIR) if f.endswith(".csv")]
            print(f"Updating {len(files)} cached stocks...")
            update_batch(files)
            print("Done.")
        else:
            df = update_one(sys.argv[1])
            print(f"{sys.argv[1]}: {len(df)} days cached")
    else:
        print("Usage: python data_cache.py <ticker> | all | stats | update")
        print(f"Rate limits: {BATCH_SIZE} stocks/batch, {SLEEP_BETWEEN_STOCKS}s between, {SLEEP_BETWEEN_BATCHES}s between batches")
        stats = get_cache_stats()
        print(f"Current cache: {stats}")
