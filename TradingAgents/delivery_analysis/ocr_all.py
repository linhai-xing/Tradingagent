from rapidocr_onnxruntime import RapidOCR
import os, json, re

FOLDER = r"C:\Users\72955\Desktop\tradingagent\TradingAgents\delivery_order"
OUT_RAW = r"C:\Users\72955\Desktop\tradingagent\TradingAgents\ocr_raw.json"

ocr = RapidOCR()
files = sorted([f for f in os.listdir(FOLDER) if f.lower().endswith(".jpg")])

all_results = {}
for f in files:
    path = os.path.join(FOLDER, f)
    result, _ = ocr(path)
    if result:
        lines = []
        for box, text, score in result:
            if score > 0.5:
                lines.append({"text": text, "score": round(float(score), 2)})
        all_results[f] = lines
        print(f"=== {f} ({len(lines)} text blocks) ===")
        for item in lines:
            print(f"  [{item['score']}] {item['text']}")
        print()

with open(OUT_RAW, "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)
print(f"Saved raw OCR to: {OUT_RAW}")
