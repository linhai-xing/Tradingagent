"""Lightweight 缠论 analysis for 百合花 (603823)"""
import pandas as pd, numpy as np
import os

CACHE = os.path.join(os.path.dirname(__file__), "data_cache", "603823.csv")
df = pd.read_csv(CACHE, parse_dates=["date"]).sort_values("date")
c = df["close"].values; h = df["high"].values; l = df["low"].values; o = df["open"].values
n = len(c)

# ═══════════════════════════════════════════════════════
# 1. 分型 (Fractals)
# ═══════════════════════════════════════════════════════
tops, bottoms = [], []
for i in range(1, n-1):
    if h[i] > h[i-1] and h[i] > h[i+1]:
        tops.append((i, df.iloc[i]["date"], h[i]))
    if l[i] < l[i-1] and l[i] < l[i+1]:
        bottoms.append((i, df.iloc[i]["date"], l[i]))

# ═══════════════════════════════════════════════════════
# 2. 笔 (Strokes / Bi)
# ═══════════════════════════════════════════════════════
points = []
for idx, date, price in tops:
    points.append({"idx": idx, "date": date, "price": price, "type": "top"})
for idx, date, price in bottoms:
    points.append({"idx": idx, "date": date, "price": price, "type": "bottom"})
points.sort(key=lambda x: x["idx"])

strokes = []
prev = points[0]
for p in points[1:]:
    if p["type"] != prev["type"] and p["idx"] - prev["idx"] >= 4:
        strokes.append({
            "start_idx": prev["idx"], "end_idx": p["idx"],
            "start_date": prev["date"], "end_date": p["date"],
            "start_price": prev["price"], "end_price": p["price"],
            "direction": "up" if prev["type"] == "bottom" else "down"
        })
        prev = p

# ═══════════════════════════════════════════════════════
# 3. 线段 (Segments)
# ═══════════════════════════════════════════════════════
segments = []
if len(strokes) >= 3:
    seg_start = 0
    for i in range(1, len(strokes)-1):
        if strokes[i]["direction"] != strokes[i+1]["direction"]:
            seg = strokes[seg_start:i+2]
            if len(seg) >= 3:
                segments.append({
                    "start_idx": seg[0]["start_idx"], "end_idx": seg[-1]["end_idx"],
                    "start_date": seg[0]["start_date"], "end_date": seg[-1]["end_date"],
                    "start_price": seg[0]["start_price"], "end_price": seg[-1]["end_price"],
                    "direction": "up" if seg[0]["direction"] == "up" else "down",
                    "stroke_count": len(seg)
                })
            seg_start = i + 1

# ═══════════════════════════════════════════════════════
# 4. 中枢 (Hubs / Zhong Shu)
# ═══════════════════════════════════════════════════════
hubs = []
if len(segments) >= 3:
    for i in range(len(segments)-2):
        s1, s2, s3 = segments[i], segments[i+1], segments[i+2]
        zl = max(min(s1["start_price"], s1["end_price"]),
                 min(s2["start_price"], s2["end_price"]),
                 min(s3["start_price"], s3["end_price"]))
        zh = min(max(s1["start_price"], s1["end_price"]),
                 max(s2["start_price"], s2["end_price"]),
                 max(s3["start_price"], s3["end_price"]))
        if zl < zh:
            hubs.append({
                "start_date": s1["start_date"], "end_date": s3["end_date"],
                "zl": zl, "zh": zh, "center": (zl+zh)/2
            })

# ═══════════════════════════════════════════════════════
# 5. 买卖点 & MA10 分析
# ═══════════════════════════════════════════════════════
ma10 = np.mean(c[-10:])
ma20 = np.mean(c[-20:])
ma5_vals = [np.mean(c[max(0,i-4):i+1]) for i in range(n)]
ma10_vals = [np.mean(c[max(0,i-9):i+1]) for i in range(n)]
ma20_vals = [np.mean(c[max(0,i-19):i+1]) for i in range(n)]

print("=" * 70)
print("  百合花 (603823) — 缠论结构分析")
print("=" * 70)

print(f"\n[分型] 顶{len(tops)}个, 底{len(bottoms)}个")
print("  最近顶分型:")
for idx, date, price in tops[-5:]:
    print(f"    顶: {date.strftime('%m-%d')} @ {price:.2f}")
print("  最近底分型:")
for idx, date, price in bottoms[-5:]:
    print(f"    底: {date.strftime('%m-%d')} @ {price:.2f}")

print(f"\n[笔] 共{len(strokes)}笔:")
for s in strokes[-8:]:
    d = "UP" if s["direction"] == "up" else "DN"
    pct = (s["end_price"]/s["start_price"]-1)*100
    print(f"  {d} {s['start_date'].strftime('%m-%d')}->{s['end_date'].strftime('%m-%d')} "
          f"{s['start_price']:.2f}->{s['end_price']:.2f} ({pct:+.1f}%)")

print(f"\n[线段] 共{len(segments)}段:")
for s in segments[-4:]:
    d = "UP" if s["direction"] == "up" else "DN"
    print(f"  {d} {s['start_date'].strftime('%m-%d')}->{s['end_date'].strftime('%m-%d')} "
          f"({s['stroke_count']}笔) {s['start_price']:.2f}->{s['end_price']:.2f}")

print(f"\n[中枢] 共{len(hubs)}个:")
for h in hubs[-3:]:
    print(f"  [{h['start_date'].strftime('%m-%d')}~{h['end_date'].strftime('%m-%d')}] "
          f"区间:{h['zl']:.2f}-{h['zh']:.2f} 中轴:{h['center']:.2f}")

# Check for 三买
print(f"\n[买卖点评估]:")
if hubs:
    last_hub = hubs[-1]
    print(f"  最近中枢: {last_hub['zl']:.2f}-{last_hub['zh']:.2f}")
    if c[-1] > last_hub["zh"]:
        print(f"  当前价格{c[-1]:.2f} > 中枢上沿{last_hub['zh']:.2f} -> 中枢上方运行 ✅")
        # Check if pullback stays above hub
        recent_low = min(l[-5:])
        if recent_low > last_hub["zh"]:
            print(f"  近5日低点{recent_low:.2f} > 中枢上沿 -> 【三买确认】🔥")
        else:
            print(f"  近5日低点{recent_low:.2f}触及中枢 -> 三买待确认")
    else:
        print(f"  价格在中枢内运行")

# Back-test MA10 bounce
print(f"\n[MA10 支撑实战回测]:")
print(f"  当前MA10: {ma10:.2f} | MA20: {ma20:.2f}")
print(f"  近20日触及MA10后反弹:")
bounces = []
for i in range(max(0, n-20), n):
    ma10_i = np.mean(c[max(0,i-9):i+1])
    if l[i] <= ma10_i <= h[i]:
        bounce_pct = (c[i] - ma10_i) / ma10_i * 100
        nxt = (c[i+1]/c[i]-1)*100 if i+1 < n else 0
        bounces.append({
            "date": df.iloc[i]["date"],
            "ma10": ma10_i, "low": l[i], "close": c[i],
            "bounce": bounce_pct, "nxt": nxt
        })
        status = "WIN" if bounce_pct > 0 or nxt > 0 else "LOSE"
        print(f"    {df.iloc[i]['date'].strftime('%m-%d')}: L={l[i]:.2f}触MA10({ma10_i:.2f}) "
              f"-> C={c[i]:.2f}({bounce_pct:+.1f}%) 次日{nxt:+.1f}% [{status}]")

if bounces:
    wins = sum(1 for b in bounces if b["bounce"] > 0 or b["nxt"] > 0)
    print(f"  MA10买入胜率: {wins}/{len(bounces)} = {wins/len(bounces)*100:.0f}%")

# 07-23 analysis
print(f"\n[07-23 K线 缠论视角]:")
print(f"  开盘{c[-2]:.2f} 高{c[-2]:.2f} -> 但07-23 O78.36 H80.90 L73.74 C73.74")
print(f"  这根K线是否形成顶分型? ", end="")
if n >= 3 and h[-2] > h[-3] and h[-2] > h[-1]:
    print(f"YES - 07-22高点{h[-2]:.2f} > 07-21高点{h[-3]:.2f} 且 > 07-23高点{h[-1]:.2f}")
    print(f"  -> 07-22形成【顶分型】⚠️")
else:
    print(f"NO - 未形成标准顶分型")

print(f"\n[趋势状态]:")
print(f"  底分型逐步抬高: ", end="")
if len(bottoms) >= 2 and bottoms[-1][2] > bottoms[-2][2]:
    print(f"YES ({bottoms[-2][2]:.2f} -> {bottoms[-1][2]:.2f}) ✅")
else:
    print(f"NO ⚠️")
print(f"  顶分型逐步抬高: ", end="")
if len(tops) >= 2 and tops[-1][2] > tops[-2][2]:
    print(f"YES ({tops[-2][2]:.2f} -> {tops[-1][2]:.2f}) ✅")
else:
    print(f"NO ⚠️")

# Final: where is the buy point?
print(f"\n[缠论买点结论]:")
print(f"  当前MA10: {ma10:.2f}")
print(f"  最近中枢上沿: {hubs[-1]['zh']:.2f}" if hubs else "  无可用中枢")
print(f"  07-23低点: {l[-1]:.2f}")
print(f"  ")
print(f"  缠论视角的理想买点:")
if len(bottoms) >= 2:
    last_bot = bottoms[-1][2]
    print(f"  1) 二买: 等待回调在最近底分型{last_bot:.2f}上方形成新底分型")
if hubs:
    print(f"  2) 三买: 回调不破中枢上沿{hubs[-1]['zh']:.2f}时入场")
print(f"  3) MA10买点: 价格回踩MA10({ma10:.2f})且不有效跌破时")
print(f"  ")
print(f"  你之前清仓的位置 vs 现在的位置:")
print(f"  是否在MA10附近? {'YES -> 如果是，卖飞了' if abs(c[-1]-ma10)/ma10 < 0.03 else f'NO -> 现价{c[-1]:.2f}距MA10 {ma10:.2f}偏离{(c[-1]/ma10-1)*100:.1f}%'}")
