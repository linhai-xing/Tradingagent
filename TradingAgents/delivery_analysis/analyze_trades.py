"""
Phase 1: Delivery order analysis - match trades, calculate P&L, extract patterns.
"""
import json, os, sys
from datetime import datetime, timedelta
from collections import defaultdict
from openpyxl import load_workbook

DELIVERY_XLSX = r"C:\Users\72955\Desktop\tradingagent\TradingAgents\delivery_analysis\delivery_orders.xlsx"
OUT_DIR = r"C:\Users\72955\Desktop\tradingagent\TradingAgents\delivery_analysis"

wb = load_workbook(DELIVERY_XLSX)
ws = wb.active

trades = []
for row in ws.iter_rows(min_row=2, values_only=True):
    seq, date_str, direction, stock_name, price, qty, amount, fee = row
    if seq is None or direction is None:
        break
    trades.append({
        "seq": int(seq),
        "datetime": datetime.strptime(str(date_str), "%Y-%m-%d %H:%M"),
        "date": str(date_str)[:10],
        "time": str(date_str)[11:16] if len(str(date_str)) > 10 else "",
        "direction": str(direction),
        "stock_name": str(stock_name),
        "price": float(price),
        "quantity": int(qty),
        "amount": float(amount),
        "fee": float(fee),
    })

print(f"Loaded {len(trades)} trades")

# Group by stock, match buys to sells (FIFO)
stocks = defaultdict(list)
for t in trades:
    stocks[t["stock_name"]].append(t)

# Sort each stock's trades by datetime
for s in stocks:
    stocks[s].sort(key=lambda x: x["datetime"])

# FIFO matching: match each buy with subsequent sells
matched_trades = []
unmatched = []

for stock_name, stock_trades in stocks.items():
    buy_queue = []  # FIFO queue of open buy positions

    for t in stock_trades:
        if t["direction"] == "买入":
            buy_queue.append(t)
        elif t["direction"] == "卖出":
            sell_qty = t["quantity"]
            while sell_qty > 0 and buy_queue:
                buy = buy_queue[0]
                match_qty = min(buy["quantity"], sell_qty)

                buy_cost = buy["price"] * match_qty
                sell_proceeds = t["price"] * match_qty
                gross_pnl = sell_proceeds - buy_cost
                net_pnl = gross_pnl - (buy["fee"] * match_qty / buy["quantity"]) - (t["fee"] * match_qty / t["quantity"])
                pnl_pct = (t["price"] / buy["price"] - 1) * 100
                hold_days = (t["datetime"] - buy["datetime"]).total_seconds() / 86400

                matched_trades.append({
                    "stock_name": stock_name,
                    "buy_date": buy["date"],
                    "buy_time": buy["time"],
                    "buy_price": buy["price"],
                    "sell_date": t["date"],
                    "sell_time": t["time"],
                    "sell_price": t["price"],
                    "quantity": match_qty,
                    "gross_pnl": round(gross_pnl, 2),
                    "net_pnl": round(net_pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "hold_days": round(hold_days, 2),
                    "buy_day_of_week": buy["datetime"].weekday(),
                    "sell_day_of_week": t["datetime"].weekday(),
                    "buy_hour": buy["datetime"].hour,
                    "sell_hour": t["datetime"].hour,
                })

                buy["quantity"] -= match_qty
                sell_qty -= match_qty

                if buy["quantity"] == 0:
                    buy_queue.pop(0)

            if sell_qty > 0:
                unmatched.append({"type": "oversell", "trade": t, "remaining": sell_qty})

    # Remaining buys (unclosed positions)
    for buy in buy_queue:
        unmatched.append({"type": "unclosed_buy", "trade": buy, "remaining": buy["quantity"]})

print(f"\nMatched {len(matched_trades)} buy-sell pairs")
print(f"Unmatched: {len(unmatched)}")

# Analyze matched trades
winners = [t for t in matched_trades if t["net_pnl"] > 0]
losers = [t for t in matched_trades if t["net_pnl"] <= 0]

print(f"\n=== P&L Summary ===")
print(f"Winning trades: {len(winners)} ({len(winners)/len(matched_trades)*100:.1f}%)")
print(f"Losing trades:  {len(losers)} ({len(losers)/len(matched_trades)*100:.1f}%)")
print(f"Total gross P&L: {sum(t['gross_pnl'] for t in matched_trades):,.2f}")
print(f"Total net P&L:   {sum(t['net_pnl'] for t in matched_trades):,.2f}")
print(f"Avg win: {sum(t['net_pnl'] for t in winners)/len(winners):,.2f}" if winners else "No winners")
print(f"Avg loss: {sum(t['net_pnl'] for t in losers)/len(losers):,.2f}" if losers else "No losers")
if winners and losers:
    print(f"Win/Loss ratio: {abs(sum(t['net_pnl'] for t in winners)/sum(t['net_pnl'] for t in losers)):.2f}")

# Group P&L by stock
print(f"\n=== P&L by Stock ===")
stock_pnl = defaultdict(lambda: {"trades": 0, "net_pnl": 0, "wins": 0, "losses": 0, "total_qty": 0})
for t in matched_trades:
    s = stock_pnl[t["stock_name"]]
    s["trades"] += 1
    s["net_pnl"] += t["net_pnl"]
    s["total_qty"] += t["quantity"]
    if t["net_pnl"] > 0: s["wins"] += 1
    else: s["losses"] += 1

for name, s in sorted(stock_pnl.items(), key=lambda x: x[1]["net_pnl"], reverse=True):
    win_rate = s["wins"] / s["trades"] * 100 if s["trades"] > 0 else 0
    bar = "WIN" if s["net_pnl"] > 0 else "LOSS"
    print(f"  {bar} {name:6s}: {s['trades']:2d} trades, net ¥{s['net_pnl']:>10,.2f}, win rate {win_rate:.0f}%")

# Analyze patterns
print(f"\n=== Hold Duration Analysis ===")
for label, group in [("Winners", winners), ("Losers", losers)]:
    if group:
        avg_hold = sum(t["hold_days"] for t in group) / len(group)
        print(f"  {label}: avg hold {avg_hold:.1f} days")
        # Distribution
        ultra_short = sum(1 for t in group if t["hold_days"] < 1)
        short = sum(1 for t in group if 1 <= t["hold_days"] < 3)
        medium = sum(1 for t in group if 3 <= t["hold_days"] < 7)
        long_p = sum(1 for t in group if t["hold_days"] >= 7)
        print(f"    <1d: {ultra_short}, 1-3d: {short}, 3-7d: {medium}, 7d+: {long_p}")

print(f"\n=== Buy Time Analysis ===")
for label, group in [("Winners", winners), ("Losers", losers)]:
    if group:
        morning = sum(1 for t in group if t["buy_hour"] < 10)
        midday = sum(1 for t in group if 10 <= t["buy_hour"] < 11)
        afternoon = sum(1 for t in group if t["buy_hour"] >= 11)
        print(f"  {label}: morning(9-10am): {morning}, midday(10-11am): {midday}, afternoon: {afternoon}")

print(f"\n=== Day of Week Analysis ===")
day_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
for label, group in [("Winners", winners), ("Losers", losers)]:
    by_day = defaultdict(lambda: {"count": 0, "pnl": 0})
    for t in group:
        d = day_names[t["buy_day_of_week"]]
        by_day[d]["count"] += 1
        by_day[d]["pnl"] += t["net_pnl"]
    parts = []
    for d in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
        if by_day[d]["count"] > 0:
            avg = by_day[d]["pnl"] / by_day[d]["count"]
            parts.append(f"{d}:{by_day[d]['count']}笔(avg ¥{avg:.0f})")
    print(f"  {label}: {', '.join(parts)}")

# P&L by position size
print(f"\n=== Position Size Analysis ===")
for label, group in [("Winners", winners), ("Losers", losers)]:
    small = sum(1 for t in group if t["quantity"] <= 200)
    medium = sum(1 for t in group if 200 < t["quantity"] <= 800)
    large = sum(1 for t in group if t["quantity"] > 800)
    print(f"  {label}: small(<=200): {small}, medium(200-800): {medium}, large(>800): {large}")

# Save detailed matched trades for K-line analysis
def json_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

with open(os.path.join(OUT_DIR, "matched_trades.json"), "w", encoding="utf-8") as f:
    json.dump({
        "matched": matched_trades,
        "unmatched": unmatched,
        "summary": {
            "total_trades": len(matched_trades),
            "winners": len(winners),
            "losers": len(losers),
            "win_rate": round(len(winners)/len(matched_trades)*100, 1) if matched_trades else 0,
            "total_pnl": round(sum(t["net_pnl"] for t in matched_trades), 2),
            "avg_win": round(sum(t["net_pnl"] for t in winners)/len(winners), 2) if winners else 0,
            "avg_loss": round(sum(t["net_pnl"] for t in losers)/len(losers), 2) if losers else 0,
        }
    }, f, ensure_ascii=False, indent=2, default=json_serializer)

print(f"\nSaved matched trades to matched_trades.json")

# Output per-stock trade details for K-line analysis
stock_symbols = {
    "中天科技": "600522", "旭光电子": "600353", "立昂微": "605358",
    "亨通光电": "600487", "工业富联": "601138", "长飞光纤": "601869",
    "恒盛能源": "605580", "宝鼎科技": "002552", "金海高科": "002126",
    "宏和科技": "603256", "胜通能源": "002369", "莲花控股": "600186",
    "诚邦股份": "603316", "华电辽能": "600726", "云南锗业": "002428",
    "恒润股份": "603985", "多氟多": "002407",
}

with open(os.path.join(OUT_DIR, "stock_symbols.json"), "w", encoding="utf-8") as f:
    json.dump(stock_symbols, f, ensure_ascii=False, indent=2)

print(f"Stock symbols saved. Ready for K-line analysis.")
