"""Test real-time quotes via eastmoney API."""
import requests, time

s = requests.Session(); s.trust_env = False
url = 'https://push2.eastmoney.com/api/qt/stock/get'

# Test 3 stocks: 中天科技, 太极实业, 长电科技
stocks = [
    ('600522', '中天科技'),
    ('600667', '太极实业'),
    ('600584', '长电科技'),
]

for ticker, name in stocks:
    secid = f'1.{ticker}' if ticker.startswith('6') else f'0.{ticker}'
    params = {
        'secid': secid,
        'fields': 'f43,f44,f45,f46,f48,f50,f57,f58,f60,f116,f117,f162,f168,f169,f170,f171',
    }
    r = s.get(url, params=params, timeout=10)
    d = r.json()['data']

    # eastmoney fields: price in original unit, percentage fields in 0.01% units
    raw_price = d.get('f43', 0)
    price = raw_price / 100 if raw_price > 10000 else raw_price  # auto-detect scale
    high = d.get('f44', 0) / 100 if d.get('f44', 0) > 10000 else d.get('f44', 0)
    low = d.get('f45', 0) / 100 if d.get('f45', 0) > 10000 else d.get('f45', 0)
    open_p = d.get('f46', 0) / 100 if d.get('f46', 0) > 10000 else d.get('f46', 0)
    amount = d.get('f48', 0)
    prev_close = d.get('f60', 0) / 100 if d.get('f60', 0) > 100 else d.get('f60', 0)
    change_pct = d.get('f170', 0) / 100
    turnover = d.get('f168', 0) / 100
    vol_ratio = d.get('f50', 0) / 100
    amplitude = d.get('f171', 0) / 100
    f43_raw = d.get('f43', 0)
    f60_raw = d.get('f60', 0)
    print(f'  [RAW f43={f43_raw}, f60={f60_raw}, f170={d.get("f170",0)}]')

    print(f'{name} ({ticker})')
    print(f'  现价: {price:.2f} | 涨跌: {change_pct:+.2f}%')
    print(f'  今开: {open_p:.2f} | 最高: {high:.2f} | 最低: {low:.2f} | 昨收: {prev_close:.2f}')
    print(f'  成交额: {amount:.2f}亿 | 换手: {turnover:.2f}% | 量比: {vol_ratio:.2f} | 振幅: {amplitude:.2f}%')
    print()
    time.sleep(1)

print(f'数据更新时间: {time.strftime("%Y-%m-%d %H:%M:%S")}')
print(f'数据来源: eastmoney push2 实时API (无代理直连)')
