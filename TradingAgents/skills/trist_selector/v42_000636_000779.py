"""Bypass all vetoes for 000636 风华高科 and 000779 甘咨询"""
import sys, os; sys.path.insert(0, os.path.dirname(__file__))
from screener import compute_indicators, cache_update_one
from scoring import TristScorer, build_market_context
import scoring as sc
import numpy as np

orig_score = sc.TristScorer.score
def patched(self, data, sector=None, discipline=None):
    # Bypass ALL veto conditions for scoring
    orig_turnover = data.get("avg_turnover_5d", 0)
    if orig_turnover < 0.01: data["avg_turnover_5d"] = 2.5
    if data.get("pre_5d_return",0) > 0.20: data["pre_5d_return"] = 0.15
    if data.get("prev_day_limit_up", False): data["prev_day_limit_up"] = False
    if abs(data.get("open_gap_pct",0)) > 0.05: data["open_gap_pct"] = 0
    orig_ma5 = data.get("ma5",0); orig_ma10 = data.get("ma10",0)
    if 0 < orig_ma5 < orig_ma10: data["ma5"] = orig_ma10 + 0.01
    result = orig_score(self, data, sector, discipline)
    data["ma5"] = orig_ma5; data["ma10"] = orig_ma10
    data["avg_turnover_5d"] = orig_turnover
    if hasattr(result, "forbidden_hits") and result.forbidden_hits:
        result.forbidden_hits = []
        result.vetoed = False
    return result
sc.TristScorer.score = patched

ctx = build_market_context()

for ticker, name in [("000636", "风华高科"), ("000779", "甘咨询")]:
    kline = cache_update_one(ticker, start_date="2026-01-01")
    ind = compute_indicators(kline)
    price = float(kline["close"].values[-1])
    ind.update({"ticker":ticker,"name":name,"price":price})
    try:
        from direct_api import get_realtime_quote
        rt = get_realtime_quote(ticker)
        if rt and rt.get('price',0)>0:
            ind['price']=rt['price']; ind['vol_ratio']=rt.get('vol_ratio',ind.get('vol_ratio',1))
            ind['today_ret']=rt.get('change_pct',0)/100
            price=rt['price']
    except: pass

    r = TristScorer(market_context=ctx).score(ind, {})

    ma5=ind.get("ma5",0); ma10=ind.get("ma10",0); ma20=ind.get("ma20",0)
    pre5d=ind.get("pre_5d_return",0); pre20d=ind.get("pre_20d_return",0)
    v=kline["volume"].values; avg_vol=np.mean(v[-5:])/1e6
    turnover=float(kline["turnover"].values[-1]) if "turnover" in kline.columns else 0
    chg=(float(kline["close"].values[-1])/float(kline["close"].values[-2])-1) if len(kline)>=2 else 0
    high_20d=np.max(kline["high"].values[-20:]) if len(kline)>=20 else price
    low_20d=np.min(kline["low"].values[-20:]) if len(kline)>=20 else price
    gap_pct=(float(kline["open"].values[-1])/float(kline["close"].values[-2])-1) if len(kline)>=2 else 0

    print(f"\n{'='*65}")
    print(f"  {ticker} {name} @ {price:.2f} (今日{chg:+.2%}) [全禁区旁路]")
    print(f"{'='*65}")
    print(f"  MA5:{ma5:.2f} MA10:{ma10:.2f} MA20:{ma20:.2f} 多头={ma5>ma10>ma20}")
    print(f"  价格vs MA5:{price-ma5:+.2f} vs MA10:{price-ma10:+.2f} vs MA20:{price-ma20:+.2f}")
    print(f"  换手:{turnover:.2f}% | 5日均量:{avg_vol:.0f}万手")
    print(f"  5日涨幅:{pre5d*100:+.1f}% | 20日涨幅:{pre20d*100:+.1f}%")
    print(f"  20日高:{high_20d:.2f} 低:{low_20d:.2f} 位置:{(price-low_20d)/(high_20d-low_20d)*100:.0f}%分位")
    print(f"  跳空:{gap_pct:+.2%}")
    print(f"")
    print(f"  Score: {r.total_score}/100 (PA:{r.pa_score}/90 + B:{r.bonus_score}/10)")
    print(f"  Position: {r.position}({r.position_pct*100:.0f}%)")
    print(f"  Market: {r.market_state} | Signal: {r.signal_bar_quality}({r.signal_bar_type})")
    if r.pa_details:
        items=[f"{k}:{v:+d}"for k,v in sorted(r.pa_details.items())if v!=0]
        print(f"  PA: {' | '.join(items)}")
    print(f"  H{r.h_count}/L{r.l_count} | Wedge:{r.wedge_type} | SR:{r.sr_confluence}")
    if r.entry_signals: print(f"  Entry: {', '.join(r.entry_signals[:6])}")
    if hasattr(r,'bonus_details'):
        hits=[k for k,v in r.bonus_details.items() if v]
        if hits: print(f"  Bonus: {', '.join(hits)}")
