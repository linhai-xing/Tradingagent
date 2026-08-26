#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
获取行情数据的统一入口，带 fallback 链：baostock → akshare → Tushare

用法：
    python fetch_market_data.py --ts_code 000001.SZ --output data.csv
    python fetch_market_data.py --ts_code 000001.SZ --start_date 20240101 --end_date 20240614

导入复用：
    from fetch_market_data import fetch_kline, get_kline_dataframe

依赖：
    pip install baostock akshare tushare pandas
"""
import argparse
import os
import pandas as pd
from datetime import datetime, timedelta


def _normalize_ticker(ticker: str) -> str:
    """统一 ticker 格式：去掉 .SZ/.SH/.BJ 后缀"""
    return ticker.upper().replace(".SZ", "").replace(".SH", "").replace(".BJ", "")


# ── 数据源实现 ─────────────────────────────────────────────

def _baostock_kline(ticker: str, start: str, end: str, freq: str) -> pd.DataFrame:
    """baostock 获取 K 线"""
    import baostock as bs
    prefix = "sh." if ticker.startswith(("6", "9")) else "sz."
    bs_code = prefix + ticker

    bs.login()
    rs = bs.query_history_k_data_plus(
        bs_code,
        "date,open,high,low,close,volume,amount",
        start_date=start, end_date=end,
        frequency=freq, adjustflag="2"
    )
    rows = []
    while (rs.error_code == '0') and rs.next():
        rows.append(rs.get_row_data())
    bs.logout()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["trade_date", "open", "high", "low", "close", "vol", "amount"])
    for c in ["open", "high", "low", "close", "vol", "amount"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df.sort_values("trade_date").reset_index(drop=True)


def _akshare_kline(ticker: str, start: str, end: str) -> pd.DataFrame:
    """akshare 获取 K 线"""
    import akshare as ak
    freq_map = {"d": "daily", "w": "weekly", "m": "monthly"}
    period = freq_map.get(start, "daily")

    df = ak.stock_zh_a_hist(
        symbol=ticker,
        period=period,
        start_date=start,
        end_date=end,
        adjust="qfq"
    )
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.rename(columns={
        "日期": "trade_date", "开盘": "open", "最高": "high",
        "最低": "low", "收盘": "close", "成交量": "vol", "成交额": "amount"
    })
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    for c in ["open", "high", "low", "close", "vol", "amount"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values("trade_date").reset_index(drop=True)

    # 筛选日期范围（akshare 的 start_date/end_date 参数不一定严格过滤）
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    df = df[(df["trade_date"] >= start_dt) & (df["trade_date"] <= end_dt)]
    return df


def _tushare_kline(ticker: str, start: str, end: str, token: str = None) -> pd.DataFrame:
    """Tushare 获取 K 线"""
    import tushare as ts
    # 优先用传入的 token，其次读环境变量
    tk = token or os.environ.get("TUSHARE_TOKEN")
    if not tk:
        raise ValueError("Tushare token 未设置，请通过 --token 传入或设置 TUSHARE_TOKEN 环境变量")

    # 确定 ts_code 格式
    if ticker.startswith(("6", "9")):
        ts_code = f"{ticker}.SH"
    else:
        ts_code = f"{ticker}.SZ"

    pro = ts.pro_api(tk)
    df = pro.daily(ts_code=ts_code, start_date=start, end_date=end)
    if df is None or df.empty:
        return pd.DataFrame()

    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"])
    for c in ["open", "high", "low", "close", "vol", "amount"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("trade_date").reset_index(drop=True)


# ── 统一入口 ─────────────────────────────────────────────

FETCH_ORDER = [
    ("baostock", _baostock_kline),
    ("akshare", _akshare_kline),
    ("tushare", _tushare_kline),
]


def fetch_kline(ticker: str, start_date: str = "20200101", end_date: str = None,
                freq: str = "d", tushare_token: str = None) -> pd.DataFrame:
    """
    获取 K 线数据，自动 fallback：baostock → akshare → Tushare

    参数：
        ticker: 股票代码，如 "000001" 或 "000001.SZ"
        start_date: 开始日期，格式 YYYYMMDD
        end_date: 结束日期，格式 YYYYMMDD，默认今天
        freq: 周期，"d"=日线, "w"=周线, "m"=月线
        tushare_token: Tushare API token（仅在 baostock 和 akshare 都失败时需要）

    返回：
        DataFrame 包含: trade_date, open, high, low, close, vol, amount
    """
    ticker = _normalize_ticker(ticker)
    # baostock 需要 YYYY-MM-DD，akshare 和 Tushare 接受 YYYYMMDD
    start_raw = start_date.replace("-", "")
    end_raw = (end_date or datetime.now().strftime("%Y%m%d")).replace("-", "")
    start_hyphen = f"{start_raw[:4]}-{start_raw[4:6]}-{start_raw[6:]}"
    end_hyphen = f"{end_raw[:4]}-{end_raw[4:6]}-{end_raw[6:]}"

    errors = []
    for name, fetcher in FETCH_ORDER:
        try:
            if name == "baostock":
                df = fetcher(ticker, start_hyphen, end_hyphen, freq)
            elif name == "tushare":
                df = fetcher(ticker, start_raw, end_raw, token=tushare_token)
            else:
                df = fetcher(ticker, start_raw, end_raw)
            if df is not None and not df.empty:
                return df
            errors.append(f"{name}: 返回空数据")
        except Exception as e:
            errors.append(f"{name}: {e}")
            continue

    raise RuntimeError(f"所有数据源均无法获取 {ticker} 的数据:\n" + "\n".join(errors))


def get_kline_dataframe(ticker: str, days: int = 365, freq: str = "d",
                        tushare_token: str = None) -> pd.DataFrame:
    """获取最近 N 天的 K 线数据"""
    end = datetime.now()
    start = end - timedelta(days=days)
    return fetch_kline(ticker, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), freq, tushare_token)


def main():
    parser = argparse.ArgumentParser(description='获取股票行情数据（baostock → akshare → Tushare 自动 fallback）')
    parser.add_argument('--ts_code', type=str, help='股票代码，如 000001.SZ 或 000001')
    parser.add_argument('--token', type=str, default=None, help='Tushare API token（仅当前两者失败时使用）')
    parser.add_argument('--start_date', type=str, help='开始日期，格式 YYYYMMDD')
    parser.add_argument('--end_date', type=str, help='结束日期，格式 YYYYMMDD')
    parser.add_argument('--days', type=int, default=365, help='回溯天数（未指定起止日期时使用）')
    parser.add_argument('--output', type=str, help='输出 CSV 文件路径')
    parser.add_argument('--freq', type=str, default='d', help='周期：d=日线 w=周线 m=月线')
    parser.add_argument('--list_stocks', action='store_true', help='列出 baostock 所有 A 股基本信息')

    args = parser.parse_args()

    if args.list_stocks:
        import baostock as bs
        bs.login()
        rs = bs.query_stock_basic()
        rows = []
        while (rs.error_code == '0') and rs.next():
            rows.append(rs.get_row_data())
        bs.logout()
        df = pd.DataFrame(rows, columns=["ticker", "name", "ipo_date", "status", "type"])
        df = df[df["type"] == "1"]
        print(f"A 股数量: {len(df)}")
        print(df[["ticker", "name", "ipo_date"]].head(10))
        if args.output:
            df.to_csv(args.output, index=False, encoding='utf-8-sig')
            print(f"已保存到 {args.output}")
        return

    if not args.ts_code:
        parser.print_help()
        return

    if args.start_date and args.end_date:
        start, end = args.start_date, args.end_date
    else:
        end = datetime.now()
        start = end - timedelta(days=args.days)
        start, end = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")

    print(f"正在获取 {args.ts_code} {start} ~ {end} 数据...")
    try:
        df = fetch_kline(args.ts_code, start, end, freq=args.freq, tushare_token=args.token)
        print(f"成功获取 {len(df)} 条记录")
        print(f"数据范围：{df['trade_date'].min().strftime('%Y-%m-%d')} 到 {df['trade_date'].max().strftime('%Y-%m-%d')}")

        if args.output:
            df_out = df.copy()
            df_out["trade_date"] = df_out["trade_date"].dt.strftime("%Y%m%d")
            df_out.to_csv(args.output, index=False, encoding='utf-8-sig')
            print(f"数据已保存到 {args.output}")
        else:
            print("\n数据预览：")
            print(df.head())
    except RuntimeError as e:
        print(f"获取失败：{e}")
        return 1


if __name__ == '__main__':
    main()
