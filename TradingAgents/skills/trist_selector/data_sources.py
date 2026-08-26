"""
Trist Selector v1.1 - External Data Sources
LHB (龙虎榜), Research Reports (B3), Financial Data (B5), Sector Classification
"""
import noproxy  # MUST be first

import time, json, os
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")


def fetch_lhb_recent(days: int = 5) -> dict:
    """
    BONUS: Fetch recent LHB (龙虎榜) data.
    Returns {ticker: {net_buy, top_seats, institution_participation}}
    """
    try:
        import akshare as ak
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        result = {}
        # Try to get LHB detail for each day
        for d in pd.date_range(start, end, freq="B"):
            date_str = d.strftime("%Y%m%d")
            try:
                df = ak.stock_lhb_stock_detail_date_em(date=date_str)
                if df is not None and len(df) > 0:
                    for _, row in df.iterrows():
                        ticker = str(row.get("代码", "")).zfill(6)
                        if ticker not in result:
                            result[ticker] = {"dates": [], "net_buy": 0, "top_seats": [], "has_institution": False}
                        entry = result[ticker]
                        entry["dates"].append(date_str)
                        entry["net_buy"] += float(row.get("净买额", 0) or 0)
                        seat = str(row.get("营业部名称", ""))
                        if seat:
                            entry["top_seats"].append(seat)
                        if "机构" in seat:
                            entry["has_institution"] = True
                time.sleep(0.3)
            except Exception:
                pass
        print(f"  LHB: {len(result)} stocks with recent activity")
        return result
    except Exception as e:
        print(f"  LHB: unavailable ({e})")
        return {}


def fetch_research_reports(ticker: str = None, days: int = 30) -> dict:
    """
    B3: Fetch recent research reports.
    Returns {ticker: {buy_count, total_count, target_price_avg}}
    """
    try:
        import akshare as ak
        df = ak.stock_research_report_em()
        if df is None or len(df) == 0:
            return {}

        # Filter by date
        if "日期" in df.columns:
            df["日期"] = pd.to_datetime(df["日期"])
            cutoff = datetime.now() - timedelta(days=days)
            df = df[df["日期"] >= cutoff]

        result = defaultdict(lambda: {"buy_count": 0, "total_count": 0, "target_prices": [], "brokers": []})
        for _, row in df.iterrows():
            code = str(row.get("股票代码", "")).zfill(6)
            rating = str(row.get("评级", "") or row.get("研究机构评级", ""))
            target = row.get("目标价", None)

            r = result[code]
            r["total_count"] += 1
            if rating in ("买入", "增持", "推荐", "强烈推荐"):
                r["buy_count"] += 1
            if target and float(target) > 0:
                r["target_prices"].append(float(target))
            broker = str(row.get("研究机构", "") or row.get("券商", ""))
            if broker:
                r["brokers"].append(broker)

        # Finalize
        final = {}
        for code, r in result.items():
            final[code] = {
                "research_buy_count": r["buy_count"],
                "research_total_count": r["total_count"],
                "target_price_avg": round(np.mean(r["target_prices"]), 2) if r["target_prices"] else 0,
                "brokers": list(set(r["brokers"]))[:5],
            }
        print(f"  Research: {len(final)} stocks with recent reports")
        return final
    except Exception as e:
        print(f"  Research: unavailable ({e})")
        return {}


def fetch_financials_batch(tickers: list) -> dict:
    """
    B5: Fetch latest quarterly financial data.
    Returns {ticker: {net_profit_growth_yoy, roe, revenue_growth_yoy}}
    """
    try:
        import baostock as bs
        bs.login()
        result = {}

        for ticker in tickers[:100]:  # Limit batch size
            try:
                prefix = "sh." if ticker.startswith(("6", "9")) else "sz."
                code = prefix + ticker

                # Profit statement
                rs = bs.query_profit_data(code, year=2026, quarter=1)
                profit_rows = []
                while (rs.error_code == '0') & rs.next():
                    profit_rows.append(rs.get_row_data())

                # Growth indicators
                rs2 = bs.query_growth_data(code, year=2026, quarter=1)
                growth_rows = []
                while (rs2.error_code == '0') & rs2.next():
                    growth_rows.append(rs2.get_row_data())

                if profit_rows and growth_rows:
                    net_profit_growth = float(growth_rows[0][6]) / 100 if len(growth_rows[0]) > 6 else 0  # YOY net profit growth
                    revenue_growth = float(growth_rows[0][2]) / 100 if len(growth_rows[0]) > 2 else 0  # YOY revenue growth
                    roe = float(profit_rows[0][7]) if len(profit_rows[0]) > 7 else 0  # ROE

                    result[ticker] = {
                        "net_profit_growth_yoy": round(net_profit_growth, 4),
                        "revenue_growth_yoy": round(revenue_growth, 4),
                        "roe": round(roe, 2),
                    }
                time.sleep(0.05)
            except Exception:
                pass

        bs.logout()
        print(f"  Financials: {len(result)} stocks with Q1 2026 data")
        return result
    except Exception as e:
        print(f"  Financials: unavailable ({e})")
        return {}


def fetch_sector_classification() -> dict:
    """
    Map ticker -> sector name using akshare.
    Returns {ticker: sector_name}
    """
    try:
        import akshare as ak
        df = ak.stock_board_industry_name_em()
        sectors = df["板块名称"].tolist()

        mapping = {}
        for sector_name in sectors[:30]:  # limit API calls
            try:
                cons = ak.stock_board_industry_cons_em(symbol=sector_name)
                for _, row in cons.iterrows():
                    code = str(row.get("代码", "")).zfill(6)
                    if code not in mapping:
                        mapping[code] = sector_name
                time.sleep(0.3)
            except Exception:
                pass

        print(f"  Sectors: {len(mapping)} tickers classified into {len(sectors)} sectors")
        return mapping
    except Exception as e:
        print(f"  Sectors: unavailable ({e})")
        return {}


def enhance_stock_data(stock_data: dict, lhb_data: dict, research_data: dict,
                       financials: dict, sectors: dict) -> dict:
    """Merge external data into stock_data dict."""
    ticker = stock_data.get("ticker", "")

    # LHB
    if ticker in lhb_data:
        lhb = lhb_data[ticker]
        stock_data["lhb_net_buy"] = lhb.get("net_buy", 0)
        stock_data["lhb_has_institution"] = lhb.get("has_institution", False)
        stock_data["lhb_top_seats"] = lhb.get("top_seats", [])[:3]

    # Research
    if ticker in research_data:
        r = research_data[ticker]
        stock_data["research_buy_count"] = r.get("research_buy_count", 0)
        stock_data["research_total_count"] = r.get("research_total_count", 0)
        stock_data["target_price_avg"] = r.get("target_price_avg", 0)

    # Financials
    if ticker in financials:
        fin = financials[ticker]
        stock_data["net_profit_growth_yoy"] = fin.get("net_profit_growth_yoy", 0)
        stock_data["revenue_growth_yoy"] = fin.get("revenue_growth_yoy", 0)
        stock_data["roe"] = fin.get("roe", 0)

    # Sector
    if ticker in sectors:
        stock_data["sector"] = sectors[ticker]

    return stock_data
