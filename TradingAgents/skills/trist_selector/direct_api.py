"""
Lightweight eastmoney API client — bypasses akshare's internal proxy issues.
Uses direct requests with trust_env=False for all eastmoney endpoints.
"""
import time, requests
from typing import Optional
import pandas as pd

EASTMONEY_LIST = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_ZT = "https://push2.eastmoney.com/api/qt/clist/get"
SESSION = None


def _get_session():
    """Create a fresh session each time — eastmoney tracks sessions."""
    s = requests.Session()
    s.trust_env = False
    s.headers.update({
        "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/{hash(str(time.time()))%10000}.0",
        "Referer": "https://quote.eastmoney.com/",
    })
    return s


def _safe_get(url, params, timeout=15, max_retries=3):
    for attempt in range(max_retries):
        s = _get_session()  # fresh session each attempt
        try:
            # Random delay to avoid rate limiting (1.5-4.5s between calls)
            delay = 1.5 + (hash(str(time.time())) % 3000) / 1000
            time.sleep(delay)
            r = s.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(3 * (2 ** attempt))
        finally:
            s.close()
    return None


def get_stock_list(page_size: int = 100) -> Optional[pd.DataFrame]:
    """Fetch all A-share stocks with realtime quotes (replaces akshare.stock_zh_a_spot_em)."""
    params = {
        "pn": 1, "pz": page_size, "po": 1, "np": 1, "fltt": 2, "invt": 2,
        "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f2,f3,f8,f9,f10,f12,f14,f15,f20,f21"
    }
    data = _safe_get(EASTMONEY_LIST, params)
    if data and "data" in data and data["data"]:
        total = data["data"]["total"]
        rows = data["data"]["diff"]
        # Map fields
        result = []
        for r in rows:
            result.append({
                "ticker": r.get("f12", ""),
                "name": r.get("f14", ""),
                "price": r.get("f2", 0),
                "change_pct": r.get("f3", 0),
                "turnover": r.get("f8", 0),
                "pe_ttm": r.get("f9", 0),
                "float_cap": r.get("f20", 0),
                "vol_ratio": r.get("f10", 0),
            })
        return pd.DataFrame(result)
    return None


def get_industry_sectors() -> Optional[pd.DataFrame]:
    """Fetch industry sector list with performance data."""
    params = {
        "pn": 1, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2,
        "fid": "f3", "fs": "m:90+t:2",
        "fields": "f2,f3,f4,f12,f14"
    }
    data = _safe_get(EASTMONEY_LIST, params)
    if data and "data" in data and data["data"]:
        rows = data["data"]["diff"]
        result = []
        for r in rows:
            result.append({
                "code": r.get("f12", ""),
                "name": r.get("f14", ""),
                "change_pct": r.get("f3", 0),
            })
        return pd.DataFrame(result)
    return None


def get_sector_constituents(sector_code: str) -> Optional[pd.DataFrame]:
    """Fetch stocks in a given industry sector."""
    params = {
        "pn": 1, "pz": 200, "po": 1, "np": 1, "fltt": 2, "invt": 2,
        "fid": "f3", "fs": f"b:{sector_code}+f:!50",
        "fields": "f2,f3,f12,f14"
    }
    data = _safe_get(EASTMONEY_LIST, params)
    if data and "data" in data and data["data"]:
        rows = data["data"]["diff"]
        result = []
        for r in rows:
            result.append({
                "ticker": r.get("f12", ""),
                "name": r.get("f14", ""),
                "change_pct": r.get("f3", 0),
            })
        return pd.DataFrame(result)
    return None


def get_limit_up_pool(date_str: str = None) -> Optional[pd.DataFrame]:
    """Fetch limit-up stocks pool."""
    params = {
        "pn": 1, "pz": 200, "po": 1, "np": 1, "fltt": 2, "invt": 2,
        "fid": "f3",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23" if not date_str else f"m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f2,f3,f4,f12,f14"
    }
    data = _safe_get(EASTMONEY_ZT, params)
    if data and "data" in data and data["data"]:
        rows = data["data"]["diff"]
        result = []
        for r in rows:
            change = r.get("f3", 0)
            if isinstance(change, (int, float)) and change > 9.5:
                result.append({
                    "ticker": r.get("f12", ""),
                    "name": r.get("f14", ""),
                    "change_pct": change,
                })
        return pd.DataFrame(result)
    return None


def _get_tencent_quote(ticker: str) -> dict:
    """Fallback: fetch real-time quote from Tencent (qt.gtimg.cn).

    Tencent API returns a text line like:
        v_sh600519="1~贵州茅台~600519~1800.00~1790.00~..."
    Field indices (0-based, split by ~):
        0:market  1:name  2:code  3:price  4:prev_close  5:open
        6:volume(lots)  9:bid  19:ask  31:high?  32:low?
        Actually: 3=price, 4=prev_close, 5=open, 33=high, 34=low,
        6=volume, 37=turnover%, 38=change%, 43=amplitude%
    """
    prefix = 'sh' if ticker.startswith(('6', '9')) else 'sz'
    url = f'https://sqt.gtimg.cn/utf8/q={prefix}{ticker}'
    try:
        r = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Referer': 'https://gu.qq.com/',
        })
        r.encoding = 'utf-8'  # Force utf-8 since URL already specifies it
        if r.status_code == 200 and r.text and '~' in r.text:
            # Parse: v_sh600519="1~name~code~price~prev_close~open~..."
            parts = r.text.split('"')[1].split('~') if '"' in r.text else r.text.split('~')
            if len(parts) >= 44:
                # Field map (0-based): 3=price, 4=prev_close, 5=open, 6=volume(lots),
                #   31=change_amt, 32=change_pct%, 33=high, 34=low,
                #   37=amount(万), 38=turnover%, 39=PE, 43=amplitude%
                return {
                    'name': parts[1] if parts[1] else '',
                    'price': float(parts[3]) if parts[3] else 0,
                    'open': float(parts[5]) if parts[5] else 0,
                    'high': float(parts[33]) if parts[33] else 0,
                    'low': float(parts[34]) if parts[34] else 0,
                    'prev_close': float(parts[4]) if parts[4] else 0,
                    'change_pct': float(parts[32]) if parts[32] else 0,
                    'volume': float(parts[6]) * 100 if parts[6] else 0,  # lots→shares
                    'amount': float(parts[37]) * 10000 if parts[37] else 0,  # 万→元
                    'turnover': float(parts[38]) if parts[38] else 0,  # %
                    'vol_ratio': 0,  # Not available in Tencent feed
                    'amplitude': float(parts[43]) if parts[43] else 0,
                    '_source': 'tencent',
                }
    except Exception:
        pass
    return {}


def get_realtime_quote(ticker: str) -> dict:
    """
    Fetch real-time intraday quote for a single stock.
    Primary: eastmoney push2 API. Fallback: Tencent qt.gtimg.cn.
    Returns dict with: price, open, high, low, prev_close, change_pct,
                       volume, amount, turnover, vol_ratio, amplitude
    """
    s = _get_session()
    prefix = '1' if ticker.startswith(('6', '9')) else '0'
    secid = f'{prefix}.{ticker}'
    params = {
        'secid': secid,
        'fields': 'f43,f44,f45,f46,f47,f48,f50,f57,f58,f60,f116,f117,f162,f168,f169,f170,f171',
    }
    try:
        r = s.get('https://push2.eastmoney.com/api/qt/stock/get', params=params, timeout=10)
        if r.status_code == 200:
            d = r.json().get('data', {})
            if d:
                return {
                    'price': d.get('f43', 0) / 100,
                    'open': d.get('f46', 0) / 100,
                    'high': d.get('f44', 0) / 100,
                    'low': d.get('f45', 0) / 100,
                    'prev_close': d.get('f60', 0) / 100,
                    'change_pct': d.get('f170', 0) / 100,
                    'volume': d.get('f47', 0),
                    'amount': d.get('f48', 0),
                    'turnover': d.get('f168', 0) / 100,
                    'vol_ratio': d.get('f50', 0) / 100,
                    'amplitude': d.get('f171', 0) / 100,
                    '_source': 'eastmoney',
                }
    except Exception:
        pass

    # Fallback: Tencent
    tencent_result = _get_tencent_quote(ticker)
    if tencent_result:
        return tencent_result

    return {}


if __name__ == "__main__":
    print("Test 1: Stock list...")
    df = get_stock_list()
    if df is not None:
        print(f"  {len(df)} stocks")
        print(df.head(3))
    else:
        print("  FAILED")

    print("\nTest 2: Industry sectors...")
    sec = get_industry_sectors()
    if sec is not None:
        print(f"  {len(sec)} sectors")
        print(sec.head(3))
    else:
        print("  FAILED")
