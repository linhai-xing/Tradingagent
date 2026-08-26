# Trist Selector v3.0 — 100分制评分体系实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Trist Selector 评分体系从 v2.x（240分制）升级到 v3.0（100分制），并加入外围半导体市场风险因子。

**Architecture:** 修改 rules.json 权重分配（核心60+强化30），新增 external_factors.py 通过 yfinance 获取美股/日韩半导体行情计算扣分，scoring.py 加入 _score_external 和 X15 禁区，screener.py 集成外围数据获取。

**Tech Stack:** Python 3.13, baostock, akshare, yfinance, pandas, requests

## Global Constraints

- 总分上限 100（核心 60 + 强化 30 + 外围 10）
- 禁区一票否决制保持不变
- 外围因子为惩罚项：默认 10 分，触发风险条件扣分，最低 0 分
- X15 禁区触发条件：外围因子 = 0 且 行业相关性 > 0.5
- C2 15 分、C5 15 分（交易者画像最高权重）
- B2 6 分、B6 6 分（用户指定强化最高权重）
- 行业相关性系数低相关行业扣分减半

---

### Task 1: Install yfinance dependency

**Files:**
- Modify: `TradingAgents/requirements.txt`

**Interfaces:**
- Produces: yfinance available in venv for Task 3

- [ ] **Step 1: Install yfinance**

```bash
& "C:\Users\72955\Desktop\tradingagent\TradingAgents\.venv\Scripts\python.exe" -m pip install yfinance -q
```

Expected: Successfully installed yfinance

- [ ] **Step 2: Verify import works**

```bash
& "C:\Users\72955\Desktop\tradingagent\TradingAgents\.venv\Scripts\python.exe" -c "import yfinance as yf; print('yfinance', yf.__version__)"
```

Expected: `yfinance X.X.X`

---

### Task 2: Update rules.json with v3.0 weights

**Files:**
- Modify: `TradingAgents/skills/trist_selector/rules.json`

**Interfaces:**
- Produces: New weight values consumed by scoring.py Tasks 5-6

- [ ] **Step 1: Update core rule weights**

Replace the entire `"core"` section in rules.json:

```json
"core": {
    "C1_trend": {
      "weight": 10,
      "description": "趋势确认：股价在 MA10 上方",
      "ma_trend": 10
    },
    "C2_no_chase": {
      "weight": 15,
      "description": "非追高：近5日涨幅 < 15%，当日非涨停板追入",
      "max_pre5d_return": 0.15
    },
    "C3_volume": {
      "weight": 10,
      "description": "量能活跃：日均换手 2%-20%，当日量比 0.5-3.0",
      "min_turnover_5d": 0.02, "max_turnover_5d": 0.20,
      "min_vol_ratio": 0.5, "max_vol_ratio": 3.0
    },
    "C4_sector": {
      "weight": 5,
      "description": "主线题材：板块近10日涨幅排名全市场前40%",
      "sector_rank_top_pct": 0.40, "sector_lookback_days": 10
    },
    "C5_emotion": {
      "weight": 15,
      "description": "情绪周期：涨停家数+连板高度判断冰点/分歧/一致/高潮",
      "ice_limit_up_max": 30, "ice_chain_max": 2,
      "diverge_limit_up_min": 30, "diverge_limit_up_max": 50, "diverge_chain_min": 3, "diverge_chain_max": 4,
      "consensus_limit_up_min": 50, "consensus_limit_up_max": 80, "consensus_chain_min": 5,
      "euphoria_limit_up_min": 80
    },
    "C6_leader": {
      "weight": 5,
      "description": "龙头地位：涨停时间/封单/板块带动/连板高度四维判定",
      "sector_leader_top_n": 3,
      "min_follower_count": 3,
      "min_chain_days": 2
    }
}
```

- [ ] **Step 2: Update strengthen rule weights**

Replace the entire `"strengthen"` section:

```json
"strengthen": {
    "B1_leader_rank": {
      "weight": 2,
      "description": "龙头辨识度：同板块近5日涨幅 Top 3",
      "leader_top_n": 3
    },
    "B2_divergence": {
      "weight": 6,
      "description": "分歧转一致：前日放量阴线 + 今日缩量阳线反包",
      "prev_day_vol_min_ratio": 1.2, "today_vol_max_ratio": 0.8
    },
    "B3_research": {
      "weight": 2,
      "description": "机构背书：近30日 >= 2家券商买入/增持",
      "min_brokers": 2, "min_buy_pct": 60
    },
    "B4_pullback": {
      "weight": 4,
      "description": "合理回调：距20日高点回调 3%-12%",
      "pullback_min_pct": 0.03, "pullback_max_pct": 0.12
    },
    "B5_earnings": {
      "weight": 2,
      "description": "盈利拐点：最新季报净利同比 > 30% 或扭亏",
      "min_net_profit_growth": 0.30
    },
    "B6_weak_to_strong": {
      "weight": 6,
      "description": "弱转强：前3日缩量弱势，今日放量(>1.3x)收中阳(>3%)突破",
      "lookback_days": 3, "max_ret_3d": 0.03, "min_ret_today": 0.03, "min_vol_ratio": 1.3
    },
    "B7_first_board": {
      "weight": 3,
      "description": "低位首板：近20日涨幅 < 20%，首板或二板",
      "max_ret_20d": 0.20, "max_chain": 2
    },
    "B8_seat_match": {
      "weight": 3,
      "description": "游资席位共振：龙虎榜出现知名游资净买入",
      "elite_seats": ["国泰君安上海江苏路","中信上海溧阳路","兴业陕西分公司","中信西安朱雀大街","浙商绍兴解放北路","华鑫上海红宝石路","国泰君安南京太平南路","招商福州六一中路"]
    },
    "B9_big_capital": {
      "weight": 2,
      "description": "大资金容量：日均成交 > 5亿，流通市值 > 50亿",
      "min_daily_amount": 500000000, "min_float_cap": 5000000000
    }
}
```

- [ ] **Step 3: Add external factors and X15 forbidden config**

Add after the `"strengthen"` section (before `"forbidden"`):

```json
"external": {
    "_comment": "外围市场风险因子 — 默认10分，触发条件扣分，最低0分",
    "max_score": 10,
    "min_score": 0,
    "deductions": {
      "smh_2d_drop_5pct": 3,
      "smh_2d_drop_10pct": 5,
      "nvda_single_day_drop_5pct": 3,
      "three_or_more_drop_3pct": 3,
      "consecutive_3d_decline": 3
    },
    "tracking_symbols": {
      "NVDA": "AI算力总龙头",
      "AMD": "数据中心GPU",
      "MU": "存储半导体",
      "AVGO": "网络芯片/AI ASIC",
      "SMH": "半导体板块ETF",
      "000660.KS": "SK Hynix HBM存储",
      "8035.T": "Tokyo Electron 半导体设备"
    }
}
```

Add X15 to the `"forbidden"` section (after X12):

```json
"X15_external_risk": {
    "description": "外围系统性风险：外围因子归零且行业相关性 > 0.5",
    "external_score_threshold": 0,
    "min_correlation": 0.5
}
```

- [ ] **Step 4: Verify JSON is valid**

```bash
& "C:\Users\72955\Desktop\tradingagent\TradingAgents\.venv\Scripts\python.exe" -c "import json; f=open(r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector\rules.json','r',encoding='utf-8'); d=json.load(f); f.close(); print('OK - core weights:', {k:v['weight'] for k,v in d['core'].items()}); print('strengthen weights:', {k:v['weight'] for k,v in d['strengthen'].items()}); print('external max:', d['external']['max_score']); print('X15:', d['forbidden']['X15_external_risk']['description'])"
```

Expected: Prints all weights and X15 description without errors.

---

### Task 3: Create correlation_map.json

**Files:**
- Create: `TradingAgents/skills/trist_selector/correlation_map.json`

**Interfaces:**
- Produces: `get_sector_correlation(sector_name: str) -> float` via external_factors.py Task 4

- [ ] **Step 1: Create the correlation mapping file**

```json
{
  "_comment": "行业 → 外围半导体相关性系数 (1.0=高相关, 0.7=中相关, 0.5=低相关)",
  "_usage": "外围扣分 = 原始扣分 × correlation_coefficient, 四舍五入取整",
  "high": {
    "coefficient": 1.0,
    "sectors": [
      "半导体", "光模块", "CPO", "存储芯片", "AI芯片",
      "消费电子", "PCB", "先进封装", "HBM", "算力",
      "集成电路", "芯片", "电子元器件"
    ]
  },
  "medium": {
    "coefficient": 0.7,
    "sectors": [
      "通信设备", "IT设备", "软件服务", "互联网",
      "计算机", "5G", "物联网", "机器人", "自动化",
      "电子", "光电"
    ]
  },
  "low": {
    "coefficient": 0.5,
    "sectors": [
      "医药", "医疗", "食品饮料", "白酒", "家电",
      "银行", "保险", "券商", "房地产", "建筑",
      "建材", "化工", "有色", "钢铁", "煤炭",
      "电力", "新能源", "汽车", "军工", "农业",
      "纺织", "商贸", "旅游", "传媒", "环保",
      "公用事业", "交通运输"
    ]
  },
  "default_coefficient": 0.7
}
```

- [ ] **Step 2: Verify JSON is valid**

```bash
& "C:\Users\72955\Desktop\tradingagent\TradingAgents\.venv\Scripts\python.exe" -c "import json; f=open(r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector\correlation_map.json','r',encoding='utf-8'); d=json.load(f); f.close(); print('OK - high:', len(d['high']['sectors']), 'medium:', len(d['medium']['sectors']), 'low:', len(d['low']['sectors']))"
```

Expected: `OK - high: 11 medium: 10 low: 25`

---

### Task 4: Create external_factors.py

**Files:**
- Create: `TradingAgents/skills/trist_selector/external_factors.py`

**Interfaces:**
- Consumes: `correlation_map.json` (Task 3), `rules.json` (Task 2)
- Produces: `fetch_external_quotes() -> dict`, `get_sector_correlation(sector_name: str) -> float`, `compute_external_score(sector_name: str) -> tuple[int, list[str], dict]`
- Consumed by: screener.py Task 7

- [ ] **Step 1: Create the module with all three functions**

```python
"""
External market risk factor module for Trist Selector v3.0.
Fetches US/Japan/Korea semiconductor stock data via yfinance,
computes deduction scores for A-share stocks based on sector correlation.
"""
import os, json, time
from typing import Optional

import yfinance as yf

RULES_PATH = os.path.join(os.path.dirname(__file__), "rules.json")
CORRELATION_PATH = os.path.join(os.path.dirname(__file__), "correlation_map.json")

# Cache: refresh once per day
_cache = {"timestamp": 0, "quotes": {}, "valid_until": 0}


def _load_rules() -> dict:
    with open(RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_correlation() -> dict:
    with open(CORRELATION_PATH, encoding="utf-8") as f:
        return json.load(f)


def fetch_external_quotes(force_refresh: bool = False) -> dict:
    """
    Fetch last 5 trading days of OHLCV for tracked external symbols.
    Returns dict: {symbol: {"close": [float x5], "change_2d": float, "change_1d": float}}
    Cached: refreshes at most once per hour (3600s) unless force_refresh=True.
    """
    now = time.time()
    if not force_refresh and _cache["quotes"] and (now - _cache["timestamp"]) < 3600:
        return _cache["quotes"]

    rules = _load_rules()
    symbols = list(rules["external"]["tracking_symbols"].keys())
    
    result = {}
    try:
        for sym in symbols:
            try:
                ticker = yf.Ticker(sym)
                hist = ticker.history(period="5d")
                if len(hist) >= 2:
                    closes = hist["Close"].tolist()
                    chg_1d = (closes[-1] / closes[-2] - 1) * 100 if len(closes) >= 2 else 0
                    chg_2d = (closes[-1] / closes[-3] - 1) * 100 if len(closes) >= 3 else chg_1d
                    result[sym] = {
                        "close": closes,
                        "change_1d": round(chg_1d, 2),
                        "change_2d": round(chg_2d, 2),
                        "consecutive_down": _count_consecutive_down(hist),
                    }
                time.sleep(0.3)  # rate limit
            except Exception:
                result[sym] = {"error": "fetch_failed", "change_1d": 0, "change_2d": 0, "consecutive_down": 0}
    except Exception:
        pass

    _cache["quotes"] = result
    _cache["timestamp"] = now
    return result


def _count_consecutive_down(hist) -> int:
    """Count consecutive down days from most recent."""
    closes = hist["Close"].tolist()
    count = 0
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] < closes[i - 1]:
            count += 1
        else:
            break
    return count


def get_sector_correlation(sector_name: str) -> float:
    """
    Get correlation coefficient for a sector name.
    Returns 1.0 (high), 0.7 (medium), 0.5 (low), or default 0.7.
    Performs substring matching — e.g. "半导体设备" matches "半导体".
    """
    corr = _load_correlation()
    default = corr.get("default_coefficient", 0.7)
    
    for level in ["high", "medium", "low"]:
        for keyword in corr[level]["sectors"]:
            if keyword in sector_name:
                return corr[level]["coefficient"]
    return default


def compute_external_score(sector_name: str = "") -> tuple:
    """
    Compute external risk deduction score.
    
    Args:
        sector_name: Stock's industry/sector name for correlation adjustment
    
    Returns:
        (score: int, reasons: list[str], details: dict)
        score is 0-10, 10 = no risk, 0 = maximum risk
    """
    rules = _load_rules()
    ext_rules = rules["external"]
    deductions = ext_rules["deductions"]
    max_score = ext_rules["max_score"]
    
    quotes = fetch_external_quotes()
    if not quotes:
        return (max_score, ["外围数据获取失败，默认满分"], {"raw_deduction": 0, "correlation": 0})
    
    correlation = get_sector_correlation(sector_name) if sector_name else 0.7
    raw_deduction = 0
    reasons = []

    # Check SMH (semiconductor ETF) — broadest signal
    smh = quotes.get("SMH", {})
    smh_2d = smh.get("change_2d", 0)
    if smh_2d < -10:
        raw_deduction += deductions["smh_2d_drop_10pct"]
        reasons.append(f"SMH 2日跌{smh_2d:.1f}% (>10%)")
    elif smh_2d < -5:
        raw_deduction += deductions["smh_2d_drop_5pct"]
        reasons.append(f"SMH 2日跌{smh_2d:.1f}% (>5%)")

    # Check NVDA single-day
    nvda = quotes.get("NVDA", {})
    nvda_1d = nvda.get("change_1d", 0)
    if nvda_1d < -5:
        raw_deduction += deductions["nvda_single_day_drop_5pct"]
        reasons.append(f"NVDA单日跌{nvda_1d:.1f}%")

    # Check 3+ symbols dropping >3% same day
    drop_count = sum(1 for q in quotes.values() if q.get("change_1d", 0) < -3)
    if drop_count >= 3:
        raw_deduction += deductions["three_or_more_drop_3pct"]
        reasons.append(f"{drop_count}只外围标的同日跌>3%")

    # Check consecutive decline
    consec_count = sum(1 for q in quotes.values() if q.get("consecutive_down", 0) >= 3)
    if consec_count >= 1:
        raw_deduction += deductions["consecutive_3d_decline"]
        reasons.append(f"{consec_count}只外围标的连续3日阴线")

    # Apply correlation coefficient
    adjusted_deduction = round(raw_deduction * correlation)
    final_score = max(max_score - adjusted_deduction, ext_rules["min_score"])
    
    details = {
        "raw_deduction": raw_deduction,
        "correlation": correlation,
        "adjusted_deduction": adjusted_deduction,
        "final_score": final_score,
        "quotes_summary": {s: {"chg_1d": q.get("change_1d", 0), "chg_2d": q.get("change_2d", 0)} 
                           for s, q in quotes.items()},
    }
    
    return (final_score, reasons, details)
```

- [ ] **Step 2: Verify module imports correctly**

```bash
& "C:\Users\72955\Desktop\tradingagent\TradingAgents\.venv\Scripts\python.exe" -c "
import sys; sys.path.insert(0, r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector')
from external_factors import get_sector_correlation, fetch_external_quotes
print('corr 半导体:', get_sector_correlation('半导体'))
print('corr 医药:', get_sector_correlation('医药'))
print('corr unknown:', get_sector_correlation('zzz'))
print('Module loaded successfully')
"
```

Expected: Prints correlation values (1.0, 0.5, 0.7) and success message.

---

### Task 5: Update scoring.py — core + strengthen + ScoreResult

**Files:**
- Modify: `TradingAgents/skills/trist_selector/scoring.py`

**Interfaces:**
- Consumes: `rules.json` v3.0 weights (Task 2)
- Produces: Updated `ScoreResult` with `external_score`, `external_reasons`, `external_details`, updated `_score_core`, `_score_strengthen` with new weights, new `_score_external` method, updated `_check_forbidden` with X15
- Consumed by: screener.py Task 7

- [ ] **Step 1: Add external fields to ScoreResult dataclass**

Add these fields to the `ScoreResult` dataclass (after `discipline_hits`):

```python
    external_score: int = 10
    external_reasons: List[str] = field(default_factory=list)
    external_details: dict = field(default_factory=dict)
    external_blocked: bool = False  # X15 triggered
```

- [ ] **Step 2: Update C5 emotion scoring logic**

Replace the C5 block in `_score_core` (lines 226-247) to match v3.0 spec: ice/diverge = full 15pts, consensus = 7pts (half), euphoria = 0pts:

```python
        # ── C5: Emotion cycle ──
        lu = self.ctx.get("limit_up_count", 0)
        chain = self.ctx.get("max_chain_height", 0)

        if lu <= C["C5_emotion"]["ice_limit_up_max"] and chain <= C["C5_emotion"]["ice_chain_max"]:
            c5_score = C["C5_emotion"]["weight"]  # 15
            phase = "ice"
        elif lu <= C["C5_emotion"]["diverge_limit_up_max"] and chain <= C["C5_emotion"]["diverge_chain_max"]:
            c5_score = C["C5_emotion"]["weight"]  # 15
            phase = "diverge"
        elif lu <= C["C5_emotion"]["consensus_limit_up_max"] and chain >= C["C5_emotion"]["consensus_chain_min"]:
            c5_score = C["C5_emotion"]["weight"] // 2  # 7.5→7 (half)
            phase = "consensus"
        elif lu >= C["C5_emotion"]["euphoria_limit_up_min"]:
            c5_score = 0
            phase = "euphoria"
        else:
            c5_score = C["C5_emotion"]["weight"]  # default full if data unavailable
            phase = "unknown"

        score += c5_score
        result.core_details["C5_emotion"] = c5_score >= 7
        result.emotion_phase = phase
```

- [ ] **Step 3: Update C6 leader scoring threshold**

Change `c6_score >= 15` to `c6_score >= 3` in line 272:
```python
        result.core_details["C6_leader"] = c6_score >= 3
```

- [ ] **Step 4: Add _score_external method to TristScorer**

Add this new method after `_score_strengthen`:

```python
    def _score_external(self, result: ScoreResult, sector_name: str = ""):
        """Compute external risk factor score (0-10, deduction-based)."""
        try:
            from external_factors import compute_external_score
            score, reasons, details = compute_external_score(sector_name)
            result.external_score = score
            result.external_reasons = reasons
            result.external_details = details
        except Exception:
            result.external_score = 10
            result.external_reasons = ["外围数据获取异常，默认满分"]
```

- [ ] **Step 5: Add X15 check to _check_forbidden**

Add this block at the end of `_check_forbidden` (before the `if hits:` block):

```python
        # X15: External systemic risk
        if hasattr(result, 'external_score') and result.external_score is not None:
            from external_factors import get_sector_correlation
            sector_name = data.get("sector", "")
            corr = get_sector_correlation(sector_name) if sector_name else 0.7
            x15_cfg = F.get("X15_external_risk", {})
            if result.external_score <= x15_cfg.get("external_score_threshold", 0):
                if corr >= x15_cfg.get("min_correlation", 0.5):
                    hits.append(f"X15:外围系统性风险(外围因子归零,行业相关性{corr:.1f})")
                    result.external_blocked = True
```

- [ ] **Step 6: Update total_score calculation in score()**

Replace line 77:
```python
        result.total_score = result.core_score + result.bonus_score
```

With:
```python
        result.total_score = result.core_score + result.bonus_score + result.external_score
```

- [ ] **Step 7: Add external scoring call in score()**

After `_score_strengthen` call (line 73-74), add:

```python
        # Step 3.5: External risk factors
        self._score_external(result, stock_data.get("sector", ""))
```

- [ ] **Step 8: Verify scoring.py loads without errors**

```bash
& "C:\Users\72955\Desktop\tradingagent\TradingAgents\.venv\Scripts\python.exe" -c "
import sys; sys.path.insert(0, r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector')
import noproxy
from scoring import TristScorer, ScoreResult
print('TristScorer loaded OK')
print('ScoreResult fields:', [f for f in ScoreResult.__dataclass_fields__.keys()])
"
```

Expected: Prints TristScorer loaded OK and lists all fields including `external_score`.

---

### Task 6: Update screener.py — integrate external factors

**Files:**
- Modify: `TradingAgents/skills/trist_selector/screener.py`

**Interfaces:**
- Consumes: scoring.py v3 (Task 5), external_factors.py (Task 4)
- Produces: Updated output display with external score info

- [ ] **Step 1: Add sector name to indicators in screen_single()**

After line 308 (`indicators["sector"] = indicators.get("sector", "")`), ensure sector data is passed:

No change needed — sector is already passed via `indicators["sector"]`. But verify the sector field flows into the scorer.

- [ ] **Step 2: Update output display to show external score**

Replace the display block around line 420-430 that shows score details. Find and update the print statements to include external score:

```python
        if not r.vetoed:
            print(f"  Core: {r.core_details}")
            print(f"  Bonus: {r.bonus_details}")
            print(f"  External: {r.external_score}/10")
            if r.external_reasons:
                for reason in r.external_reasons:
                    print(f"    ⚠ {reason}")
```

- [ ] **Step 3: Update full-screen output to include external score**

In the `screen_full` function output, add external score to the top5 JSON.

---

### Task 7: End-to-end test with both stocks

**Files:**
- Create: (none — runs directly)

- [ ] **Step 1: Test with 603823 百合花**

```bash
cd "C:/Users/72955/Desktop/tradingagent/TradingAgents/skills/trist_selector" && ../../.venv/Scripts/python.exe screener.py 603823
```

Expected: Shows Core/Bonus/External scores, total out of 100, position recommendation.

- [ ] **Step 2: Test with 002384 东山精密**

```bash
cd "C:/Users/72955/Desktop/tradingagent/TradingAgents/skills/trist_selector" && ../../.venv/Scripts/python.exe screener.py 002384
```

Expected: Shows Core/Bonus/External scores with external deduction if semiconductor selloff persists.

- [ ] **Step 3: Verify total doesn't exceed 100**

```bash
& "C:\Users\72955\Desktop\tradingagent\TradingAgents\.venv\Scripts\python.exe" -c "
import sys; sys.path.insert(0, r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector')
import noproxy
from scoring import TristScorer

scorer = TristScorer()
max_core = sum(v['weight'] for v in scorer.rules['core'].values())
max_bonus = sum(v['weight'] for v in scorer.rules['strengthen'].values())
max_ext = scorer.rules['external']['max_score']
print(f'Max Core: {max_core} | Max Bonus: {max_bonus} | Max External: {max_ext}')
print(f'Max Total: {max_core + max_bonus + max_ext}')
assert max_core + max_bonus + max_ext == 100, 'Total must equal 100!'
print('PASS: Total = 100')
"
```

Expected: `PASS: Total = 100`

---

### Task 8: Update 交易规则手册.md to v3.0

**Files:**
- Modify: `TradingAgents/skills/trist_selector/交易规则手册.md`

- [ ] **Step 1: Update version header**

Change:
```
# Trist 交易规则手册 v2.3
> 最后更新：2026-07-15
> v2.3 新增：幽灵的礼物三原则（G1-G11）
```

To:
```
# Trist 交易规则手册 v3.0
> 最后更新：2026-07-17
> v3.0 新增：100分制评分重构 + 外围半导体风险因子（X15）
```

- [ ] **Step 2: Update 1.3 核心规则 table**

Replace the weight values in the core rules table to match v3.0:
- C1 趋势确认: 10分
- C2 非追高: 15分
- C3 量能活跃: 10分
- C4 主线题材: 5分
- C5 情绪周期: 15分
- C6 龙头地位: 5分

- [ ] **Step 3: Update 1.5 强化规则 table**

Replace the weight values in the strengthen rules table:
- B2 分歧转一致: 6分
- B6 弱转强: 6分
- B4 合理回调: 4分
- B7 低位首板: 3分
- B8 席位共振: 3分
- B1 龙头辨识: 2分
- B3 机构背书: 2分
- B5 盈利拐点: 2分
- B9 大资金容量: 2分

- [ ] **Step 4: Update 1.7 仓位决策**

Change:
```
总分 = C1+C2+C3+C4+C5+C6 + B1~B9（最高 240）
```
To:
```
总分 = 核心(C1~C6,60) + 强化(B1~B9,30) + 外围(0~10,惩罚项)（最高 100）
```

- [ ] **Step 5: Add new section "〇附、外围风险因子"**

Insert after the 游资选股总框架 section, describing:
- 追踪标的（NVDA/AMD/MU/SMH/SK Hynix/Tokyo Electron）
- 扣分机制
- 行业相关性系数
- X15 禁区触发条件
