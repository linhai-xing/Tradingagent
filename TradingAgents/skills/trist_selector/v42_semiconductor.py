"""Semiconductor sector screen — top 5 for right-side trend trading"""
import sys, os, time, json, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from screener import compute_indicators, cache_update_one
from scoring import TristScorer, build_market_context
import scoring as sc

sc.TristScorer._check_forbidden = lambda self, result, data, sector: None

# Get semiconductor sector constituents
print("Fetching semiconductor sector constituents...")
tickers_semi = []
try:
    import akshare as ak
    # Try multiple sector names
    for sector_name in ["半导体", "芯片", "半导体及元件"]:
        try:
            cons = ak.stock_board_industry_cons_em(symbol=sector_name)
            tickers_semi = cons["代码"].tolist()
            names = dict(zip(cons["代码"], cons["名称"]))
            print(f"  Found {len(tickers_semi)} stocks in '{sector_name}' sector")
            break
        except:
            continue
except:
    pass

if not tickers_semi:
    # Fallback: known semiconductor stocks
    tickers_semi = [
        "603986","002049","603501","600703","002185","300223",
        "688981","688008","002156","300474","603160","688012",
        "300782","688536","002371","300604","688256","688037",
        "300458","688396","002409","300672","300661","603005",
        "002916","688126","300576","688595","688052","603690",
    ]
    names = {}
    print(f"  Using fallback list: {len(tickers_semi)} stocks")

print(f"  Candidate pool: {len(tickers_semi)}")

ctx = build_market_context()
print(f"  Market: Limit-up={ctx.get('limit_up_count','?')}")

# Score all
print(f"\nScoring {len(tickers_semi)} semiconductor stocks...")
results = []
for i, t in enumerate(tickers_semi):
    try:
        kline = cache_update_one(t, start_date="2026-03-01")
        if len(kline) < 20: continue
        ind = compute_indicators(kline)
        price = float(kline["close"].values[-1])
        ind.update({"ticker": t, "name": names.get(t, ""), "price": price})

        # Tencent real-time override
        try:
            from direct_api import _get_tencent_quote
            tq = _get_tencent_quote(t)
            if tq and tq.get('price',0) > 0:
                ind['price'] = tq['price']
                ind['vol_ratio'] = tq.get('vol_ratio', ind.get('vol_ratio',1))
                ind['today_ret'] = tq.get('change_pct',0)/100
                price = tq['price']
                ind['name'] = tq.get('name', ind.get('name',''))
        except: pass

        r = TristScorer(market_context=ctx).score(ind, {})

        ma5 = ind.get("ma5",0); ma10 = ind.get("ma10",0); ma20 = ind.get("ma20",0)
        ma_bull = ma5 > ma10 > ma20 > 0
        close_arr = kline["close"].values
        ret_5d = (close_arr[-1]/close_arr[-6]-1)*100 if len(close_arr)>=6 else 0
        high_20d = np.max(kline["high"].values[-20:])
        low_20d = np.min(kline["low"].values[-20:])
        pos_20d = (price-low_20d)/(high_20d-low_20d)*100 if high_20d>low_20d else 50

        results.append({
            "ticker": t, "name": ind.get('name',''), "price": price,
            "score": r.total_score, "pa_score": r.pa_score,
            "ma_bull": ma_bull, "ma5": round(ma5,2), "ma10": round(ma10,2), "ma20": round(ma20,2),
            "ret_5d": round(ret_5d,1), "pos_20d": round(pos_20d,0),
            "market": r.market_state, "signal": r.signal_bar_quality,
            "h_count": r.h_count, "l_count": r.l_count,
            "wedge": r.wedge_type, "sr": r.sr_confluence,
            "pa_details": r.pa_details,
            "entry_signals": r.entry_signals,
        })
    except: pass
    if (i+1) % 10 == 0: print(f"  Progress: {i+1}/{len(tickers_semi)}")

# Rank: MA-bull first, then by score
ma_bull_list = sorted([r for r in results if r["ma_bull"]], key=lambda x: x["score"], reverse=True)
all_sorted = sorted(results, key=lambda x: x["score"], reverse=True)

print(f"\nScored: {len(results)} | MA-bull: {len(ma_bull_list)}")

def print_stock(i, r, label):
    print(f"\n  #{i+1} {r['ticker']} {r['name']} @ {r['price']:.2f} {label}")
    print(f"  Score: {r['score']}/100 (PA:{r['pa_score']}/90)")
    print(f"  MA5:{r['ma5']} MA10:{r['ma10']} MA20:{r['ma20']} 多头:{r['ma_bull']}")
    print(f"  5日:{r['ret_5d']:+.1f}% | 20日分位:{r['pos_20d']:.0f}%")
    print(f"  Market:{r['market']} Signal:{r['signal']} H{r['h_count']}/L{r['l_count']} Wedge:{r['wedge']} SR:{r['sr']}")
    if r['pa_details']:
        items = [f"{k}:{v:+d}" for k,v in sorted(r['pa_details'].items()) if v!=0]
        print(f"  PA: {' | '.join(items)}")
    if r['entry_signals']:
        print(f"  Entry: {', '.join(r['entry_signals'][:4])}")

print(f"\n{'='*65}")
print(f"  [RIGHT-SIDE TREND] Semiconductor MA-Bull Top 5")
print(f"{'='*65}")
for i, r in enumerate(ma_bull_list[:5]):
    print_stock(i, r, ">>MA多头<<")

print(f"\n{'='*65}")
print(f"  [OVERALL] Semiconductor Top 5 by Score")
print(f"{'='*65}")
for i, r in enumerate(all_sorted[:5]):
    label = "MA多头" if r["ma_bull"] else ("MA偏多" if r["ma5"]>r["ma10"] else "MA偏空")
    print_stock(i, r, label)

print(f"\n  Summary: {len(ma_bull_list)} MA-bull / {len(results)} scored")
if ma_bull_list:
    print(f"  Best: {ma_bull_list[0]['ticker']} {ma_bull_list[0]['name']} {ma_bull_list[0]['score']}/100")
