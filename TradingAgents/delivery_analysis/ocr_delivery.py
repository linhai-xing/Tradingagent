"""
OCR script for Chinese stock delivery order images.
Uses cnocr to extract text, then parses trade data to CSV.
"""
import os
import re
import json
import sys

FOLDER = r"C:\Users\72955\Desktop\tradingagent\TradingAgents\delivery_order"
OUTPUT_CSV = r"C:\Users\72955\Desktop\tradingagent\TradingAgents\delivery_orders.csv"
OUTPUT_JSON = r"C:\Users\72955\Desktop\tradingagent\TradingAgents\delivery_orders.json"
RAW_TXT = r"C:\Users\72955\Desktop\tradingagent\TradingAgents\raw_ocr.txt"


def ocr_image(filepath, ocr):
    """Run OCR on a single image using cnocr."""
    results = ocr.ocr(filepath)
    lines = []
    for block in results:
        line_text = "".join([char["text"] for char in block])
        lines.append(line_text)
    return "\n".join(lines)


def parse_delivery_orders(text, filename):
    """Parse OCR text from a Chinese brokerage delivery order."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    full_text = " ".join(lines)

    trades = []

    date_pattern = r'(\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2})'
    stock_code_pattern = r'(\d{6})'
    amount_pattern = r'([\d,]+\.?\d*)'

    buy_keywords = ['买入', '买', 'BUY', '购买']
    sell_keywords = ['卖出', '卖', 'SELL']

    # Collect all dates in the document
    dates = re.findall(date_pattern, full_text)

    for i, line in enumerate(lines):
        direction = None
        if any(kw in line for kw in buy_keywords):
            direction = "买入"
        elif any(kw in line for kw in sell_keywords):
            direction = "卖出"

        if not direction:
            continue

        trade = {
            "filename": filename,
            "line": i + 1,
            "direction": direction,
            "raw_text": line,
        }

        # Stock code (6 digits)
        code_match = re.search(stock_code_pattern, line)
        if code_match:
            trade["stock_code"] = code_match.group(1)

        # Stock name
        name_match = re.search(
            r'([一-鿿]{2,6}(?:股份|科技|集团|控股|银行|证券|保险|医药|'
            r'能源|地产|汽车|电子|通信|传媒|食品|饮料|服装|化工|钢铁|矿业|航空|'
            r'铁路|港口|高速|电力|水务|燃气|环保|建筑|建材|家电|机械|军工|农业|'
            r'旅游|商业|物流|软件|互联网|半导体|新能源)?)',
            line
        )
        if name_match:
            trade["stock_name"] = name_match.group(1)

        # Monetary amounts
        amounts = re.findall(amount_pattern, line)
        monetary = []
        for a in amounts:
            try:
                val = float(a.replace(",", ""))
                if 0.01 < val < 100000000:
                    monetary.append(val)
            except ValueError:
                pass

        if monetary:
            trade["amount"] = max(monetary)
            sorted_vals = sorted(set(monetary))
            if len(sorted_vals) >= 2:
                # Price is typically the smallest non-unit number
                potential_prices = [v for v in sorted_vals if v < 10000]
                if potential_prices:
                    trade["price"] = potential_prices[0] if potential_prices[0] > 0.1 else potential_prices[-1]
                # Quantity is typically in lots of 100 shares
                potential_qty = [v for v in sorted_vals if v >= 100 and v < 1000000]
                if potential_qty:
                    trade["quantity"] = max(potential_qty) if len(potential_qty) <= 2 else sorted(potential_qty)[-2]

        # Date
        date_match = re.search(date_pattern, line)
        if date_match:
            trade["date"] = date_match.group(1)
        elif dates:
            trade["date"] = dates[0]

        trades.append(trade)

    return trades


def main():
    from cnocr import CnOcr

    print("Loading cnOCR model (this may take a moment on first run)...")
    ocr = CnOcr()

    files = sorted([
        f for f in os.listdir(FOLDER)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ])
    print(f"Found {len(files)} images.\n")

    all_trades = []
    raw_lines = []

    for idx, f in enumerate(files, 1):
        filepath = os.path.join(FOLDER, f)
        print(f"[{idx}/{len(files)}] Processing: {f}")
        text = ocr_image(filepath, ocr)

        raw_lines.append(f"=== {f} ===")
        raw_lines.append(text)
        raw_lines.append("")

        print("  --- OCR text ---")
        for line in text.split("\n"):
            if line.strip():
                print(f"  | {line.strip()}")
        print("  --- end ---\n")

        trades = parse_delivery_orders(text, f)
        print(f"  -> Detected {len(trades)} trade(s)")
        for t in trades:
            print(f"     {t.get('date','?')} | {t.get('direction','?')} | "
                  f"{t.get('stock_name','?')}({t.get('stock_code','?')}) | "
                  f"¥{t.get('amount','?')}")
        print()
        all_trades.extend(trades)

    # Save raw OCR text
    with open(RAW_TXT, "w", encoding="utf-8") as rf:
        rf.write("\n".join(raw_lines))
    print(f"Raw OCR saved to: {RAW_TXT}\n")

    # Save results
    import csv
    if all_trades:
        with open(OUTPUT_JSON, "w", encoding="utf-8") as jf:
            json.dump(all_trades, jf, ensure_ascii=False, indent=2)

        with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as cf:
            fieldnames = [
                "date", "direction", "stock_code", "stock_name",
                "price", "quantity", "amount", "filename", "raw_text"
            ]
            writer = csv.DictWriter(cf, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for t in all_trades:
                row = {k: t.get(k, "") for k in fieldnames}
                # Ensure date field maps correctly
                writer.writerow(row)

        print(f"Saved {len(all_trades)} trades:")
        print(f"  CSV:  {OUTPUT_CSV}")
        print(f"  JSON: {OUTPUT_JSON}")
    else:
        print("WARNING: No trades could be parsed automatically.")
        print("The raw OCR output has been saved for manual review.")


if __name__ == "__main__":
    main()
