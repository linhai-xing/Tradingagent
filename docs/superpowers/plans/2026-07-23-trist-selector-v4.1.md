# Trist Selector v4.1 Implementation Plan

> **For agentic workers:** Execute tasks sequentially. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 v4.0 90分制 PA 评分系统升级到 v4.1 100分制，新增独立执行门禁（gate.py），评分只管选股，门禁管执行。

**Architecture:** rules.json 权重调整（信号K线 25 + 入场结构 22），新增 gate.py（Gate-A/B/C 三关），scoring.py 名称调整+gate_results 字段，screener.py 展示门禁状态。

**Tech Stack:** Python 3.13, pandas

## Global Constraints

- 评分总分 100 = PA(70) + 强化(20) + 外围(10)
- PA 信号K线（PA4-PA7）合计 25 分
- PA 入场结构（PA8-PA10）合计 22 分
- PA3 逆势惩罚 -4 分（顺势 +4）
- 仓位阈值：≥80 满仓，60-79 半仓，<60 观察
- 执行门禁不占分，三关全部通过才下单
- Gate-C 强制下午 14:00 后执行

---

### Task 1: Update rules.json to v4.1 weights

**Files:**
- Modify: `TradingAgents/skills/trist_selector/rules.json`

**Interfaces:**
- Produces: New PA weights consumed by scoring.py Task 3

Replace the `price_action` section. The new weights:

```json
"price_action": {
    "_comment": "Trist Selector v4.1 — 100分制选股过滤器。PA1-PA13盘后评分70分，Gate独立执行。",
    "_section1": "一级：市场背景 — 13 分",
    "PA1_trend_strength": {
      "weight": 5,
      "description": "趋势强度：EMA排列 + 均线缺口(≥20根K线不碰MA20) + 趋势K线占比",
      "ma_bull_alignment": ["MA5>MA20>MA60"],
      "ma_gap_bars_min": 20,
      "trend_bar_ratio_min": 0.5
    },
    "PA2_range_detection": {
      "weight": 4,
      "description": "交易区间识别：K线重叠度+区间振幅",
      "overlap_ratio_high": 0.70,
      "overlap_ratio_medium": 0.50,
      "range_amplitude_max": 0.08,
      "breakout_fail_ratio": 0.80
    },
    "PA3_80pct_alignment": {
      "weight": 4,
      "description": "80%惯性法则：顺势操作+4分，逆势操作-4分",
      "align_bonus": 4,
      "counter_penalty": -4
    },

    "_section2": "二级：信号K线质量 — 25 分",
    "PA4_close_position": {
      "weight": 8,
      "description": "收盘位置：收盘在K线顶部/底部1/3以内"
    },
    "PA5_body_strength": {
      "weight": 7,
      "description": "实体强度：实体占比+影线方向"
    },
    "PA6_pullback_confirm": {
      "weight": 5,
      "description": "回调确认：信号K线前≥2根反向K线"
    },
    "PA7_special_bar": {
      "weight": 5,
      "description": "特殊K线：Pin Bar/内包线/外包线/强趋势K线"
    },

    "_section3": "三级：入场结构 — 22 分",
    "PA8_h_l_count": {
      "weight": 10,
      "description": "H1/H2/L1/L2计数：H2/L2黄金标准=满分，H1/L1陷阱=半分"
    },
    "PA9_wedge_flag": {
      "weight": 6,
      "description": "楔形/旗形：三推+嵌套+抛物线楔形"
    },
    "PA10_sr_confluence": {
      "weight": 6,
      "description": "SR共振：均线+前高/低多重重合"
    },

    "_section4": "四级：辅助确认 — 10 分",
    "PA11_volume": {
      "weight": 3,
      "description": "量能确认"
    },
    "PA12_sector": {
      "weight": 3,
      "description": "主线/板块"
    },
    "PA13_emotion": {
      "weight": 4,
      "description": "情绪周期：冰点/分歧满分，一致半分"
    }
}
```

Update the `position` thresholds:
```json
"position": {
    "full_score": 80, "half_score": 60,
    "max_single_pct": 0.25,
    "full_buy_pct": 1.0, "half_buy_pct": 0.5
}
```

Update the `_comment` at top:
```json
"_comment": "Trist Selector v4.1 — 100分制选股过滤器 (PA70+强化20+外围10)。Gate门禁独立于评分。"
```

Keep `strengthen`, `forbidden`, `external`, `discipline`, `screener` sections unchanged.

- [ ] **Step 1: Verify JSON validity**
```bash
& "C:\Users\72955\Desktop\tradingagent\TradingAgents\.venv\Scripts\python.exe" -c "import json; f=open(r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector\rules.json','r',encoding='utf-8'); d=json.load(f); f.close(); pa=d['price_action']; total=sum(v['weight'] for k,v in pa.items() if k.startswith('PA')); print('PA total:', total); assert total==70; print('OK')"
```
Expected: `PA total: 70` and `OK`

---

### Task 2: Create gate.py — 执行门禁

**Files:**
- Create: `TradingAgents/skills/trist_selector/gate.py`

**Interfaces:**
- Produces: `GateResult`, `check_gate_a()`, `check_gate_b()`, `check_gate_c()`
- Consumed by: screener.py Task 4

```python
"""Trist Selector v4.1 — Execution Gate (执行门禁).
Three hard gates, independent of scoring. All must pass before any order.
Gate-A: Entry method (signal bar != entry bar)
Gate-B: Post-entry confirmation
Gate-C: Time window (afternoon only, per user's 75% win rate data)
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class GateResult:
    gate_name: str
    passed: bool
    reason: str
    detail: str = ""


def check_gate_a(entry_method: str, signal_bar_date: str = "") -> GateResult:
    """
    Gate-A: Entry method must be 'limit_order' (break of signal bar high/low +1 tick).
    Auction buy ('auction') and market chase ('chase') are rejected.
    
    Args:
        entry_method: 'limit_order' | 'auction' | 'chase' | 'market'
        signal_bar_date: date of the signal bar (for display)
    """
    if entry_method == "limit_order":
        return GateResult("Gate-A", True, "突破挂单入场", f"信号K线{signal_bar_date}已确认，挂突破单")
    elif entry_method == "auction":
        return GateResult("Gate-A", False, "竞价买入", "信号K线≠入场K线，竞价买入=同一根K线既是信号又是入场")
    elif entry_method == "chase":
        return GateResult("Gate-A", False, "盘中追入", "价格已远离信号K线高低点，盈亏比恶化")
    else:
        return GateResult("Gate-A", False, "入场方式不明", "未指定入场方式")


def check_gate_b(entry_kline_close: float, entry_price: float, signal_direction: str = "long") -> GateResult:
    """
    Gate-B: Entry bar must close in the direction of the trade.
    If entry bar closes against the trade, reduce or exit.
    
    Args:
        entry_kline_close: closing price of the entry bar (the bar after signal bar)
        entry_price: your fill price
        signal_direction: 'long' or 'short'
    """
    if entry_kline_close <= 0:
        return GateResult("Gate-B", True, "入场K线未收盘", "盘中检查，收盘后再确认")

    if signal_direction == "long":
        if entry_kline_close >= entry_price:
            return GateResult("Gate-B", True, "入场K线收阳确认", f"收{entry_kline_close:.2f}≥入场{entry_price:.2f}，持仓")
        else:
            return GateResult("Gate-B", False, "入场K线反向", f"收{entry_kline_close:.2f}<入场{entry_price:.2f}，次日减仓或清仓")
    else:  # short
        if entry_kline_close <= entry_price:
            return GateResult("Gate-B", True, "入场K线收阴确认", f"收{entry_kline_close:.2f}≤入场{entry_price:.2f}，持仓")
        else:
            return GateResult("Gate-B", False, "入场K线反向", f"收{entry_kline_close:.2f}>入场{entry_price:.2f}，次日减仓或清仓")


def check_gate_c(entry_time: str = "") -> GateResult:
    """
    Gate-C: Entry must be after 14:00 (user's 75% afternoon win rate).
    Morning entries (before 11:30) are rejected.
    
    Args:
        entry_time: 'HH:MM' format, or datetime string with time
    """
    if not entry_time:
        now = datetime.now()
        hour = now.hour
        minute = now.minute
    else:
        try:
            # Handle various formats: '14:30', '2026-07-23 14:30:00', '14'
            time_str = entry_time
            if ' ' in time_str:
                time_str = time_str.split(' ')[1]
            parts = time_str.split(':')
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        except (ValueError, IndexError):
            return GateResult("Gate-C", True, "时间解析失败，默认通过", "")

    if hour >= 14:
        return GateResult("Gate-C", True, "下午入场", f"{hour:02d}:{minute:02d} 下午执行（胜率75%）")
    elif hour >= 11:
        return GateResult("Gate-C", False, "午间/早盘尾段", f"{hour:02d}:{minute:02d} 上午买入胜率仅27%，等下午")
    else:
        return GateResult("Gate-C", False, "早盘买入", f"{hour:02d}:{minute:02d} 上午买入胜率仅27%，等下午")


def check_all_gates(entry_method: str, entry_price: float = 0,
                    entry_kline_close: float = 0, entry_time: str = "",
                    signal_bar_date: str = "", signal_direction: str = "long") -> dict:
    """
    Run all three gates. Returns dict with individual results and overall pass/fail.
    """
    results = {
        "gate_a": check_gate_a(entry_method, signal_bar_date),
        "gate_b": check_gate_b(entry_kline_close, entry_price, signal_direction),
        "gate_c": check_gate_c(entry_time),
    }
    all_pass = all(r.passed for r in results.values())
    return {
        "gates": results,
        "all_pass": all_pass,
        "blocked": not all_pass,
    }
```

- [ ] **Step 1: Verify gate.py loads**
```bash
& "C:\Users\72955\Desktop\tradingagent\TradingAgents\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0, r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector'); from gate import check_all_gates; r=check_all_gates('auction',signal_bar_date='2026-07-22'); print('Blocked:', r['blocked']); print('Gate-A:', r['gates']['gate_a'].reason)"
```
Expected: `Blocked: True` and Gate-A reason mentions auction.

---

### Task 3: Update scoring.py — ScoreResult gate field

**Files:**
- Modify: `TradingAgents/skills/trist_selector/scoring.py`

**Interfaces:**
- Consumes: rules.json v4.1 weights (Task 1)
- Produces: ScoreResult with gate_results field
- Consumed by: screener.py Task 4

- [ ] **Step 1: Add gate_results to ScoreResult dataclass**

After `discipline_hits: List[str] = field(default_factory=list)`, add:
```python
    gate_results: dict = field(default_factory=dict)  # v4.1 gate check results
    gate_blocked: bool = False  # v4.1 True if any gate failed
```

- [ ] **Step 2: Update version header comment**

Change line 1 from:
```python
"""Trist Selector v4.0 — Price Action Scoring Engine (阿布价格行为学 90分制)."""
```
To:
```python
"""Trist Selector v4.1 — Price Action Scoring Engine (阿布价格行为学 70分制 PA + 20强化 + 10外围 = 100)."""
```

- [ ] **Step 3: Verify**

```bash
& "C:\Users\72955\Desktop\tradingagent\TradingAgents\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0, r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector'); import noproxy; from scoring import ScoreResult; f=list(ScoreResult.__dataclass_fields__.keys()); assert 'gate_results' in f; assert 'gate_blocked' in f; print('OK - gate fields present')"
```
Expected: `OK - gate fields present`

---

### Task 4: Update screener.py — display gate status

**Files:**
- Modify: `TradingAgents/skills/trist_selector/screener.py`

**Interfaces:**
- Consumes: gate.py Task 2, scoring.py Task 3

- [ ] **Step 1: Add gate import**

At top of screener.py, after `from scoring import TristScorer, ScoreResult, build_market_context`, add:
```python
from gate import check_all_gates
```

- [ ] **Step 2: Add gate check section in single-stock output**

Find the single-stock output block (after `print(f"  External: {result.external_score}/10")` and before printing entry signals). Add:

```python
    # Gate check (v4.1)
    print(f"  Gate门禁:")
    entry_method = "limit_order"  # default for display; real check by user
    gates = check_all_gates(entry_method)
    for gate_key, gate_result in gates["gates"].items():
        if isinstance(gate_result, dict):
            status = "PASS" if gate_result.get("passed") else "FAIL"
            print(f"    {gate_key}: {status}")
    if gates.get("blocked"):
        print(f"    ! 门禁未通过，请用挂单方式 + 下午执行")
```

Wait — the output won't show the actual user's entry method since the screener doesn't know it. Better approach: show the gate requirements as a checklist reminder:

```python
    # Gate reminder (v4.1)
    print(f"  Gate门禁 (下单前必查):")
    print(f"    Gate-A: 挂突破单入场 (禁止竞价/追入)")
    print(f"    Gate-B: 入场K线收盘确认方向")
    print(f"    Gate-C: 下午14:00后执行 (上午胜率27%)")
```

- [ ] **Step 3: Verify syntax**

```bash
& "C:\Users\72955\Desktop\tradingagent\TradingAgents\.venv\Scripts\python.exe" -c "import ast; ast.parse(open(r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector\screener.py', encoding='utf-8').read()); print('syntax OK')"
```
Expected: `syntax OK`

---

### Task 5: End-to-end verification

- [ ] **Step 1: Run screener on 603823**

```bash
cd "C:/Users/72955/Desktop/tradingagent/TradingAgents/skills/trist_selector" && ../../.venv/Scripts/python.exe screener.py 603823
```

Expected: Shows Score, Core/Bonus/External, Gate门禁 checklist. No import errors.

- [ ] **Step 2: Verify PA total = 70**

```bash
& "C:\Users\72955\Desktop\tradingagent\TradingAgents\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0, r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector'); import noproxy; from scoring import TristScorer; s=TristScorer(); pa=s.rules['price_action']; t=sum(v['weight'] for k,v in pa.items() if k.startswith('PA')); b=sum(v['weight'] for v in s.rules['strengthen'].values()); e=s.rules['external']['max_score']; print(f'PA:{t} + B:{b} + Ext:{e} = {t+b+e}'); assert t+b+e==100; print('Total=100 PASS')"
```
Expected: `PA:70 + B:20 + Ext:10 = 100` and `Total=100 PASS`

- [ ] **Step 3: Verify gate module**

```bash
& "C:\Users\72955\Desktop\tradingagent\TradingAgents\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0, r'C:\Users\72955\Desktop\tradingagent\TradingAgents\skills\trist_selector'); from gate import check_all_gates; r1=check_all_gates('auction'); r2=check_all_gates('limit_order'); r3=check_all_gates('chase','','','09:30'); print('Auction blocked:', r1['blocked']); print('Limit OK:', r2['all_pass']); print('Chase blocked:', r3['blocked']); assert r1['blocked'] and r2['all_pass'] and r3['blocked']; print('Gate logic PASS')"
```
Expected: All assertions pass.
