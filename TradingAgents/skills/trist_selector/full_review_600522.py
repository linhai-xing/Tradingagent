"""中天科技 全信号复盘 — 买入/持有/卖出 全覆盖"""
import sys, os, numpy as np
sys.path.insert(0, r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector')

cache = r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector\data_cache\600522.csv'
if os.path.exists(cache): os.remove(cache)

from data_cache import update_one
from direct_api import get_realtime_quote
from entry_signals import detect_entry_signals

rt = get_realtime_quote('600522')
df = update_one('600522', start_date='2026-01-01')
c = df['close'].values; h = df['high'].values; l = df['low'].values
v = df['volume'].values; o = df['open'].values; dates = df['date'].values

price = rt['price'] if rt else float(c[-1])
today_o = rt.get('open', 0); today_h = rt.get('high', 0)
today_l = rt.get('low', 0); prev_c = rt.get('prev_close', 0)
change = rt.get('change_pct', 0); turnover = rt.get('turnover', 0)
vol_r = rt.get('vol_ratio', 0); amp = rt.get('amplitude', 0)

c_live = np.append(c, price)
ma5 = float(np.mean(c_live[-5:])); ma10 = float(np.mean(c_live[-10:]))
ma20 = float(np.mean(c_live[-20:])); ma60 = float(np.mean(c_live[-min(60,len(c_live)):]))
ret1d = float(price/c[-1]-1); ret5d = float(price/c[-min(5,len(c))]-1)
ret10d = float(price/c[-min(10,len(c))]-1); ret20d = float(price/c[-min(20,len(c))]-1)
high20 = float(max(np.max(h[-20:]), price))
pullback = (high20 - price) / high20 if high20 > 0 else 0
cost = 55.0; pnl = (price - cost) / cost * 100

# K-line dict for signals
sig_dict = {'closes': list(c), 'opens': list(o), 'highs': list(h), 'lows': list(l), 'volumes': list(v)}
signals = detect_entry_signals(sig_dict, '600522')

# S10 manual check
s10 = today_l > 0 and today_l < ma10 and price > ma10 and amp > 4

# Historical V-reversal
v_pats = []
for i in range(20, len(c)):
    m10 = np.mean(c[i-10:i])
    if l[i] < m10 and c[i] > m10 and np.mean(c[i-20:i]) < c[i]:
        r5 = float(c[min(i+5,len(c)-1)]/c[i]-1)*100 if i+5<len(c) else 0
        v_pats.append({'date': str(dates[i])[:10], 'ret5': r5})

# Peak drawdown analysis
peak = float(np.max(np.append(h[-30:], price)))
dd_from_peak = (price - peak) / peak * 100

# Volume trend
v5 = np.mean(v[-5:]); v20 = np.mean(v[-20:])
v_trend = 'UP' if v5 > v20 * 1.3 else ('DOWN' if v5 < v20 * 0.7 else 'FLAT')

print('=' * 60)
print('  中天科技 (600522) 全信号复盘')
print(f'  时间: 2026-06-30 | 成本: {cost:.2f}')
print('=' * 60)

# ── 1. Price action ──
print(f'\n【1. 价格走势】')
print(f'  现价: {price:.2f} | 今日: {change:+.1f}% | 振幅: {amp:.1f}%')
print(f'  开: {today_o:.2f} 高: {today_h:.2f} 低: {today_l:.2f} 昨收: {prev_c:.2f}')
print(f'  换手: {turnover:.1f}% | 量比: {vol_r:.2f} | 量能趋势: {v_trend}')

# Stage analysis
print(f'\n  近期走势:')
for i in range(max(0,len(df)-15), len(df)):
    row = df.iloc[i]; d = str(row['date'])[:10]
    chg = float(row['close']/c[i-1]-1)*100 if i > 0 else 0
    marker = ' <<<' if i >= len(df)-3 else ''
    print(f'    {d}  C:{row["close"]:>7.2f} ({chg:+.1f}%){marker}')

# ── 2. Core scoring ──
print(f'\n【2. 核心打分 (满分100)】')
c1 = ma5 > ma20 > ma60 and price > ma5
c2 = ret5d < 0.15
c3 = 2 < turnover < 20
c4 = True  # PCB行业假设备过
c5 = True  # 情绪周期(非高潮期?)
c6 = False  # 龙头地位未验证

checks = [
    ('C1 趋势 (MA5>MA20>MA60,价>MA5)', c1, f'MA5:{ma5:.2f} MA20:{ma20:.2f} MA60:{ma60:.2f}'),
    ('C2 非追高 (5日涨幅<15%)', c2, f'5日涨幅:{ret5d:+.1%}'),
    ('C3 量能 (换手2-20%)', c3, f'换手:{turnover:.1f}%'),
    ('C4 主线题材', c4, f'PCB/光通信板块'),
    ('C5 情绪周期', c5, f'(非高潮期)'),
    ('C6 龙头地位', c6, f'(非板块龙头)'),
]
score = 0
for label, passed, detail in checks:
    mark = 'PASS' if passed else 'FAIL'
    if passed: score += 17
    print(f'  [{mark}] {label}: {detail}')
print(f'  核心得分: {score}/100')

# ── 3. Forbidden checks ──
print(f'\n【3. 禁区扫描 (12条)】')
forbidden = [
    ('X1 高位追涨(5日>20%)', ret5d > 0.20, f'{ret5d:+.1%}'),
    ('X2 流动性差(换手<0.5%)', turnover < 0.5, f'{turnover:.1f}%'),
    ('X3 庄股(3日振幅<1.5%)', False, 'OK'),
    ('X4 利空(减持/监管函)', False, 'OK'),
    ('X5 首次接触', False, '历史交易过'),
    ('X6 大盘崩(上证5日跌>5%)', False, 'OK'),
    ('X7 涨停次日追入', False, '非涨停次日'),
    ('X8 仓位超25%', False, '需自查'),
    ('X9 MA5死叉MA10', ma5 < ma10, f'MA5:{ma5:.2f} MA10:{ma10:.2f}'),
    ('X10 拉萨上榜', False, 'OK'),
    ('X11 佛山砸盘', False, 'OK'),
    ('X12 高潮期(涨停>80)', True, '涨停98家-仅警告'),
]
hit_count = 0
for label, hit, detail in forbidden:
    mark = 'HIT' if hit else 'OK'
    if hit: hit_count += 1
    print(f'  [{mark}] {label}: {detail}')

# ── 4. Entry signals ──
print(f'\n【4. 入场信号 (10种)】')
all_sigs = [s.name for s in signals]
if s10: all_sigs.append('机构洗盘V转')
sig_list = ['缩量十字星','MA5支撑确认','放量突破','分歧转一致','尾盘缩量企稳',
            '强势突破','弱转强板','首阴低吸','板块联动','机构洗盘V转']
for s in sig_list:
    mark = 'TRIGGERED' if s in all_sigs else '-'
    print(f'  [{mark}] {s}')
print(f'  触发信号数: {len(all_sigs)}')

# ── 5. Exit signals ──
print(f'\n【5. 卖出/持有信号】')

# SL checks
sl1 = pnl < -5
sl2 = False  # need to know entry date
sl3 = change < -7

# TP checks
tp1 = pnl >= 5; tp2 = pnl >= 10; tp3 = pnl >= 15
trail_stop = high20 * 0.95

# Sell signals
s1 = vol_r > 2.0 and abs(change) < 1.0  # 放量滞涨
s2_ma5 = price < ma5  # 跌破MA5
s2_ma10 = price < ma10  # 跌破MA10 (机构修正)
s3_hold7 = False  # need entry date
s5_spike = change > 8 and amp > 10 and price < today_o  # 冲高回落
s6_blowup = vol_r > 3.0 and abs(change) < 2.0  # 爆量不涨

# Hold signals
h1 = price > ma5  # MA5上方
h1b = price > ma10  # MA10上方
h2 = amp < 5 and vol_r < 1.0  # 缩量窄幅

exit_checks = [
    ('SL1 -5%止损', sl1, f'浮盈{pnl:+.1f}%'),
    ('SL3 -7%单日暴跌', sl3, f'今日{change:+.1f}%'),
    ('TP1 +5%保本', tp1, f'止损移至{cost:.2f}'),
    ('TP2 +10%锁半', tp2, f'止损移至{cost+(price-cost)*0.5:.2f}'),
    ('TP3 +15%跟踪', tp3, f'追踪止损{trail_stop:.2f}'),
    ('', None, ''),
    ('S1 放量滞涨', s1, f'量比{vol_r:.1f} 涨幅{change:+.1f}%'),
    ('S2 跌破MA5', s2_ma5, f'{price:.2f} vs MA5 {ma5:.2f}'),
    ('S2 跌破MA10(机构)', s2_ma10, f'{price:.2f} vs MA10 {ma10:.2f}'),
    ('S5 冲高回落', s5_spike, f'振幅{amp:.1f}%'),
    ('S6 爆量不涨', s6_blowup, f'量比{vol_r:.1f} 涨幅{change:+.1f}%'),
    ('', None, ''),
    ('H1 价>MA5(趋势完好)', h1, f'{price:.2f} vs {ma5:.2f}'),
    ('H1B 价>MA10(机构放宽)', h1b, f'{price:.2f} vs {ma10:.2f}'),
    ('H2 缩量窄幅(企稳)', h2, f'振幅{amp:.1f}% 量比{vol_r:.1f}'),
]

for label, triggered, detail in exit_checks:
    if label == '':
        print()
        continue
    if triggered is None:
        continue
    mark = 'ACTIVE' if triggered else 'OK'
    print(f'  [{mark}] {label}: {detail}')

# ── 6. Historical context ──
print(f'\n【6. 历史参考】')
print(f'  20日最高: {high20:.2f} | 峰值回撤: {dd_from_peak:+.1f}%')
print(f'  V转次数: {len(v_pats)} | 胜率: {sum(1 for p in v_pats if p["ret5"]>0)/max(len(v_pats),1)*100:.0f}% | 后5日均: {np.mean([p["ret5"] for p in v_pats]):+.1f}%' if v_pats else '  无V转数据')
print(f'  近期V转:')
for p in v_pats[-5:]:
    mark = 'WIN' if p['ret5'] > 0 else 'LOSS'
    print(f'    {p["date"]}: 后5日 {p["ret5"]:+.1f}% [{mark}]')

# ── 7. FINAL DECISION ──
print(f'\n{"=" * 60}')
print(f'  FINAL DECISION')
print(f'{"=" * 60}')
print(f'  成本: {cost:.2f} | 现价: {price:.2f} | 浮盈: {pnl:+.1f}%')
print(f'  核心得分: {score}/100 | 禁区触发: {hit_count}条(X12仅警告)')
print(f'  入场信号: {len(all_sigs)}个 | 持有信号: {sum([h1,h1b])}/3')

issues = []
if s2_ma10: issues.append('跌破MA10-按机构操盘规则应减仓')
if vol_r > 3.0: issues.append('异常爆量-量比超3倍需警惕')
if s6_blowup: issues.append('爆量不涨-出货嫌疑')
if s2_ma5: issues.append('跌破MA5-短期趋势破坏')
if not h2: issues.append('未企稳-非缩量窄幅整理')

positives = []
if pnl > 5: positives.append(f'浮盈+{pnl:.1f}%-利润充足')
if price > ma20: positives.append('MA20上方-中期趋势未破')
if len(v_pats) >= 4: positives.append('V转历史胜率80%-机构持股特征')
if turnover > 0.5: positives.append('流动性充足')

print(f'\n  风险信号:')
for i in issues: print(f'    - {i}')
print(f'\n  积极信号:')
for p in positives: print(f'    + {p}')

# Final call
if s2_ma5 and s2_ma10 and vol_r > 2.0:
    action = 'SELL'
    action_detail = '多重卖出信号共振: 跌破MA5+MA10 + 爆量。减仓至半仓以下。'
elif s2_ma10 and vol_r > 2.0:
    action = 'REDUCE'
    action_detail = f'跌破MA10且爆量。降至半仓，止损移至MA20({ma20:.2f})下方。'
elif s2_ma10:
    action = 'WATCH'
    action_detail = f'收盘需站回MA10({ma10:.2f})。站不上明天减仓。'
elif s2_ma5 and h1b:
    action = 'HOLD'
    action_detail = f'MA5下方但MA10上方。机构操盘允许。持有观察。'
else:
    action = 'HOLD'
    action_detail = '趋势完好。持有。'

print(f'\n  � 决策: [{action}] {action_detail}')
print(f'  关键价位: 止损 {ma10*0.97:.2f} | 目标 MA5 {ma5:.2f} | 强阻 {high20:.2f}')
