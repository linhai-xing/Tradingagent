"""
Extract CPO/Semiconductor/PCB stocks from baostock industry classification.
"""
import sys, os, json
import baostock as bs

bs.login()

# Get industry classification
rs = bs.query_stock_industry()
stocks_by_industry = {}
total = 0
while (rs.error_code == '0') & rs.next():
    row = rs.get_row_data()
    # row[0]: code (e.g., "sh.600000"), row[1]: industry name, row[2]: industry code
    code = row[0].split('.')[-1]  # extract ticker from "sh.600000"
    industry = row[1]
    if industry not in stocks_by_industry:
        stocks_by_industry[industry] = []
    stocks_by_industry[industry].append(code)
    total += 1

bs.logout()
print(f'Total classified: {total} stocks')
print(f'Unique industries: {len(stocks_by_industry)}')

# Find relevant industries
keywords = ['半导体', '芯片', '电子', '元器件', 'PCB', '光学', '光电', '通信设备',
            '软件', 'IT', '互联网', '计算机', 'AI', '人工智能', '封裝', '封装',
            '传感器', '电路', '组件', '模组', '模塊', '存储', 'Memory', '晶圆',
            '材料', '设备', '消费电子', '汽车电子']

print(f'\n{"="*60}')
print(f'Relevant industries (matching keywords):')
print(f'{"="*60}')

all_relevant_stocks = set()
for industry in sorted(stocks_by_industry.keys()):
    for kw in keywords:
        if kw.lower() in industry.lower():
            tickers = stocks_by_industry[industry]
            print(f'  {industry}: {len(tickers)} stocks')
            all_relevant_stocks.update(tickers)
            break

print(f'\nTotal unique stocks across relevant industries: {len(all_relevant_stocks)}')

# Also find specific sector stocks our pool is missing
current_pool = {
    '300308','300502','300394','002281','000988','300570','300620','300548',
    '688048','688498','688608','688595','688313','300757','603083',
    '002371','688012','688082','688120','688072','688037','688200','688596',
    '300604','300666','603690','688559','688138','300456',
    '603501','603986','002049','300782','300661','688256','688521','688536',
    '688099','688110','688766','300458','300672','688018','688019',
    '002079','300223','603160','688368','300327','603893',
    '600584','002156','002185','688981','600703','600460','603005',
    '688396','605358','603290','688187','300623','605111',
    '002916','002463','002938','002436','603228','300476','002384',
    '603920','002579','300657','300735','603186','688183','300852',
    '600601','002134','300739','603989','300632','600522',
    '002409','300236','300346','300102','300708','002129',
    '600171','300576','688300','300684','603650',
    '688041','300474','603019','600667','300212',
    '000725','002456','300433',
    '300373','300613','300476','603228','603386','002579','300739',
    '002134','603920','603989','300852','002552','300686','688020',
}

# Show tickers NOT in current pool
missing = all_relevant_stocks - current_pool
print(f'\nNew stocks not in current pool: {len(missing)}')
print(f'Sample: {sorted(list(missing))[:30]}')

# Show categorization
print(f'\n{"="*60}')
print(f'Industry breakdown:')
for ind in sorted(stocks_by_industry.keys()):
    for kw in keywords:
        if kw.lower() in ind.lower():
            tickers = stocks_by_industry[ind]
            # Show which are new
            new = set(tickers) - current_pool
            if new:
                print(f'  {ind} ({len(tickers)}): {len(new)} new - {sorted(list(new))[:10]}...')
            break

print(f'\nDone.')
