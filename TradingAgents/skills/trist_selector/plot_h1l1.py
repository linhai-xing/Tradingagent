"""
Plot 火炬电子(603678) with H1/L1/H2/L2 structure markings
"""
import baostock as bs
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import FancyArrowPatch
import warnings
warnings.filterwarnings('ignore')

# ─── 1. Get data ───
lg = bs.login()
rs = bs.query_history_k_data_plus(
    'sh.603678',
    'date,open,high,low,close,volume',
    start_date='2026-01-01', end_date='2026-08-14',
    frequency='d', adjustflag='2'
)
data = []
while rs.error_code == '0' and rs.next():
    data.append(rs.get_row_data())
bs.logout()

df = pd.DataFrame(data, columns=['date','open','high','low','close','volume'])
df['date'] = pd.to_datetime(df['date'])
df[['open','high','low','close','volume']] = df[['open','high','low','close','volume']].astype(float)
df.set_index('date', inplace=True)

# ─── 2. EMA20 ───
df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()

# ─── 3. Identify structure points ───
# Macro structure (post-crash recovery context)
# L1: Jul 1 peak (87.50) → Jul 20 low (42.51)
# H1: Jul 20 low (42.51) → Aug 11 high (54.80)
# L2: ? (potentially forming now)

l1_start = ('2026-07-01', 87.50)   # Peak
l1_end = ('2026-07-20', 42.51)     # Bottom of crash
h1_start = ('2026-07-20', 42.51)   # Bounce start
h1_end = ('2026-08-11', 54.80)     # Bounce high

# Current position
current_price = 51.37
current_date = '2026-08-14'

# ─── 4. Plot ───
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10),
                                 gridspec_kw={'height_ratios': [3, 1]},
                                 sharex=True)

# ── Upper: Candlestick chart ──
# Use mplfinance style
from mplfinance.original_flavor import candlestick_ohlc

# Prepare OHLC data
ohlc = df[['open','high','low','close']].copy()
ohlc['date_num'] = mdates.date2num(df.index.to_pydatetime())
ohlc_data = ohlc[['date_num','open','high','low','close']].values

# Draw candlesticks
candlestick_ohlc(ax1, ohlc_data, width=0.6, colorup='#e74c3c', colordown='#2ecc71', alpha=0.8)

# EMA20
ax1.plot(df.index, df['ema20'], color='#3498db', linewidth=1.5, alpha=0.7, label='EMA20')

# ── Annotations for H1/L1 ──
# L1 (first leg down - bear trend)
ax1.annotate('', xy=(pd.Timestamp('2026-07-01'), 87.50),
             xytext=(pd.Timestamp('2026-07-20'), 42.51),
             arrowprops=dict(arrowstyle='->', color='#e74c3c', lw=3,
                           connectionstyle='arc3,rad=0.2'))
ax1.text(pd.Timestamp('2026-07-10'), 65, 'L1\n第一段下跌',
         fontsize=13, fontweight='bold', color='#e74c3c',
         ha='center', va='center',
         bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='#e74c3c', alpha=0.9))

# H1 (first bounce - bear trend bounce)
ax1.annotate('', xy=(pd.Timestamp('2026-07-20'), 42.51),
             xytext=(pd.Timestamp('2026-08-11'), 54.80),
             arrowprops=dict(arrowstyle='->', color='#f39c12', lw=3,
                           connectionstyle='arc3,rad=0.2'))
ax1.text(pd.Timestamp('2026-07-28'), 48, 'H1\n第一次反弹\n(陷阱区)',
         fontsize=13, fontweight='bold', color='#f39c12',
         ha='center', va='center',
         bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='#f39c12', alpha=0.9))

# L2 (potential - what we're waiting for)
# Mark the current area as "L2 forming?"
ax1.annotate('', xy=(pd.Timestamp('2026-08-11'), 54.80),
             xytext=(pd.Timestamp(current_date), current_price + 2),
             arrowprops=dict(arrowstyle='->', color='#e74c3c', lw=2, linestyle='dashed',
                           connectionstyle='arc3,rad=-0.2'))
ax1.text(pd.Timestamp('2026-08-12'), 57, 'L2?\n(等待确认)',
         fontsize=13, fontweight='bold', color='#e74c3c',
         ha='center', va='bottom',
         bbox=dict(boxstyle='round,pad=0.3', facecolor='#fff5f5', edgecolor='#e74c3c', alpha=0.9,
                  linestyle='dashed'))

# Key price labels
ax1.axhline(y=42.51, color='#e74c3c', linestyle=':', alpha=0.5)
ax1.text(pd.Timestamp('2026-07-15'), 42.51, ' 42.51 (L1底)',
         fontsize=10, color='#e74c3c', va='bottom')

ax1.axhline(y=54.80, color='#f39c12', linestyle=':', alpha=0.5)
ax1.text(pd.Timestamp('2026-08-05'), 54.80, ' 54.80 (H1顶)',
         fontsize=10, color='#f39c12', va='bottom')

ax1.axhline(y=87.50, color='#e74c3c', linestyle=':', alpha=0.3)
ax1.text(pd.Timestamp('2026-06-28'), 87.50, ' 87.50 (历史高点)',
         fontsize=10, color='#e74c3c', va='bottom')

# Mark current price
ax1.axhline(y=current_price, color='#2c3e50', linestyle='--', alpha=0.6)
ax1.text(pd.Timestamp(current_date), current_price, f' 当前 {current_price}',
         fontsize=11, fontweight='bold', color='#2c3e50', va='bottom')

# Trap zone highlight
ax1.axhspan(42.51, 54.80, alpha=0.06, color='#f39c12')
ax1.text(pd.Timestamp('2026-08-01'), 43.5, '⬛ H1陷阱区\n(反弹区间)',
         fontsize=9, color='#f39c12', alpha=0.6, va='top')

# ── Title ──
ax1.set_title('火炬电子(603678) H1/L1/H2/L2 结构分析 (2026.01 - 2026.08)',
              fontsize=16, fontweight='bold', pad=15)
ax1.set_ylabel('价格 (元)', fontsize=12)
ax1.legend(loc='upper left', fontsize=10)
ax1.grid(True, alpha=0.2)
ax1.set_ylim(25, 100)

# ── Lower: Volume ──
colors = ['#e74c3c' if df['close'].iloc[i] >= df['open'].iloc[i] else '#2ecc71'
          for i in range(len(df))]
ax2.bar(df.index, df['volume'], color=colors, alpha=0.5, width=0.8)
ax2.set_ylabel('成交量', fontsize=12)
ax2.grid(True, alpha=0.2)

# Format x-axis
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
ax2.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
plt.xticks(rotation=45)

plt.tight_layout()
plt.savefig('C:\\Users\\72955\\Desktop\\tradingagent\\TradingAgents\\skills\\trist_selector\\603678_structure.png',
            dpi=150, bbox_inches='tight')
print("Chart saved successfully!")

# ─── 5. Calculate key insights ───
print(f"\n{'='*50}")
print(f"结构分析摘要")
print(f"{'='*50}")
print(f"L1 (第一段下跌): 87.50 → 42.51 (-51.4%)")
print(f"   期间: 2026-07-01 至 2026-07-20 (14个交易日)")
print(f"H1 (第一次反弹): 42.51 → 54.80 (+28.9%)")
print(f"   期间: 2026-07-20 至 2026-08-11 (16个交易日)")
print(f"\n当前价格: {current_price} ({current_date})")
print(f"L1底部: 42.51 | H1顶部: 54.80")
print(f"当前位于H1反弹区间内 ({42.51} - {54.80})")
print(f"\n等待L2确认:")
print(f"  - 若跌破42.51 → L2确认 = 继续下跌趋势, 不可入场")
print(f"  - 若突破54.80 + 回踩不破 → 趋势反转可能, 等待H2结构")
print(f"  - 当前评分35分, 观察区, 不操作")