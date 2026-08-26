#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
一键缠论分析：输入股票代码 → 自动获取 K 线 → 结构分析 + 买卖点信号

与 trist-selector 配合使用：
    trist-selector 选股 → 此脚本做缠论技术分析 → 综合报告

用法：
    python analyze_from_trist.py 600522
    python analyze_from_trist.py 000001.SZ --days 365
    python analyze_from_trist.py 600522 --token your_tushare_token  # Tushare 兜底
"""
import argparse
import sys
import os
from datetime import datetime, timedelta

# Windows 控制台 UTF-8 编码适配
if sys.platform == "win32" and sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 确保同级目录可导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetch_market_data import fetch_kline
from analyze_czsc_structure import convert_to_raw_bars, analyze_structure
from signal_analysis import analyze_buy_sell_points, analyze_divergence, analyze_trend
from czsc import CZSC


def run_full_analysis(ticker: str, days: int = 365, freq: str = "d",
                      tushare_token: str = None, max_bi: int = 20):
    """
    完整缠论分析流程：获取数据 → 结构分析 → 买卖点 → 背驰 → 趋势

    参数：
        ticker: 股票代码
        days: 回溯天数
        freq: 周期
        tushare_token: Tushare token（可选兜底）
        max_bi: 最大笔数

    返回：
        CZSC 对象（可用于后续程序化分析）
    """
    print("=" * 60)
    print(f"  缠论分析：{ticker}")
    print("=" * 60)

    # Step 1: 获取数据
    print(f"\n[1/3] 获取 {ticker} 最近 {days} 天 K 线数据...")
    end = datetime.now()
    start = end - timedelta(days=days)
    df = fetch_kline(ticker, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"),
                     freq=freq, tushare_token=tushare_token)
    print(f"  -> 获取到 {len(df)} 条 K 线 ({df['trade_date'].min().strftime('%Y-%m-%d')} ~ {df['trade_date'].max().strftime('%Y-%m-%d')})")

    # Step 2: 缠论结构分析
    print(f"\n[2/3] 缠论结构分析...")
    raw_bars = convert_to_raw_bars(df, ticker)
    czsc_obj = CZSC(raw_bars, max_bi_num=max_bi)
    analyze_structure(czsc_obj)

    # Step 3: 买卖点信号分析
    print(f"\n[3/3] 买卖点信号分析...")
    analyze_buy_sell_points(czsc_obj)
    analyze_divergence(czsc_obj)
    analyze_trend(czsc_obj)

    print("\n" + "=" * 60)
    print("  分析完成")
    print("=" * 60)

    return czsc_obj


def main():
    parser = argparse.ArgumentParser(description='一键缠论分析（含数据获取）')
    parser.add_argument('ticker', type=str, help='股票代码，如 600522 或 000001.SZ')
    parser.add_argument('--days', type=int, default=365, help='回溯天数')
    parser.add_argument('--freq', type=str, default='d', help='周期：d=日线 w=周线 m=月线')
    parser.add_argument('--token', type=str, help='Tushare token（可选兜底）')
    parser.add_argument('--max_bi', type=int, default=20, help='最大笔数')

    args = parser.parse_args()
    run_full_analysis(args.ticker, args.days, args.freq, args.token, args.max_bi)


if __name__ == '__main__':
    main()
