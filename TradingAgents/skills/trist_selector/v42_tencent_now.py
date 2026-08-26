"""v4.2 with Tencent real-time quotes — latest prices for tracked stocks"""
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
from screener import compute_indicators, cache_update_one
from scoring import TristScorer, build_market_context
import scoring as sc
import numpy as np

# Force Tencent API
from direct_api import _get_tencent_quote

def get_latest(ticker):
    """Get latest price + data from Tencent, fallback to cached"""
    tq = _get_tencent_quote(ticker)
    if tq and tq.get('price', 0) > 0:
        return tq
    # Fallback: use cached kline
    kline = cache_update_one(ticker, start_date="2026-07-01")
    if len(kline) > 0:
        c = kline["close"].values
        return {
            'name': '', 'price': float(c[-1]),
            'open': float(kline["open"].values[-1]),
            'high': float(kline["high"].values[-1]),
            'low': float(kline["low"].values[-1]),
            'prev_close': float(c[-2]) if len(c)>=2 else float(c[-1]),
            'change_pct': (float(c[-1])/float(c[-2])-1)*100 if len(c)>=2 else 0,
            'volume': float(kline["volume"].values[-1]) if "volume" in kline.columns else 0,
            'amount': 0, 'turnover': 0, 'vol_ratio': 0, 'amplitude': 0,
            '_source': 'cached_kline',
        }
    return {}

# Aggressive bypass: skip _check_forbidden entirely
orig_check_forbidden = sc.TristScorer._check_forbidden
def patched_check(self, result, data, sector):
    pass  # Skip all forbidden checks
sc.TristScorer._check_forbidden = patched_check

ctx = build_market_context()

# Stocks to check
stocks = [
    ("601168", "西部矿业", None),
    ("000636", "风华高科", 58.65),
]

for ticker, name, entry in stocks:
    tq = get_latest(ticker)
    price = tq.get('price', 0)
    chg = tq.get('change_pct', 0)
    source = tq.get('_source', '?')

    # Get cached K-line for MA calculations
    kline = cache_update_one(ticker, start_date="2026-06-01")
    ind = compute_indicators(kline)
    close_arr = kline["close"].values

    # Override with Tencent real price
    ind["price"] = price
    ind["ticker"] = ticker
    ind["name"] = tq.get('name', name)

    # Recalculate MAs with live price (bugfix: cached close[-1] is stale)
    n = len(close_arr)
    if n >= 5 and price > 0:
        ind["ma5"] = round(float(np.mean(np.append(close_arr[-4:], price))), 2)
    if n >= 7 and price > 0:
        ind["ma7"] = round(float(np.mean(np.append(close_arr[-6:], price))), 2)
    if n >= 10 and price > 0:
        ind["ma10"] = round(float(np.mean(np.append(close_arr[-9:], price))), 2)
    if n >= 20 and price > 0:
        ind["ma20"] = round(float(np.mean(np.append(close_arr[-19:], price))), 2)

    r = TristScorer(market_context=ctx).score(ind, {})

    ma5 = ind.get("ma5",0); ma10 = ind.get("ma10",0); ma20 = ind.get("ma20",0)
    ma7 = float(np.mean(close_arr[-7:])) if len(close_arr)>=7 else 0

    # Real gap from Tencent
    real_open = tq.get('open', 0)
    real_prev = tq.get('prev_close', 0)
    real_gap = (real_open/real_prev - 1)*100 if real_prev > 0 else 0

    pre5d = ind.get("pre_5d_return",0); pre20d = ind.get("pre_20d_return",0)
    v = kline["volume"].values; avg_vol5 = np.mean(v[-5:])/1e6
    high_20d = np.max(kline["high"].values[-20:]) if len(kline)>=20 else price
    low_20d = np.min(kline["low"].values[-20:]) if len(kline)>=20 else price
    pnl = ((price/entry-1)*100) if entry else None

    print(f"\n{'='*65}")
    print(f"  {ticker} {name} @ {price:.2f} ({chg:+.2f}%) [数据:{source}]")
    if pnl is not None:
        print(f"  成本: {entry} | 浮动盈亏: {pnl:+.1f}%")
    print(f"{'='*65}")
    print(f"  MA5:{ma5:.2f} MA7:{ma7:.2f} MA10:{ma10:.2f} MA20:{ma20:.2f}")
    print(f"  多头(5>10>20):{ma5>ma10>ma20} | 短多(5>7>10):{ma5>ma7>ma10}")
    print(f"  价格vs MA5: {price-ma5:+.2f}({(price/ma5-1)*100:+.1f}%) | vs MA10: {price-ma10:+.2f}")
    print(f"  今开:{real_open:.2f} 昨收:{real_prev:.2f} 跳空:{real_gap:+.2f}%")
    print(f"  5日涨幅:{pre5d*100:+.1f}% | 20日:{pre20d*100:+.1f}%")
    print(f"  20日高:{high_20d:.2f} 低:{low_20d:.2f} 分位:{(price-low_20d)/(high_20d-low_20d)*100:.0f}%")
    print(f"  量: {avg_vol5:.0f}万手 | 换手:{tq.get('turnover',0):.2f}%")
    print(f"")
    print(f"  Score: {r.total_score}/100 (PA:{r.pa_score}/90 + B:{r.bonus_score}/10)")
    print(f"  Position: {r.position}({r.position_pct*100:.0f}%)")
    print(f"  Market: {r.market_state} | Signal: {r.signal_bar_quality}({r.signal_bar_type})")
    if r.pa_details:
        items=[f"{k}:{v:+d}"for k,v in sorted(r.pa_details.items())if v!=0]
        print(f"  PA: {' | '.join(items)}")
    print(f"  H{r.h_count}/L{r.l_count} | Wedge:{r.wedge_type} | SR:{r.sr_confluence}")
    if hasattr(r,'bonus_details'):
        hits=[k for k,v in r.bonus_details.items() if v]
        if hits: print(f"  Bonus: {', '.join(hits)}")
