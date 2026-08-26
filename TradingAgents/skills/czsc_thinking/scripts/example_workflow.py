#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
示例：完整的缠论分析流程演示（自动 fallback: baostock -> akshare -> Tushare）

使用方法：
    python example_workflow.py --ts_code 000001.SZ
    python example_workflow.py --ts_code 000001.SZ --days 180
    python example_workflow.py --ts_code 000001.SZ --token your_tushare_token
"""
import argparse
import os
import sys
from datetime import datetime, timedelta


def run_command(cmd):
    print(f"\n{'=' * 60}")
    print(f"执行命令: {cmd}")
    print(f"{'=' * 60}")
    result = os.system(cmd)
    if result != 0:
        print(f"命令执行失败: {cmd}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='缠论分析完整流程演示')
    parser.add_argument('--token', type=str, help='Tushare token（可选，兜底用）')
    parser.add_argument('--ts_code', type=str, default='000001.SZ', help='股票代码')
    parser.add_argument('--days', type=int, default=180, help='数据天数')

    args = parser.parse_args()

    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    start_s, end_s = start_date.strftime('%Y%m%d'), end_date.strftime('%Y%m%d')
    output_file = f"{args.ts_code.replace('.', '_')}_data.csv"

    print("\n" + "=" * 60)
    print("缠论分析完整流程演示")
    print("=" * 60)
    print(f"股票代码: {args.ts_code}")
    print(f"数据范围: {start_s} - {end_s}")

    # 步骤 1
    print("\n\n步骤 1/3: 获取行情数据")
    tk = f"--token {args.token}" if args.token else ""
    run_command(f"python fetch_market_data.py --ts_code {args.ts_code} {tk} "
                f"--start_date {start_s} --end_date {end_s} --output {output_file}")

    # 步骤 2
    print("\n\n步骤 2/3: 分析缠论结构")
    run_command(f"python analyze_czsc_structure.py --input {output_file} --symbol {args.ts_code}")

    # 步骤 3
    print("\n\n步骤 3/3: 分析买卖点信号")
    run_command(f"python signal_analysis.py --input {output_file} --symbol {args.ts_code}")

    print("\n\n" + "=" * 60)
    print("完整流程执行完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()
