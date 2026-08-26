"""
电力板块 — 纯PA评分 (X12+X1+X9+X7完全绕过)
关键: patch _check_forbidden 防止early return
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
from scoring import TristScorer, build_market_context, ScoreResult
from entry_signals import detect_entry_signals, get_entry_recommendation
import scoring as sc

# ═══════════════════════════════════════════════════════════
# PATCH 1: 绕开_check_forbidden的early return
# ═══════════════════════════════════════════════════════════
orig_check_forbidden = sc.TristScorer._check_forbidden
def patched_check_forbidden(self, result, data, sector):
    # 先调原始检查，拿到hit列表
    hits = []
    F = self.rules["forbidden"]

    # X1: 5日涨幅>20% (bypass - 我们想看纯粹PA分)
    ret_5d = data.get("pre_5d_return", 0)
    # 不检查X1 — SKIP

    # X2: 换手率+市值
    turnover = data.get("avg_turnover_5d", 5)
    float_cap = data.get("float_cap", 1e10)
    if turnover < F.get("X2_liquidity", {}).get("min_turnover", 1):
        pass  # 不触发
    if float_cap and float_cap < F.get("X2_liquidity", {}).get("min_float_cap", 2e9):
        hits.append(f"X2:流通市值{float_cap/1e8:.0f}亿<20亿(流动性差)")

    # X3: 庄股嫌疑
    up_days_20 = data.get("up_days_ratio_20d", 0)
    if up_days_20 > F.get("X3_zhuanggu", {}).get("max_up_days_ratio", 0.85):
        hits.append(f"X3:20日上涨天数占比{up_days_20:.0%}>85%(庄股嫌疑)")

    # X4: 利空
    bad_news = data.get("bad_news_count", 0)
    if bad_news > 0:
        hits.append(f"X4:近期利空消息{bad_news}条")

    # X5: 跳过(首次接触)

    # X6: 大盘崩
    bench = self.ctx.get("benchmark", {})
    if bench.get("decline_5d", 0) < F.get("X6_market_crash", {}).get("max_decline_5d", -0.10):
        hits.append(f"X6:大盘5日跌{bench['decline_5d']:.1%}>10%")

    # X7: 涨停次日 (bypass)
    # SKIP

    # X8: 仓位>25% (bypass)
    # SKIP

    # X9: MA5死叉 (bypass)
    # SKIP

    # X10: 拉萨上榜
    lhb_seats = data.get("lhb_seats", [])
    lasa_kws = F.get("X10_lasa_seats", {}).get("lasa_keywords", [])
    if any(any(kw in str(s) for kw in lasa_kws) for s in lhb_seats):
        hits.append("X10:拉萨天团上榜")

    # X11: 佛山砸盘
    foshan_kws = F.get("X11_foshan_seats", {}).get("foshan_keywords", [])
    if any(any(kw in str(s) for kw in foshan_kws) for s in lhb_seats):
        hits.append("X11:佛山系上榜")

    # X12: 市场高潮 (bypass — 今天100涨停, 由半导体带动, 电力无关)
    # SKIP

    # X15: 外围风险
    external_blocked = getattr(result, 'external_blocked', False)
    if external_blocked:
        hits.append("X15:外围风险过高(外盘大跌)")

    result.forbidden_hits = hits
    # 强制不清veto — 继续PA评分
    # result.vetoed = (len(hits) > 0)  ← 不执行!
    result.vetoed = False
sc.TristScorer._check_forbidden = patched_check_forbidden

# ═══════════════════════════════════════════════════════════
# PATCH 2: 顺带修MA5绕过X9的残留影响
# ═══════════════════════════════════════════════════════════
orig_score = sc.TristScorer.score
def patched_score(self, data, sector=None, discipline=None):
    orig_ma5 = data.get("ma5", 0)
    orig_ma10 = data.get("ma10", 0)
    if orig_ma5 < orig_ma10 and orig_ma10 > 0:
        data["ma5"] = orig_ma10 + 0.01
    if data.get("pre_5d_return", 0) > 0.20:
        data["pre_5d_return"] = 0.15
    if data.get("prev_day_limit_up", False):
        data["prev_day_limit_up"] = False

    result = orig_score(self, data, sector, discipline)

    data["ma5"] = orig_ma5
    data["ma10"] = orig_ma10
    return result
sc.TristScorer.score = patched_score

print("=" * 60)
print("  电力板块 — 纯PA评分 (_check_forbidden bypass)")
print("  绕过: X1 X7 X9 X12 | 保留: X2 X3 X4 X6 X10 X11 X15")
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
        kline = cache_update_one(ticker, start_date="2026-01-01")
        if kline is None or len(kline) < 20: continue

        ind = compute_indicators(kline)
        if not ind: continue

        rt = _get_tencent_quote(ticker)
        time.sleep(0.08)
        price = rt.get('price', float(kline["close"].values[-1])) if rt else float(kline["close"].values[-1])
        change_pct = rt.get('change_pct', 0) if rt else 0

        ind["ticker"] = ticker; ind["name"] = name
        ind["price"] = price; ind["is_realtime"] = True
        if change_pct != 0: ind["today_ret"] = change_pct / 100

        result = scorer.score(ind, {})

        kline_dict = {
            "closes": kline["close"].tolist(), "opens": kline["open"].tolist(),
            "highs": kline["high"].tolist(), "lows": kline["low"].tolist(),
            "volumes": kline["volume"].tolist(),
        }
        signals = detect_entry_signals(kline_dict, ticker)
        result.entry_signals = [s.name for s in signals]

        closes = kline["close"].values
        result._ma5 = pd.Series(closes).rolling(5).mean().values[-1]
        result._ma10 = pd.Series(closes).rolling(10).mean().values[-1]
        result._ma20 = pd.Series(closes).rolling(20).mean().values[-1]
        result._rt_price = price
        result._rt_change = change_pct
        result._name = name

        results.append(result)
    except Exception as e:
        continue

results.sort(key=lambda x: x.total_score, reverse=True)

print(f"\n{'='*60}")
print(f"  电力板块 纯PA排名 ({len(results)}只)")
print(f"{'='*60}")

for i, r in enumerate(results):
    name = getattr(r, '_name', '')
    price = getattr(r, '_rt_price', r.price)
    change = getattr(r, '_rt_change', 0)
    ma5, ma10, ma20 = getattr(r, '_ma5', 0), getattr(r, '_ma10', 0), getattr(r, '_ma20', 0)
    if ma5 > ma10 > ma20: ms = "MA多头"
    elif price > ma20: ms = "站上MA20"
    else: ms = "MA空头"

    if r.total_score >= 72: tag = "\033[1;32m[满仓]\033[0m"
    elif r.total_score >= 54: tag = "\033[1;33m[半仓]\033[0m"
    elif r.total_score >= 40: tag = "[观察]"
    else: tag = "[弱]"

    print(f"\n  #{i+1} {tag} {name}({r.ticker}) {r.total_score}分 @{price:.2f} {change:+.1f}% {ms}")
    if r.pa_details:
        pas = [f"{k}:{v:+d}" for k,v in sorted(r.pa_details.items()) if v != 0]
        if pas: print(f"    PA: {' | '.join(pas)}")
    print(f"    PA{r.pa_score}+强化{r.bonus_score}+外围{r.external_score} | 市场:{r.market_state or '?'} K线:{r.signal_bar_quality or '?'}({r.signal_bar_type or '-'})")
    print(f"    H{r.h_count}/L{r.l_count} | 楔形:{r.wedge_type or '-'} | SR:{r.sr_confluence}重")
    if r.bonus_details:
        hits = [f"{k}" for k,v in r.bonus_details.items() if v and v is not False]
        if hits: print(f"    强化: {', '.join(hits)}")
    if r.entry_signals: print(f"    信号: {', '.join(r.entry_signals[:4])}")
    # show remaining vetoes
    remaining = [h for h in (r.forbidden_hits if hasattr(r,'forbidden_hits') else [])]
    if remaining: print(f"    ⚠️剩余禁区: {remaining}")

# ── 600396 deep dive ──
r396 = next((r for r in results if r.ticker == '600396'), None)
if r396:
    print(f"\n{'='*60}")
    print(f"  >>> 华电辽能 600396 <<<")
    print(f"{'='*60}")
    ma5, ma10, ma20 = getattr(r396, '_ma5', 0), getattr(r396, '_ma10', 0), getattr(r396, '_ma20', 0)
    p = getattr(r396, '_rt_price', r396.price)

    print(f"  评分: {r396.total_score} (PA{r396.pa_score}+强化{r396.bonus_score}+外围{r396.external_score})")
    print(f"  价格: {p:.2f} | MA5={ma5:.2f} MA10={ma10:.2f} MA20={ma20:.2f}")
    print(f"  市场: {r396.market_state} | K线: {r396.signal_bar_quality}({r396.signal_bar_type})")
    print(f"  H{r396.h_count}/L{r396.l_count} | 楔形:{r396.wedge_type or '无'} | SR:{r396.sr_confluence}")

    kline = cache_update_one('600396', start_date="2026-07-15")
    recent = kline.tail(8)
    print(f"\n  近8日K线:")
    for idx, row in recent.iterrows():
        print(f"    {idx} O:{row['open']:.2f} H:{row['high']:.2f} L:{row['low']:.2f} C:{row['close']:.2f}")

    # 计算ATR
    closes = kline["close"].values
    trs = [max(kline["high"].values[j] - kline["low"].values[j],
              abs(kline["high"].values[j] - closes[j-1]),
              abs(kline["low"].values[j] - closes[j-1]))
           for j in range(1, len(closes))]
    atr5 = np.mean(trs[-5:])
    atr14 = np.mean(trs[-14:])

    print(f"\n  ATR5: {atr5:.2f} ({atr5/p*100:.1f}%) | ATR14: {atr14:.2f} ({atr14/p*100:.1f}%)")

    # 20日高低
    h20 = kline["high"].tail(20).max()
    l20 = kline["low"].tail(20).min()
    pos_20d = (p - l20) / (h20 - l20) * 100
    print(f"  20日高低: {h20:.2f}/{l20:.2f} | 位置: {pos_20d:.0f}%")

    print(f"\n  [决策指引]")
    if r396.total_score >= 72:
        print(f"    ✅ 满仓级 — 可入场")
    elif r396.total_score >= 54:
        print(f"    ⚡ 半仓级 — 信号K线确认后入场")
    else:
        print(f"    ⚠️ 评分不足 ({r396.total_score}<54) — 不满足半仓标准")
