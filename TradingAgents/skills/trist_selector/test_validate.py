"""Quick validation: screen the user's 17 traded stocks."""
import noproxy  # MUST be first

import json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from screener import screen_single
from data_cache import update_batch as pull_kline_batch

# User's 17 stocks from delivery orders
HISTORY_STOCKS = {
    "600522": "中天科技", "600353": "旭光电子", "605358": "立昂微",
    "600487": "亨通光电", "601138": "工业富联", "601869": "长飞光纤",
    "605580": "恒盛能源", "002552": "宝鼎科技", "002126": "金海高科",
    "603256": "宏和科技", "002369": "胜通能源", "600186": "莲花控股",
    "603316": "诚邦股份", "600726": "华电辽能", "002428": "云南锗业",
    "603985": "恒润股份", "002407": "多氟多",
}

print("=" * 60)
print("  Trist Selector - Historical Stock Validation")
print("=" * 60)

tickers = list(HISTORY_STOCKS.keys())
klines = pull_kline_batch(tickers)

results = []
for ticker, kline_df in klines.items():
    name = HISTORY_STOCKS.get(ticker, "")
    price = float(kline_df["close"].values[-1])
    r = screen_single(ticker, name, price, kline_df)
    results.append(r)

results.sort(key=lambda x: x.total_score, reverse=True)

print(f"\n{'Rank':<5} {'Score':<6} {'Pos':<8} {'Name':<10} {'Price':<10} {'Core':<40} {'Signals'}")
print("-" * 110)

for i, r in enumerate(results):
    pos_map = {"full": "FULL", "half": "HALF", "observe": "WATCH"}
    core_emoji = "".join(["+" if v else "-" for v in r.core_details.values()])
    sig_str = ",".join(r.entry_signals[:2]) if r.entry_signals else "-"
    veto_str = "VETO:" + r.forbidden_hits[0][:20] if r.vetoed else ""

    print(f"{i+1:<5} {r.total_score:<6} {pos_map.get(r.position,'SKIP'):<8} "
          f"{r.name:<10} {r.price:<10.2f} {core_emoji:<40} {sig_str:<25} {veto_str}")

print(f"\n  FULL: {sum(1 for r in results if r.position=='full')} | "
      f"HALF: {sum(1 for r in results if r.position=='half')} | "
      f"WATCH: {sum(1 for r in results if r.position=='observe')} | "
      f"VETOED: {sum(1 for r in results if r.vetoed)}")
