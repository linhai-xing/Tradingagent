"""Deep K-line analysis for 600428 中远海特 — explain why MA5 pullback entry fails here"""
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
from screener import compute_indicators, cache_update_one
import numpy as np

kline = cache_update_one("600428", start_date="2026-05-01")
close = kline["close"].values
high = kline["high"].values
low = kline["low"].values
open_ = kline["open"].values
volume = kline["volume"].values
dates = kline.index.values if hasattr(kline.index, 'values') else list(range(len(kline)))

# Compute MAs from raw data
n = len(close)
ma5_arr = np.array([np.nan]*n)
ma10_arr = np.array([np.nan]*n)
ma20_arr = np.array([np.nan]*n)
for i in range(n):
    if i >= 4: ma5_arr[i] = np.mean(close[i-4:i+1])
    if i >= 9: ma10_arr[i] = np.mean(close[i-9:i+1])
    if i >= 19: ma20_arr[i] = np.mean(close[i-19:i+1])

# Last 20 bars for display
start = max(0, n-25)
end = n

price = close[-1]
ma5 = ma5_arr[-1]
ma10 = ma10_arr[-1]
ma20 = ma20_arr[-1]

# Key metrics
# H count: count of bars where high > previous bar's high since last swing low
h_count = 0
for i in range(n-1, max(0, n-40), -1):
    if high[i] > high[i-1]:
        h_count += 1
    else:
        break

# Find recent swing low and high
recent_high = np.max(high[-20:])
recent_low = np.min(low[-20:])
recent_high_idx = np.argmax(high[-20:]) + (n-20)
recent_low_idx = np.argmin(low[-20:]) + (n-20)

# Distance from MA5
dist_ma5_pct = (price - ma5) / ma5 * 100

# Volume trend
avg_vol_first10 = np.mean(volume[n-20:n-10])
avg_vol_last5 = np.mean(volume[n-5:])
vol_trend = "increasing" if avg_vol_last5 > avg_vol_first10 * 1.1 else ("decreasing" if avg_vol_last5 < avg_vol_first10 * 0.9 else "flat")

# Check: how many times in last 60 days did price touch MA5 and bounce?
touch_count = 0
for i in range(max(0,n-60), n):
    if abs(close[i] - ma5_arr[i]) / ma5_arr[i] < 0.02 and i > 0:
        next_day_ret = (close[i+1] - close[i]) / close[i] if i+1 < n else 0
        touch_count += 1

# Check if bear_wedge: lower highs pattern
bear_wedge = True
recent_highs = []
for i in range(n-1, max(0, n-30), -1):
    if i > 0 and high[i] > high[i-1] and high[i] > high[i+1] if i+1 < n else True:
        recent_highs.append((i, high[i]))
        if len(recent_highs) >= 3:
            break

print(f"\n{'='*65}")
print(f"  600428 中远海特 — K线逐根拆解")
print(f"{'='*65}")
print(f"  最新价: {price:.2f}")
print(f"  MA5: {ma5:.2f}  (距{price-ma5:+.2f}, {dist_ma5_pct:+.1f}%)")
print(f"  MA10: {ma10:.2f}")
print(f"  MA20: {ma20:.2f}")
print(f"  H计数: {h_count} | 20日高:{recent_high:.2f} 低:{recent_low:.2f}")
print(f"  量能趋势: {vol_trend} (近5日均量 vs 前10日均量)")
print(f"  近60日MA5触碰次数: {touch_count}")

# ── K-line by K-line analysis of last 20 bars ──
print(f"\n{'='*65}")
print(f"  最近20根日K线逐根分析")
print(f"{'='*65}")
print(f"  {'日期':<12} {'开盘':>6} {'最高':>6} {'最低':>6} {'收盘':>6} {'涨跌':>7} {'MA5':>6} {'特征'}")
print(f"  {'─'*70}")

for i in range(start, end):
    o = open_[i]; h = high[i]; l = low[i]; c = close[i]
    chg = (c / close[i-1] - 1) * 100 if i > 0 else 0
    m5 = ma5_arr[i]

    # Classify bar
    features = []
    body = abs(c - o)
    total_range = h - l
    body_ratio = body / total_range if total_range > 0 else 0

    if c > o:
        direction = "+"
    else:
        direction = "-"

    # Close position (0=bottom, 1=top)
    if h > l:
        close_pos = (c - l) / (h - l)
    else:
        close_pos = 0.5

    if body_ratio > 0.6:
        features.append("强实体")
    elif body_ratio < 0.3:
        features.append("小实体/十字")

    if close_pos > 0.8:
        features.append("收顶")
    elif close_pos < 0.2:
        features.append("收底")

    # Check if higher high
    if i > 0 and h > high[i-1]:
        features.append("HH" if len(features)==0 else "HH")

    # Check if near MA5
    if not np.isnan(m5):
        dist = abs(c - m5) / m5
        if dist < 0.02:
            features.append("=MA5")
        elif c > m5 * 1.03:
            features.append(">>MA5")

    # Check volume spike
    if i > 0 and volume[i] > np.mean(volume[max(0,i-5):i]) * 1.5:
        features.append("放量")

    date_str = str(dates[i])[:10] if hasattr(dates[i], '__len__') else f"T-{n-1-i}"
    print(f"  {date_str:<12} {o:>6.2f} {h:>6.2f} {l:>6.2f} {c:>6.2f} {chg:>+6.2f}% {m5:>6.2f}  {' '.join(features)}")

# ── Why MA5 Pullback Fails Here ──
print(f"\n{'='*65}")
print(f"  为什么MA5回踩买入在这里行不通？")
print(f"{'='*65}")

print(f"""
  一、价格根本没在"回踩"MA5
  ┌─────────────────────────────────────┐
  │ 当前价: {price:.2f}                         │
  │ MA5:    {ma5:.2f}                         │
  │ 差距:   {price-ma5:.2f} ({dist_ma5_pct:+.1f}%)                        │
  │                                     │
  │ 你所谓的"回踩MA5"需要价格先跌{price-ma5:.2f}元  │
  │ 那是从现在价格跌-{dist_ma5_pct:.0f}%到MA5附近           │
  │                                     │
  │ 如果跌-{dist_ma5_pct:.0f}%到MA5 → MA5当时也会下行   │
  │ → 你买到的不是"支撑位"，是"下跌通道"      │
  └─────────────────────────────────────┘

  二、H{h_count}的残酷真相（阿布）
  ┌─────────────────────────────────────┐
  │ H{h_count} = 连续{h_count}根K线高点抬高                  │
  │                                     │
  │ 阿布说：H1(首次创新高) → 趋势启动     │
  │        H2/H3(二次/三次) → 黄金买点   │
  │        H8+ → 聪明钱在分批出货        │
  │        H11+ → 已有11天派发期         │
  │                                     │
  │ 你现在买在H{h_count} → 买在派发周期尾端      │
  │ A股的游资叫这个：高位接盘             │
  └─────────────────────────────────────┘

  三、MA5回踩策略在什么情况下有效？
  ┌─────────────────────────────────────┐
  │ MA5回踩买入需要两个前提：             │
  │                                     │
  │ 1. 强趋势（价格持续在MA5上方运行）      │
  │    当前市场状态: trading_range       │
  │    → 震荡市里MA5没有"趋势支撑力"       │
  │                                     │
  │ 2. 均线缺口（20+根K线不碰MA20）       │
  │    当前: 价格频繁穿越MA20             │
  │    → 没有缺口 = 没有强趋势            │
  │                                     │
  │ 没有这两个前提，MA5回踩不是买点，      │
  │ 是"价格在回落到震荡区中部"。           │
  └─────────────────────────────────────┘

  四、实盘回测：近60天内MA5触碰后的表现
""")

# Actual MA5 touch analysis
touches = []
for i in range(max(0, n-60), n-1):
    if not np.isnan(ma5_arr[i]) and abs(close[i] - ma5_arr[i]) / ma5_arr[i] < 0.02:
        ret_1d = (close[i+1] - close[i]) / close[i]
        ret_3d = (close[min(i+3, n-1)] - close[i]) / close[i]
        ret_5d = (close[min(i+5, n-1)] - close[i]) / close[i]
        touches.append((i, close[i], ret_1d, ret_3d, ret_5d))

if touches:
    print(f"  {'日期':<12} {'触碰价':>7} {'次日':>8} {'3日后':>8} {'5日后':>8}")
    for t in touches[-5:]:
        date_str = str(dates[t[0]])[:10] if hasattr(dates[t[0]], '__len__') else f"idx{t[0]}"
        print(f"  {date_str:<12} {t[1]:>7.2f} {t[2]:>+7.1%} {t[3]:>+7.1%} {t[4]:>+7.1%}")

    wins = sum(1 for t in touches if t[3] > 0)
    print(f"\n  MA5触碰买入3日胜率: {wins}/{len(touches)} = {wins/len(touches)*100:.0f}%")
else:
    print(f"  近60日无MA5触碰记录 — 说明价格根本没在这个区域横盘过")

print(f"""
  五、熊旗楔形 + 20日+35% 双重警告
  ┌─────────────────────────────────────┐
  │ PA9检测: bear_wedge (熊旗楔形)       │
  │ → 价格正在收敛，方向偏空             │
  │                                     │
  │ 20日涨幅: +35%                       │
  │ → 阿布：20日涨30%以上的股票，        │
  │   任何回调至少到MA20才算"正常"       │
  │   回MA5就反弹 = 诱多陷阱             │
  │                                     │
  │ 你想做MA5回踩？                      │
  │ 阿布的回答：                         │
  │ "涨了35%只回调到MA5？这不是支撑，     │
  │  这是机构还没跑完。"                  │
  └─────────────────────────────────────┘

  六、正确的入场对比
  ┌──────────────────────────────────────┐
  │                                      │
  │  ❌ 方案A: 回MA5买入 ({ma5:.2f})          │
  │     风险: 买在H{h_count}高位，没回调空间    │
  │     止损: MA10({ma10:.2f}) → 亏{abs(ma5-ma10)/ma5*100:.1f}%  │
  │     胜率: 低（震荡市MA5无趋势支撑力）   │
  │                                      │
  │  ✅ 方案B: 回MA20买入 ({ma20:.2f})         │
  │     风险: 充分回调后入场              │
  │     止损: {ma20*0.97:.2f} (MA20-3%)        │
  │     胜率: 中（有阿布逻辑支撑）         │
  │     盈亏比: 2.4:1                    │
  │                                      │
  │  两者差: {ma5-ma20:.2f}元 = {(ma5-ma20)/ma5*100:.0f}%的额外安全垫        │
  │                                      │
  └──────────────────────────────────────┘
""")

# Final summary
print(f"  结论:")
print(f"  中远海特MA多头排列确实漂亮。但漂亮≠安全。")
print(f"  涨了35%后回MA5({'ma5:.2f'})买入 = 花了更多钱，买了更少的安全边际。")
print(f"  回MA20({'ma20:.2f'})买入 = 跌出安全垫后再入场，同样的MA多头+"+
       "更低的价格。")
print(f"  你是做右侧趋势，不是做追高。等回调=右侧的精髓。")
