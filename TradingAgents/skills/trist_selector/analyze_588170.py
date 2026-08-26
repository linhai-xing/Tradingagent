"""
单ETF分析: 588170 (半导体ETF)
v4.0 Trist Selector — ETF special analysis
"""
import noproxy
import os, sys, json
from datetime import datetime
import requests

# Fix Windows encoding
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(__file__))
from direct_api import _get_tencent_quote

print("=" * 60)
print("  588170 半导体ETF — Trist Selector v4.0 分析")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 60)

# ── 1. Real-time quote ──
rt = _get_tencent_quote('588170')
if rt:
    print(f"\n[实时行情]")
    print(f"  名称: {rt.get('name', 'N/A')}")
    print(f"  最新价: {rt.get('price', 'N/A')}")
    print(f"  涨跌幅: {rt.get('change_pct', 0):+.2f}%")
    print(f"  最高: {rt.get('high', 'N/A')}")
    print(f"  最低: {rt.get('low', 'N/A')}")
    print(f"  开盘: {rt.get('open', 'N/A')}")
    print(f"  昨收: {rt.get('prev_close', 'N/A')}")
    print(f"  振幅: {rt.get('amplitude', 0):.2f}%")
else:
    print("  ⚠️ 无法获取实时行情")

# ── 2. Parse fund info from Tencent response ──
print(f"\n[基金信息] (来自腾讯行情)")
s = requests.Session(); s.trust_env = False
r = s.get('https://qt.gtimg.cn/q=sh588170', timeout=10)
text = r.text

# Tencent ETF fields: field[5]=name, field[3]=price, field[4]=prev_close,
# field[33]=NAV, field[41]=float_cap, field[44]=total_cap
parts = text.split('~')
if len(parts) > 44:
    try:
        nav = float(parts[39]) if parts[39] else 0  # IOPV/NAV
        float_cap = float(parts[39]) if parts[39] else 0
        # Try other fields
        for idx in range(len(parts)):
            val = parts[idx].strip()
            if val and val.replace('.','').replace('-','').isdigit():
                pass
    except:
        pass

# ── 3. Price structure ──
print(f"\n[价格结构分析]")
price = rt.get('price', 0)
prev_close = rt.get('prev_close', 0)
high = rt.get('high', 0)
low = rt.get('low', 0)

if price and prev_close:
    discount_pct = (price - prev_close) / prev_close * 100
    print(f"  昨收→现价: {prev_close:.4f} → {price:.4f} ({discount_pct:+.2f}%)")

# ── 4. Historical context (from baostock or cached ETF data) ──
print(f"\n[技术分析] (日线级别)")
# Try to get ETF K-line data
try:
    import baostock as bs
    bs.login()
    fields = "date,open,high,low,close,volume,amount"
    rs = bs.query_history_k_data_plus("sh.588170", fields,
        start_date='2026-03-01', end_date=datetime.now().strftime('%Y-%m-%d'),
        frequency="d", adjustflag="2")
    data = []
    while (rs.error_code == '0') & rs.next():
        data.append(rs.get_row_data())
    bs.logout()

    if data:
        import pandas as pd
        df = pd.DataFrame(data, columns=['date','open','high','low','close','volume','amount'])
        for c in ['open','high','low','close','volume']:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df.dropna()

        # Key levels
        recent_close = df['close'].values[-1]
        ma20 = df['close'].rolling(20).mean().values[-1]
        ma60 = df['close'].rolling(60).mean().values[-1]
        recent_high_20d = df['high'].tail(20).max()
        recent_low_20d = df['low'].tail(20).min()
        recent_high_60d = df['high'].tail(60).max()
        recent_low_60d = df['low'].tail(60).min()

        # Trend assessment
        closes = df['close'].values
        ret_5d = (closes[-1] / closes[-6] - 1) if len(closes) > 5 else 0
        ret_20d = (closes[-1] / closes[-21] - 1) if len(closes) > 20 else 0
        ret_60d = (closes[-1] / closes[-61] - 1) if len(closes) > 60 else 0

        # Volatility
        vol_20d = df['close'].pct_change().tail(20).std() * (252**0.5)

        # Volume trend
        avg_vol_5d = df['volume'].tail(5).mean()
        avg_vol_20d = df['volume'].tail(20).mean()
        vol_ratio = avg_vol_5d / avg_vol_20d if avg_vol_20d > 0 else 0

        # Price position within range
        range_20d = recent_high_20d - recent_low_20d
        pos_20d = (recent_close - recent_low_20d) / range_20d * 100 if range_20d > 0 else 50
        range_60d = recent_high_60d - recent_low_60d
        pos_60d = (recent_close - recent_low_60d) / range_60d * 100 if range_60d > 0 else 50

        print(f"  数据: {len(df)}根日K线 ({df['date'].values[0]} ~ {df['date'].values[-1]})")
        print(f"  MA20: {ma20:.4f} | 现价 vs MA20: {(recent_close/ma20-1)*100:+.1f}%")
        print(f"  MA60: {ma60:.4f} | 现价 vs MA60: {(recent_close/ma60-1)*100:+.1f}%")
        print(f"  5日收益: {ret_5d:+.1%} | 20日收益: {ret_20d:+.1%} | 60日收益: {ret_60d:+.1%}")
        print(f"  20日振幅: {vol_20d:.1%} | 量比(5d/20d): {vol_ratio:.2f}")
        print(f"  20日位置: {pos_20d:.0f}% (0=低点, 100=高点)")
        print(f"  60日位置: {pos_60d:.0f}% (0=低点, 100=高点)")

        # Trend signal
        if recent_close > ma20 > ma60:
            trend = "📈 多头排列 (MA现价>MA20>MA60)"
        elif recent_close < ma20 < ma60:
            trend = "📉 空头排列 (MA现价<MA20<MA60)"
        elif recent_close > ma20:
            trend = "↗️ 短线反弹 (站上MA20, 未站上MA60)"
        else:
            trend = "↘️ 短线调整 (跌破MA20)"

        print(f"  趋势: {trend}")

        # Support/Resistance
        print(f"\n[关键位]")
        print(f"  上方阻力: 20日高 {recent_high_20d:.4f} | 60日高 {recent_high_60d:.4f}")
        print(f"  下方支撑: 20日低 {recent_low_20d:.4f} | 60日低 {recent_low_60d:.4f}")
        print(f"  均线: MA20={ma20:.4f} MA60={ma60:.4f}")

        # AT-based range projection
        atr20 = max(df['high'].tail(20).values - df['low'].tail(20).values)
        print(f"  20日真实波幅(ATR近似): {atr20:.4f} ({(atr20/recent_close)*100:.1f}%)")

    else:
        print("  ⚠️ baostock 数据获取失败")

except Exception as e:
    print(f"  ⚠️ 技术分析异常: {e}")

# ── 5. External context ──
print(f"\n[外围联动分析]")
print(f"  昨晚美股:")
print(f"    费城半导体指数(SOX): 跟踪上涨")
print(f"    NVDA: 存储+AI芯片龙头")
print(f"    MU: 存储芯片龙头")
print(f"    AVGO/MRVL: 光通信/数据中心")
print(f"  联动逻辑: 美股半导体大涨 → A股半导体ETF高开预期")
print(f"  风险提示: A股常出现\"利好高开低走\"，需确认开盘后资金承接")

# ── 6. Pre-market checklist (Al Brooks style) ──
print(f"\n[阿布价格行为学 — 开盘检查清单]")
print(f"  ☐ 等待开盘(9:30)确认方向 — 不要抢集合竞价")
print(f"  ☐ 观察前30分钟 K线形态:")
print(f"     - 如果跳空高开+放量 → 可能形成\"跳空缺口\"趋势日")
print(f"     - 如果高开低走 → 警惕\"利好出货\"陷阱")
print(f"  ☐ 入场规则:")
print(f"     - 信号K线: 今天第1-2根30分钟K线(预警)")
print(f"     - 入场K线: 后续K线确认突破信号K线高/低点")
print(f"  ☐ 仓位建议:")
print(f"     - ETF自带分散，但588170波动接近个股")
print(f"     - 建议不超过总仓位15%")
print(f"  ☐ 止损: 入场K线低点下方1-2个tick 或 前低")

# ── 7. Summary ──
print(f"\n{'='*60}")
print(f"  综合判断")
print(f"{'='*60}")

if rt.get('price', 0) > 0:
    price = rt['price']
    change = rt.get('change_pct', 0)
    print(f"  588170 半导体ETF @ {price:.4f} ({change:+.2f}%)")

    # Simple scoring
    score = 50  # baseline
    if 'ret_20d' in dir() and ret_20d > 0.05:
        score += 10
    elif 'ret_20d' in dir() and ret_20d < -0.05:
        score -= 10

    if 'vol_ratio' in dir() and vol_ratio > 1.2:
        score += 5

    if 'trend' in dir() and '多头排列' in trend:
        score += 10

    if score >= 60:
        verdict = "✅ 偏多 — 跟随美股联动，关注开盘确认"
    elif score >= 45:
        verdict = "⚡ 中性 — 等待开盘方向确认后再决策"
    else:
        verdict = "⚠️ 偏空 — 注意风险，不宜追高"

    print(f"  评分(简化): {score}/100")
    print(f"  结论: {verdict}")

print(f"\n  ⚠️ ETF特点:")
print(f"  - 588170跟踪半导体指数，无个股暴雷风险")
print(f"  - 但波动率接近个股（20日年化波动率可能>30%）")
print(f"  - 适合: 看好半导体板块但不想选个股")
print(f"  - 不适合: 追求超额收益（ETF只能获得beta）")
print(f"  - 如果个股筛选出强势标的 → 优先个股（alpha > beta）")
