# Trist Selector v4.2 — Scoring System Redesign

**Date**: 2026-08-04
**Status**: Approved, pending implementation
**Context**: v4.0 scoring system had 3 flaws: (1) external risk factors (10pts) irrelevant to A-share stock selection, (2) strengthen bonuses (20pts) only triggered 5/20pts in practice due to dead data sources and overly narrow conditions, (3) PA module weights didn't reflect Al Brooks priority hierarchy.

## Change Summary

| Component | v4.0/v4.1 | v4.2 | Delta |
|:---|:--:|:--:|:--:|
| PA Selection (PA1-PA13) | 70 | **90** | +20 |
| Strengthen (B2+B6 only) | 20 (B1-B9) | **10** (B2+B6) | -10 |
| External Risk | 10 | **0** (removed) | -10 |
| **Total** | **100** | **100** | 0 |

## Detailed Weight Changes

### Market Background (PA1-PA3): 13 → 22

| Item | Old | New | Rationale |
|:---|:--:|:--:|:---|
| PA1 Trend Strength | 5 | **8** | Trend is the #1 principle in Price Action. 5pts was too light to differentiate trend vs range. |
| PA2 Range Detection | 4 | **7** | A-shares spend ~80% of time in ranges. Identifying "when NOT to trade" is as important as knowing when to trade. |
| PA3 80% Rule | 4 | **7** | Al Brooks' signature rule — 80% of breakouts fail in ranges. Correct alignment should be rewarded significantly. |

### Signal Bar Quality (PA4-PA7): 25 → 30

| Item | Old | New | Rationale |
|:---|:--:|:--:|:---|
| PA4 Close Position | 8 | **9** | Close at extreme (top/bottom 1/3) is the strongest single signal of intent. |
| PA5 Body Strength | 7 | **9** | Body ratio + shadow direction together distinguish real breakouts from fake moves. Deserves equal weight to PA4. |
| PA6 Pullback Confirm | 5 | **6** | "No pullback, no entry" — requires ≥2 opposing bars before signal bar. Modest increase. |
| PA7 Special K-line | 5 | **6** | Pin Bar / Inside / Outside / Strong Trend bars are rare but high-quality when detected. |

### Entry Setup (PA8-PA10): 22 → 23

| Item | Old | New | Rationale |
|:---|:--:|:--:|:---|
| PA8 H/L Count | 10 | **10** | Already max weight. H2/L2 gold standard remains the anchor. |
| PA9 Wedge/Flag | 6 | **6** | Unchanged. Wedge detection depends on algorithm accuracy. |
| PA10 SR Confluence | 6 | **7** | Most objective entry metric — counting overlapped support/resistance levels. Directly usable as stop-loss/take-profit anchors. |

### Auxiliary (PA11-PA13): 10 → 15

| Item | Old | New | Rationale |
|:---|:--:|:--:|:---|
| PA11 Volume | 3 | **5** | Volume-price relationship is the 2nd most important technical dimension. 3pts severely undervalued it. |
| PA12 Sector | 3 | **4** | Modest increase. Sector API instability limits reliability as a scoring factor. |
| PA13 Emotion Cycle | 4 | **5** | "Buy at ice point, sell at euphoria" is youzi rule #1. Equal weight to volume. |

### Strengthen: 20 → 10 (B2 + B6 only)

| Item | Old | New | Rationale |
|:---|:--:|:--:|:---|
| B2 Divergence→Consensus | 4 | **5** | Kept — highest-value pattern: prior day heavy-volume decline + today light-volume rally. |
| B6 Weak→Strong | 4 | **5** | Kept — breakout reversal pattern. |
| B1/B3/B4/B5/B7/B8/B9 | 12 | **0 (removed)** | All removed. B1/B3/B5/B8 had dead data sources. B4/B7 were too easy to trigger (no differentiation). B9 threshold too high for small-caps. |

### External Risk: 10 → 0 (removed)

Entire `external` section removed from `rules.json`. The NVDA/SMH/AI-semiconductor tracking was designed for US tech exposure but irrelevant to most A-share stock selection decisions. 

### Position Thresholds

| Line | Score | Position |
|:---|:--:|:---|
| Full | ≥80 | 100% |
| Half | ≥60 | 50% |
| Observe | <60 | 0% |

Thresholds **unchanged**. The scoring redistribution alone is sufficient — more points allocated to sections with higher utilization rates will naturally produce better score differentiation.

## Implementation Scope

### Files to modify

1. **`rules.json`** — Update all PA weights, reduce strengthen to B2+B6 only, remove external section, update `_comment`
2. **`scoring.py`** — Remove `_score_external()` call from `score()`, simplify `_score_strengthen()` to B2+B6 only, set `external_score` to 0, remove external-related imports and fields
3. **`ScoreResult` dataclass** — Keep `external_score` field (default 0 for backward compat) but remove `external_reasons`, `external_details`, `external_blocked`

### Files NOT modified

- `screener.py` — No changes. Indicator computation unchanged.
- `gate.py` — No changes. Entry gates are independent of scoring.
- `rules.json` forbidden/position/exit/discipline sections — No changes.
- All `bypass_*.py` scripts — Will work as-is after re-scoring.

### Backward compatibility

- Total remains 100 points
- Position thresholds unchanged (80/60)
- Forbidden checks unchanged
- Gate system unchanged
- All PA function signatures unchanged (only weight values change)
