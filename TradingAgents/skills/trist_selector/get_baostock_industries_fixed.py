"""
Fix: baostock industry classification - column index was wrong.
Row format: [date, code, stock_name, industry_name, industry_classification_code]
"""
import baostock as bs

bs.login()
rs = bs.query_stock_industry()

stocks_by_industry = {}
total = 0
while (rs.error_code == '0') & rs.next():
    row = rs.get_row_data()  # [date, code, stock_name, industry_name, classification]
    ticker = row[1].split('.')[-1]  # sh.600000 -> 600000
    industry = row[3]               # industry name is col 3
    stock_name = row[2]

    if not industry:
        continue

    if industry not in stocks_by_industry:
        stocks_by_industry[industry] = []
    stocks_by_industry[industry].append((ticker, stock_name))
    total += 1

bs.logout()

print(f'Total classified stocks: {total}')
print(f'Unique industries: {len(stocks_by_industry)}')

# Show all industry names
print(f'\nAll industries (sorted):')
for ind in sorted(stocks_by_industry.keys()):
    print(f'  {ind}: {len(stocks_by_industry[ind])} stocks')

# Now match keywords for our sectors
keywords = ['半导体', '芯片', '电子', '元器件', 'PCB', '光学', '光电', '通信',
            '软件', 'IT', '互联网', '计算机', 'AI', '人工智能', '封裝', '封装',
            '传感器', '电路', '组件', '模组', '模塊', '存储', '晶圆',
            '材料', '设备', '消费电子', '汽车电子', '元件']

print(f'\n{"="*60}')
print(f'Matched industries:')
print(f'{"="*60}')
all_matched = set()
for ind in sorted(stocks_by_industry.keys()):
    for kw in keywords:
        if kw in ind:
            tickers = [t for t, n in stocks_by_industry[ind]]
            print(f'  [{kw}] {ind}: {len(tickers)} stocks')
            print(f'    {", ".join(tickers[:15])}')
            if len(tickers) > 15:
                print(f'    ... and {len(tickers)-15} more')
            all_matched.update(tickers)
            break

print(f'\nTotal matched stocks: {len(all_matched)}')

# Save to file for use
with open(r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector\baostock_sector_stocks.json', 'w', encoding='utf-8') as f:
    json.dump({
        'total': total,
        'total_matched': len(all_matched),
        'matched_stocks': sorted(list(all_matched)),
        'industries': {ind: [t for t,n in stocks] for ind, stocks in stocks_by_industry.items()}
    }, f, ensure_ascii=False, indent=2)

print(f'\nSaved to baostock_sector_stocks.json')
