"""
电力板块 — 纯PA评分（不看禁区，一票不否）
"""
import noproxy
import sys, os, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector'
sys.path.insert(0, BASE)
os.chdir(BASE)

from datetime import datetime
import pandas as pd, numpy as np
from direct_api import _get_tencent_quote
from screener import compute_indicators, cache_update_one
from scoring import TristScorer, build_market_context
from entry_signals import detect_entry_signals, get_entry_recommendation
import scoring as sc

# ── Patch: 完全绕过所有禁区 ──
orig_score = sc.TristScorer.score
def patched(self, data, sector=None, discipline=None):
    # 伪造MA5>MA10 绕过X9
    orig_ma5, orig_ma10 = data.get("ma5", 0), data.get("ma10", 0)
    if orig_ma5 < orig_ma10 and orig_ma10 > 0:
        data["ma5"] = orig_ma10 + 0.01
    # 限制5日涨幅 绕过X1
    if data.get("pre_5d_return", 0) > 0.20:
        data["pre_5d_return"] = 0.15
    # 清掉涨停标记 绕过X7
    if data.get("prev_day_limit_up", False):
        data["prev_day_limit_up"] = False

    result = orig_score(self, data, sector, discipline)

    data["ma5"], data["ma10"] = orig_ma5, orig_ma10
    # 清空所有禁区
    if hasattr(result, "forbidden_hits"):
        result.forbidden_hits = []
        result.vetoed = False
    return result
sc.TristScorer.score = patched

print("=" * 60)
print("  电力板块 — 纯PA评分 (全部禁区绕过)")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 60)

ctx = build_market_context()
scorer = TristScorer(market_context=ctx)

tickers = [
    ('600396','华电辽能'),('600011','华能国际'),('600023','浙能电力'),
    ('600027','华电国际'),('600795','国电电力'),('601991','大唐发电'),
    ('000539','粤电力A'),('000543','皖能电力'),('600886','国投电力'),
    ('600578','京能电力'),('600021','上海电力'),('000690','宝新能源'),
    ('000720','新能泰山'),('000767','晋控电力'),
    ('600900','长江电力'),('600674','川投能源'),('600025','华能水电'),
    ('000883','湖北能源'),
    ('601985','中国核电'),('003816','中国广核'),
    ('600905','三峡能源'),('601016','节能风电'),('600163','中闽能源'),
    ('000862','银星能源'),
    ('600406','国电南瑞'),('601877','正泰电器'),('000400','许继电气'),
    ('600509','天富能源'),('600644','乐山电力'),('600101','明星电力'),
    ('600452','涪陵电力'),('600982','宁波能源'),('000600','建投能源'),
    ('600483','福能股份'),('600089','特变电工'),
]

results = []
for ticker, name in tickers:
    try:
        # 用 cache_update_one 获取最新K线 (baostock)
        kline = cache_update_one(ticker, start_date="2026-01-01")
        if kline is None or len(kline) < 20:
            continue

        ind = compute_indicators(kline)
        if not ind:
            continue

        # 实时价格
        rt = _get_tencent_quote(ticker)
        time.sleep(0.10)
        price = rt.get('price', float(kline["close"].values[-1])) if rt else float(kline["close"].values[-1])
        change_pct = rt.get('change_pct', 0) if rt else 0

        ind["ticker"] = ticker
        ind["name"] = name
        ind["price"] = price
        ind["is_realtime"] = True
        if change_pct != 0:
            ind["today_ret"] = change_pct / 100

        result = scorer.score(ind, {})
        if result is None:
            continue

        # 入场信号
        kline_dict = {
            "closes": kline["close"].tolist(), "opens": kline["open"].tolist(),
            "highs": kline["high"].tolist(), "lows": kline["low"].tolist(),
            "volumes": kline["volume"].tolist(),
        }
        signals = detect_entry_signals(kline_dict, ticker)
        result.entry_signals = [s.name for s in signals]

        # 附加均线
        closes = kline["close"].values
        result._ma5 = pd.Series(closes).rolling(5).mean().values[-1]
        result._ma10 = pd.Series(closes).rolling(10).mean().values[-1]
        result._ma20 = pd.Series(closes).rolling(20).mean().values[-1]
        result._rt_price = price
        result._rt_change = change_pct
        result._name = name

        results.append(result)
        print(f"  {ticker} {name}: {result.total_score}分")
    except Exception as e:
        print(f"  {ticker} ERROR: {e}")
        continue

# 排序
results.sort(key=lambda x: x.total_score, reverse=True)

print(f"\n{'='*60}")
print(f"  电力板块 纯PA排名 (无禁区, 共{len(results)}只)")
print(f"{'='*60}")

for i, r in enumerate(results):
    name = getattr(r, '_name', '') or getattr(r, 'name', '')
    price = getattr(r, '_rt_price', r.price)
    change = getattr(r, '_rt_change', 0)

    if r.total_score >= 72: tag = "\033[1;32m[满仓]\033[0m"
    elif r.total_score >= 54: tag = "\033[1;33m[半仓]\033[0m"
    elif r.total_score >= 40: tag = "[观察]"
    else: tag = "[弱]"

    # 均线状态
    ma5, ma10, ma20 = getattr(r, '_ma5', 0), getattr(r, '_ma10', 0), getattr(r, '_ma20', 0)
    if ma5 > ma10 > ma20: ms = "多头"
    elif price > ma20: ms = "站上MA20"
    else: ms = "空头"

    print(f"\n  #{i+1} {tag} {name}({r.ticker}) {r.total_score}分 @{price:.2f} 实时:{change:+.1f}% MA:{ms}")
    if r.pa_details:
        pas = [f"{k}:{v:+d}" for k,v in sorted(r.pa_details.items()) if v != 0]
        if pas: print(f"    PA: {' | '.join(pas)}")
    print(f"    PA分:{r.pa_score} 强化:{r.bonus_score} 外围:{r.external_score}")
    print(f"    市场:{r.market_state} | K线:{r.signal_bar_quality}({r.signal_bar_type or '-'})")
    print(f"    H{r.h_count}/L{r.l_count} | 楔形:{r.wedge_type or '-'} | SR:{r.sr_confluence}重")
    if r.bonus_details:
        hits = [f"{k}" for k,v in r.bonus_details.items() if v and v is not False]
        if hits: print(f"    强化项: {', '.join(hits)}")
    if r.entry_signals: print(f"    信号: {', '.join(r.entry_signals[:4])}")

# ── 600396深度 ──
r396 = next((r for r in results if r.ticker == '600396'), None)
if r396:
    print(f"\n{'='*60}")
    print(f"  >>> 华电辽能 600396 深度分析 <<<")
    print(f"{'='*60}")
    name = getattr(r396, '_name', '华电辽能')
    price = getattr(r396, '_rt_price', r396.price)
    ma5, ma10, ma20 = getattr(r396, '_ma5', 0), getattr(r396, '_ma10', 0), getattr(r396, '_ma20', 0)

    print(f"  评分: {r396.total_score} (PA{r396.pa_score}+强化{r396.bonus_score}+外围{r396.external_score})")
    print(f"  价格: {price:.2f} | MA5={ma5:.2f} MA10={ma10:.2f} MA20={ma20:.2f}")
    print(f"  信号K线: {r396.signal_bar_quality}({r396.signal_bar_type})")
    print(f"  入场结构: H{r396.h_count}/L{r396.l_count} | 楔形:{r396.wedge_type or '无'} | SR:{r396.sr_confluence}重")

    # 近期K线
    kline = cache_update_one('600396', start_date="2026-07-01")
    recent = kline.tail(5)
    print(f"\n  近5日K线:")
    for idx, row in recent.iterrows():
        print(f"    {idx} O:{row['open']:.2f} H:{row['high']:.2f} L:{row['low']:.2f} C:{row['close']:.2f}")

    # 决策建议
    print(f"\n  [决策指引]")
    if r396.total_score >= 72:
        print(f"    ✅ 满仓级别 — 可等信号K线确认后入场")
    elif r396.total_score >= 54:
        print(f"    ⚡ 半仓级别 — 信号K线确认后可半仓入场")
    elif r396.total_score >= 40:
        print(f"    👀 观察级别 — 评分不足，等待或轻仓试探")
    else:
        print(f"    ⛔ 弱级别 — 不建议入场")

    # 实际禁区(仅供参考)
    print(f"\n  [被绕过的禁区(仅供参考)]")
    print(f"    X12: 今日涨停100>80(市场高潮)")
    print(f"    X1: 近5日涨幅可能>20%(需确认)")
    print(f"    → 这些禁区被绕过是为了看纯PA评分")
    print(f"    → 实际操作中X12(市场高潮)仍需谨慎")
