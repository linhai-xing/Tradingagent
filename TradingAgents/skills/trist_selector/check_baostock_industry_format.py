"""
Check baostock industry format.
"""
import baostock as bs

bs.login()
rs = bs.query_stock_industry()

samples = []
total = 0
while (rs.error_code == '0') & rs.next():
    row = rs.get_row_data()
    if total < 30:
        samples.append(row)
    total += 1

bs.logout()

print(f'Total: {total} rows')
print(f'\nFirst 20 samples (code, industry_name, industry_code):')
for s in samples[:20]:
    print(f'  {s}')

# Check unique industry names
bs.login()
rs2 = bs.query_stock_industry()
industries = set()
while (rs2.error_code == '0') & rs2.next():
    row = rs2.get_row_data()
    industries.add(row[1])
bs.logout()

print(f'\nUnique industry names: {len(industries)}')
print(f'Sample industry names:')
for ind in sorted(list(industries))[:30]:
    print(f'  "{ind}"')

# Look for semiconductor-related
print(f'\nIndustries containing "半":')
for ind in sorted(list(industries)):
    if '半' in ind:
        print(f'  "{ind}"')

print(f'\nIndustries containing "芯":')
for ind in sorted(list(industries)):
    if '芯' in ind:
        print(f'  "{ind}"')

print(f'\nIndustries containing "电":')
for ind in sorted(list(industries)):
    if '电' in ind:
        print(f'  "{ind}"')
