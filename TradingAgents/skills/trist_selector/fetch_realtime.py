"""Fetch real-time prices from Sina for 600460 + semiconductor peers."""
import requests

codes = {
    'sh600460': '士兰微',
    'sh688981': '中芯国际',
    'sh688012': '中微公司',
    'sz002371': '北方华创',
    'sh688008': '澜起科技',
    'sh688396': '华润微',
    'sh688126': '沪硅产业',
    'sh603986': '兆易创新',
    'sh688536': '思瑞浦',
    'sz002049': '紫光国微',
}
url = 'http://hq.sinajs.cn/list=' + ','.join(codes.keys())
headers = {'Referer': 'https://finance.sina.com.cn'}
try:
    r = requests.get(url, headers=headers, timeout=10)
    r.encoding = 'gbk'
    print('=== 半导体板块 最新价格 (Sina实时) ===')
    for line in r.text.strip().split('\n'):
        if '=' in line:
            name_part = line.split('=')[0].split('_')[-1]
            data = line.split('"')[1].split(',')
            if len(data) > 30:
                price = float(data[3])
                prev_close = float(data[2])
                high = float(data[4])
                low = float(data[5])
                open_p = float(data[1])
                chg_pct = (price - prev_close) / prev_close * 100 if prev_close != 0 else 0
                name = codes.get(name_part, name_part)
                print(f'{name:<10} 现价:{price:<10.2f} 昨收:{prev_close:<10.2f} 涨幅:{chg_pct:+.2f}%  今开:{open_p:.2f} 高:{high:.2f} 低:{low:.2f}')
except Exception as e:
    print(f'Sina failed: {e}')

# Also try eastmoney for more detail on 600460
try:
    url2 = 'https://push2.eastmoney.com/api/qt/stock/get?secid=1.600460&fields=f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f60,f116,f117,f162,f167,f168,f169,f170,f171'
    r2 = requests.get(url2, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
    data = r2.json().get('data', {})
    if data:
        print(f'\n=== 士兰微 600460 详细 (Eastmoney) ===')
        print(f'现价: {data.get("f43",0)/100:.2f}')
        print(f'昨收: {data.get("f60",0)/100:.2f}')
        print(f'最高: {data.get("f44",0)/100:.2f}')
        print(f'最低: {data.get("f45",0)/100:.2f}')
        print(f'今开: {data.get("f46",0)/100:.2f}')
        print(f'成交量: {data.get("f47",0)}')
        print(f'成交额: {data.get("f48",0)}')
        print(f'换手率: {data.get("f168",0)/100:.2f}%')
        print(f'量比: {data.get("f50",0)/100:.2f}')
        print(f'市盈率: {data.get("f162",0)/100:.2f}')
        print(f'总市值: {data.get("f116",0)}')
        print(f'流通市值: {data.get("f117",0)}')
except Exception as e:
    print(f'Eastmoney failed: {e}')
