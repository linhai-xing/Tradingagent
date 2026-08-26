"""Trist Selector v4.2 — Price Action Scoring Engine (PA90+强化10=100). Gate门禁独立于评分."""
import noproxy  # MUST be first

import json, os
from typing import Dict, List, Optional
from dataclasses import dataclass, field

import pandas as pd

RULES_PATH = os.path.join(os.path.dirname(__file__), "rules.json")
with open(RULES_PATH, encoding="utf-8") as f:
    RULES = json.load(f)


@dataclass
class ScoreResult:
    ticker: str
    name: str = ""
    total_score: int = 0
    pa_score: int = 0          # PA1-PA13 subtotal (max 70)
    bonus_score: int = 0
    pa_details: Dict[str, int] = field(default_factory=dict)     # {PA_code: score_awarded}
    pa_reasons: Dict[str, str] = field(default_factory=dict)     # {PA_code: reason}
    bonus_details: Dict[str, bool] = field(default_factory=dict)
    forbidden_hits: List[str] = field(default_factory=list)
    vetoed: bool = False
    position: str = "observe"
    position_pct: float = 0.0
    entry_signals: List[str] = field(default_factory=list)
    entry_recommendation: str = ""
    # Price Action specific outputs
    market_state: str = ""           # "trend_bull" | "trend_bear" | "trading_range" | "unknown"
    signal_bar_quality: str = ""     # "excellent" | "good" | "fair" | "poor"
    signal_bar_type: str = ""        # "strong_trend" | "pin_bar" | "inside" | "outside" | "standard"
    signal_bar_high: float = 0.0     # signal bar high (for buy stop placement)
    signal_bar_low: float = 0.0      # signal bar low (for sell stop / stop loss)
    h_count: int = 0                 # H1/H2/H3 count detected
    l_count: int = 0                 # L1/L2/L3 count detected
    wedge_type: str = ""             # "bull_wedge" | "bear_wedge" | "parabolic" | "none"
    sr_confluence: int = 0           # number of S/R levels near price
    entry_gate_a: bool = False       # GATE-A: entry bar triggered?
    entry_gate_b: bool = False       # GATE-B: entry bar confirmed direction?
    price: float = 0.0
    sector: str = ""
    sector_rank: int = 0
    emotion_phase: str = ""
    leader_level: str = ""
    discipline_blocked: bool = False
    discipline_hits: List[str] = field(default_factory=list)
    gate_results: dict = field(default_factory=dict)  # v4.1: gate check results
    gate_blocked: bool = False  # v4.1: True if any gate failed
    external_score: int = 0


class TristScorer:
    """v4.2: Price Action scoring engine integrating Al Brooks methodology. PA90+Strengthen10=100."""

    def __init__(self, market_context: Optional[dict] = None):
        self.rules = RULES
        self.ctx = market_context or {}

    def score(self, stock_data: dict, sector_data: Optional[dict] = None,
              discipline_state: Optional[dict] = None) -> ScoreResult:
        result = ScoreResult(
            ticker=stock_data.get("ticker", ""),
            name=stock_data.get("name", ""),
            price=stock_data.get("price", 0),
        )

        # Step 0: Discipline rules
        if discipline_state:
            self._check_discipline(result, discipline_state)

        # Step 1: Forbidden checks (veto)
        self._check_forbidden(result, stock_data, sector_data or {})
        if result.vetoed:
            return result

        # Step 2: Price Action scoring (PA1-PA13, 90 pts max)
        self._score_price_action(result, stock_data, sector_data or {})

        # Step 3: Strengthen rules (B2+B6, 0-10 pts)
        self._score_strengthen(result, stock_data, sector_data or {})

        # Step 4: Position decision (external risk removed in v4.2)
        result.total_score = result.pa_score + result.bonus_score
        if result.total_score >= self.rules["position"]["full_score"]:
            result.position = "full"
            result.position_pct = self.rules["position"]["full_buy_pct"]
        elif result.total_score >= self.rules["position"]["half_score"]:
            result.position = "half"
            result.position_pct = self.rules["position"]["half_buy_pct"]
        else:
            result.position = "observe"
            result.position_pct = 0.0

        return result

    # ═══════════════════════════════════════════════════════════
    # Discipline
    # ═══════════════════════════════════════════════════════════

    def _check_discipline(self, result: ScoreResult, discipline_state: dict):
        D = self.rules.get("discipline", {})
        hits = []

        if discipline_state.get("stop_loss_today", False):
            hits.append("X13:今日已触发止损，当天禁止新开仓位")

        loss = discipline_state.get("last_trade_loss_pct", 0)
        cooldown = discipline_state.get("cooldown_until_date", "")
        today = discipline_state.get("today_date", "")
        if loss <= D.get("X14_big_loss_cooldown", {}).get("loss_threshold", -0.05) and cooldown and today:
            if today < cooldown:
                days_left = (pd.to_datetime(cooldown) - pd.to_datetime(today)).days
                hits.append(f"X14:上一笔亏损{loss:.1%}>5%，强制冷却{days_left}天（{cooldown}前不可交易）")
        elif loss <= D.get("X14_big_loss_cooldown", {}).get("loss_threshold", -0.05):
            hits.append(f"X14:上一笔亏损{loss:.1%}>5%，强制停止交易2天")

        if hits:
            result.discipline_hits = hits
            result.discipline_blocked = True

    # ═══════════════════════════════════════════════════════════
    # Forbidden
    # ═══════════════════════════════════════════════════════════

    def _check_forbidden(self, result: ScoreResult, data: dict, sector: dict):
        F = self.rules["forbidden"]
        hits = []

        pre5d = data.get("pre_5d_return", 0)
        if pre5d > F["X1_chase_high"]["max_pre5d_return"]:
            hits.append(f"X1:近5日涨{pre5d:.1%}>{F['X1_chase_high']['max_pre5d_return']:.0%}")

        turnover = data.get("avg_turnover_5d", 0)
        if turnover < F["X2_liquidity"]["min_daily_turnover"]:
            hits.append(f"X2:换手{turnover:.2%}<{F['X2_liquidity']['min_daily_turnover']:.1%}")

        amp3 = data.get("avg_amplitude_3d", 1.0)
        if amp3 < F["X3_manipulation"]["max_amplitude_3d"]:
            hits.append(f"X3:3日振幅{amp3:.1%}<{F['X3_manipulation']['max_amplitude_3d']:.1%}")

        if data.get("has_bad_news_3d", False):
            hits.append("X4:近3日有利空公告")

        if data.get("prev_day_limit_up", False):
            hits.append("X7:前日涨停，今日追高风险极高")

        ma5 = data.get("ma5", 0)
        ma10 = data.get("ma10", 0)
        if ma5 > 0 and ma10 > 0 and ma5 < ma10:
            hits.append(f"X9:MA5({ma5:.2f})<MA10({ma10:.2f})死叉")

        # X10: Lhasa seats
        lhb_seats = self.ctx.get("lhb_data", {}).get(result.ticker, {}).get("seats", [])
        lasa_kw = F["X10_lasa_seats"]["lasa_keyword"]
        lasa_count = sum(1 for s in lhb_seats if lasa_kw in str(s))
        if lasa_count >= 2:
            hits.append(f"X10:拉萨{lasa_count}席位上榜(散户接盘信号)")

        # X11: Foshan seats
        foshan_kws = F["X11_foshan_seats"]["foshan_keywords"]
        if any(any(kw in str(s) for kw in foshan_kws) for s in lhb_seats):
            hits.append("X11:佛山系上榜(一日游砸盘风险)")

        # X12: Euphoria
        lu_count = self.ctx.get("limit_up_count", 0)
        if lu_count > F["X12_euphoria"]["max_limit_up_count"]:
            hits.append(f"X12:涨停{lu_count}家>80家(高潮期)")

        # X6: Market crash
        bench = self.ctx.get("benchmark", {})
        bench5d = bench.get("ret_5d", 0)
        bench_dead = bench.get("ma5_dead_cross_ma20", False)
        if bench5d < -F["X6_market_crash"]["max_index_drop_5d"] and bench_dead:
            hits.append(f"X6:上证5日跌{bench5d:.1%}且死叉")

        # X17: 跳空日禁入 — 开盘跳空>5%当日不交易
        gap_pct = data.get("open_gap_pct", 0)
        x17_cfg = F.get("X17_gap_entry", {})
        if x17_cfg and abs(gap_pct) > x17_cfg.get("max_gap_pct", 0.05):
            direction = "高开" if gap_pct > 0 else "低开"
            hits.append(f"X17:跳空{direction}{abs(gap_pct):.1%}>{x17_cfg['max_gap_pct']:.0%}(跳空日波动放大,禁入)")

        if hits:
            result.forbidden_hits = hits
            result.vetoed = True

    # ═══════════════════════════════════════════════════════════
    # Price Action Scoring (PA1-PA13, 90 pts)
    # ═══════════════════════════════════════════════════════════

    def _score_price_action(self, result: ScoreResult, data: dict, sector: dict):
        PA = self.rules["price_action"]
        score = 0
        details = {}
        reasons = {}

        # ── Section 1: Market Background (PA1-PA3, 13 pts) ──

        # PA1: Trend Strength (8 pts)
        pa1_score, pa1_reason = self._score_pa1_trend(data, PA)
        score += pa1_score
        details["PA1_trend"] = pa1_score
        reasons["PA1_trend"] = pa1_reason

        # PA2: Trading Range Detection (6 pts)
        pa2_score, pa2_reason = self._score_pa2_range(data, PA)
        score += pa2_score
        details["PA2_range"] = pa2_score
        reasons["PA2_range"] = pa2_reason

        # PA3: 80% Rule Alignment (6 pts, bidirectional)
        pa3_score, pa3_reason, market_state = self._score_pa3_80pct(data, PA)
        score += pa3_score
        details["PA3_80pct"] = pa3_score
        reasons["PA3_80pct"] = pa3_reason
        result.market_state = market_state

        # ── Section 2: Signal Bar Quality (PA4-PA7, 25 pts) ──

        pa4_score, pa4_reason = self._score_pa4_close_position(data, PA)
        score += pa4_score
        details["PA4_close_pos"] = pa4_score
        reasons["PA4_close_pos"] = pa4_reason

        pa5_score, pa5_reason = self._score_pa5_body(data, PA)
        score += pa5_score
        details["PA5_body"] = pa5_score
        reasons["PA5_body"] = pa5_reason

        pa6_score, pa6_reason = self._score_pa6_pullback(data, PA)
        score += pa6_score
        details["PA6_pullback"] = pa6_score
        reasons["PA6_pullback"] = pa6_reason

        pa7_score, pa7_reason, bar_type = self._score_pa7_special_kline(data, PA)
        score += pa7_score
        details["PA7_special_k"] = pa7_score
        reasons["PA7_special_k"] = pa7_reason
        result.signal_bar_type = bar_type

        # Aggregate signal bar quality
        sig_quality = details["PA4_close_pos"] + details["PA5_body"] + details["PA6_pullback"] + details["PA7_special_k"]
        pa4_max = PA["PA4_close_position"]["weight"]
        pa5_max = PA["PA5_body_strength"]["weight"]
        pa6_max = PA["PA6_pullback_confirm"]["weight"]
        pa7_max = PA["PA7_special_kline"]["weight"]
        sig_max = pa4_max + pa5_max + pa6_max + pa7_max
        sig_pct = sig_quality / sig_max if sig_max > 0 else 0
        if sig_pct >= 0.75:
            result.signal_bar_quality = "excellent"
        elif sig_pct >= 0.55:
            result.signal_bar_quality = "good"
        elif sig_pct >= 0.35:
            result.signal_bar_quality = "fair"
        else:
            result.signal_bar_quality = "poor"

        # Signal bar levels for entry stop placement
        result.signal_bar_high = data.get("signal_bar_high", data.get("price", 0))
        result.signal_bar_low = data.get("signal_bar_low", data.get("price", 0))

        # ── Section 3: Entry Setup (PA8-PA10, 22 pts) ──

        pa8_score, pa8_reason, hc, lc = self._score_pa8_h_count(data, PA, market_state)
        score += pa8_score
        details["PA8_h_count"] = pa8_score
        reasons["PA8_h_count"] = pa8_reason
        result.h_count = hc
        result.l_count = lc

        pa9_score, pa9_reason, wtype = self._score_pa9_wedge(data, PA, market_state)
        score += pa9_score
        details["PA9_wedge"] = pa9_score
        reasons["PA9_wedge"] = pa9_reason
        result.wedge_type = wtype

        pa10_score, pa10_reason, sr_count = self._score_pa10_sr(data, PA)
        score += pa10_score
        details["PA10_sr"] = pa10_score
        reasons["PA10_sr"] = pa10_reason
        result.sr_confluence = sr_count

        # ── Section 4: Auxiliary (PA11-PA13, 10 pts) ──

        pa11_score, pa11_reason = self._score_pa11_volume(data, PA)
        score += pa11_score
        details["PA11_volume"] = pa11_score
        reasons["PA11_volume"] = pa11_reason

        pa12_score, pa12_reason = self._score_pa12_sector(data, sector, PA)
        score += pa12_score
        details["PA12_sector"] = pa12_score
        reasons["PA12_sector"] = pa12_reason
        result.sector = sector.get("name", "")
        result.sector_rank = sector.get("rank", 0)

        pa13_score, pa13_reason, emotion_phase = self._score_pa13_emotion(PA)
        score += pa13_score
        details["PA13_emotion"] = pa13_score
        reasons["PA13_emotion"] = pa13_reason
        result.emotion_phase = emotion_phase

        result.pa_score = max(0, score)  # floor at 0 (PA3 penalty could make it negative)
        result.pa_details = details
        result.pa_reasons = reasons

    # ── PA1: Trend Strength (5 pts) ───────────────────────────

    def _score_pa1_trend(self, data: dict, PA: dict) -> tuple:
        cfg = PA["PA1_trend_strength"]
        ma5 = data.get("ma5", 0)
        ma20 = data.get("ma20", 0)
        ma60 = data.get("ma60", 0)
        price = data.get("price", 0)
        gap_bars = data.get("ma_gap_bars", 0)
        trend_bar_ratio = data.get("trend_bar_ratio", 0)

        score = 0
        reasons = []

        # Bull alignment: MA5 > MA20 > MA60 and price above MA5
        bull_aligned = ma5 > ma20 > ma60 > 0 and price > ma5
        bear_aligned = 0 < ma5 < ma20 < ma60 and price < ma5

        if bull_aligned or bear_aligned:
            score += 3
            reasons.append("均线多头/空头排列(+3)")
        elif ma5 > ma20 > 0 and price > ma5:  # partial bull
            score += 1
            reasons.append("短期均线偏多(+1)")
        elif 0 < ma5 < ma20 and price < ma5:  # partial bear
            score += 1
            reasons.append("短期均线偏空(+1)")

        # MA gap: 20+ bars without touching MA20 = strong trend
        gap_min = cfg.get("ma_gap_bars_min", 20)
        if gap_bars >= gap_min:
            score += 2
            reasons.append(f"均线缺口{gap_bars}根K线未碰MA20→强趋势(+2)")
        elif gap_bars >= gap_min * 0.5:
            score += 1
            reasons.append(f"均线缺口{gap_bars}根K线(+1)")

        # Trend bar ratio
        if trend_bar_ratio >= 0.6:
            score += 1
            reasons.append(f"趋势K线占比{trend_bar_ratio:.0%}(+1)")

        return min(score, cfg["weight"]), "; ".join(reasons) if reasons else "无趋势特征"

    # ── PA2: Trading Range Detection (4 pts) ──────────────────

    def _score_pa2_range(self, data: dict, PA: dict) -> tuple:
        cfg = PA["PA2_range_detection"]
        overlap = data.get("bar_overlap_ratio", 0)
        amp_20d = data.get("range_amplitude_20d", 0.99)

        score = 0
        reasons = []

        # High overlap = trading range
        if overlap >= cfg.get("overlap_ratio_high", 0.70):
            if amp_20d <= cfg.get("range_amplitude_max", 0.08):
                score = cfg["weight"]
                reasons.append(f"明确交易区间(K线重叠{overlap:.0%},振幅{amp_20d:.1%})(+{cfg['weight']})")
            else:
                score = cfg["weight"] - 2
                reasons.append(f"宽幅震荡(K线重叠{overlap:.0%},振幅偏大{amp_20d:.1%})(+{score})")
        elif overlap >= cfg.get("overlap_ratio_medium", 0.50):
            score = cfg["weight"] - 3
            reasons.append(f"部分重叠(过渡阶段,重叠{overlap:.0%})(+{score})")
        else:
            reasons.append(f"低重叠→趋势特征明显(重叠{overlap:.0%})(+0)")

        return score, "; ".join(reasons) if reasons else "趋势主导，非交易区间"

    # ── PA3: 80% Rule (4 pts, bidirectional) ──────────────────

    def _score_pa3_80pct(self, data: dict, PA: dict) -> tuple:
        cfg = PA["PA3_80pct_alignment"]
        overlap = data.get("bar_overlap_ratio", 0)
        is_bullish = data.get("is_bullish_bar", True)
        ma5 = data.get("ma5", 0)
        ma20 = data.get("ma20", 0)
        price = data.get("price", 0)

        # Determine market state
        if overlap >= 0.60:
            market_state = "trading_range"
        elif price > ma20 > 0 and ma5 > ma20:
            market_state = "trend_bull"
        elif 0 < price < ma20 and ma5 < ma20:
            market_state = "trend_bear"
        else:
            market_state = "unknown"

        # PA3: check alignment with 80% rule
        if market_state == "trend_bull" and is_bullish:
            # In bull trend, buying is correct (80% trend continuation)
            score = cfg["align_bonus"]
            reason = f"牛趋势+做多信号→顺应80%法则(+{score})"
        elif market_state == "trend_bear" and not is_bullish:
            score = cfg["align_bonus"]
            reason = f"熊趋势+做空信号→顺应80%法则(+{score})"
        elif market_state == "trading_range":
            # Check if near boundary (simplified: use distance from 20d high/low)
            dist_from_20h = data.get("dist_from_20d_high", 0.5)
            if dist_from_20h >= 0.85 and not is_bullish:  # near top, looking to sell
                score = cfg["align_bonus"]
                reason = f"区间顶部+做空信号→顺应80%法则(假突破概率高)(+{score})"
            elif dist_from_20h <= 0.15 and is_bullish:  # near bottom, looking to buy
                score = cfg["align_bonus"]
                reason = f"区间底部+做多信号→顺应80%法则(假突破概率高)(+{score})"
            elif 0.3 <= dist_from_20h <= 0.7:
                score = 0
                reason = "区间中部→方向不明确(+0)"
            else:
                # Near boundary but trading WITH breakout (wrong)
                score = 0
                reason = "区间边界追突破→对抗80%法则(+0)"
        elif market_state == "trend_bull" and not is_bullish:
            # Bearish signal in bull trend = against 80%
            score = 0
            reason = "牛趋势中做空信号→对抗80%法则(+0)"
        elif market_state == "trend_bear" and is_bullish:
            score = 0
            reason = "熊趋势中做多信号→对抗80%法则(+0)"
        else:
            score = 0
            reason = "市场状态不明确(+0)"

        return score, reason, market_state

    # ── PA4: Close Position (8 pts) ──────────────────────────

    def _score_pa4_close_position(self, data: dict, PA: dict) -> tuple:
        cfg = PA["PA4_close_position"]
        close_pos = data.get("signal_close_position", 0.5)

        extreme = cfg["extreme_threshold"]
        good = cfg["good_threshold"]

        if close_pos >= extreme or close_pos <= (1 - extreme):
            score = cfg["weight"]
            reason = f"收盘在极端位置({close_pos:.0%})→信号K线质量极佳(+{score})"
        elif close_pos >= good or close_pos <= (1 - good):
            score = int(cfg["weight"] * 0.7)
            reason = f"收盘偏极端({close_pos:.0%})(+{score})"
        elif close_pos >= cfg["fair_threshold"] or close_pos <= (1 - cfg["fair_threshold"]):
            score = int(cfg["weight"] * 0.4)
            reason = f"收盘位置一般({close_pos:.0%})(+{score})"
        else:
            score = 0
            reason = f"收盘在K线中部({close_pos:.0%})→信号模糊(+0)"

        return score, reason

    # ── PA5: Body Strength (7 pts) ────────────────────────────

    def _score_pa5_body(self, data: dict, PA: dict) -> tuple:
        cfg = PA["PA5_body_strength"]
        body_ratio = data.get("signal_body_ratio", 0)
        upper_shadow = data.get("signal_upper_shadow_ratio", 0)
        lower_shadow = data.get("signal_lower_shadow_ratio", 0)
        is_bullish = data.get("is_bullish_bar", True)

        score = 0
        reasons = []

        # Body ratio scoring
        if body_ratio >= cfg["strong_body_ratio"]:
            score += 3
            reasons.append(f"实体饱满({body_ratio:.0%})(+3)")
        elif body_ratio >= cfg["good_body_ratio"]:
            score += 1
            reasons.append(f"实体适中({body_ratio:.0%})(+1)")

        # Shadow analysis: for bullish bar, want small upper shadow, some lower shadow ok
        shadow_favor = cfg["shadow_favor_max"]
        if is_bullish:
            if upper_shadow <= shadow_favor:
                score += 2
                reasons.append(f"上影线小({upper_shadow:.0%})→多头无阻力(+2)")
            if 0.10 <= lower_shadow <= 0.35:
                score += 2
                reasons.append(f"下影线适中({lower_shadow:.0%})→多头有支撑(+2)")
            elif lower_shadow > 0.35:
                score += 1
                reasons.append(f"下影线偏长→多空争夺(+1)")
        else:
            if lower_shadow <= shadow_favor:
                score += 2
                reasons.append(f"下影线小({lower_shadow:.0%})→空头无支撑(+2)")
            if 0.10 <= upper_shadow <= 0.35:
                score += 2
                reasons.append(f"上影线适中({upper_shadow:.0%})→空头有压力(+2)")
            elif upper_shadow > 0.35:
                score += 1
                reasons.append(f"上影线偏长→多空争夺(+1)")

        final_score = min(score, cfg["weight"])
        return final_score, "; ".join(reasons) if reasons else "实体/影线不理想(+0)"

    # ── PA6: Pullback Confirmation (5 pts) ────────────────────

    def _score_pa6_pullback(self, data: dict, PA: dict) -> tuple:
        cfg = PA["PA6_pullback_confirm"]
        opposing = data.get("opposing_bars_count", 0)
        opt = cfg["optimal_opposing_bars"]

        if opposing >= opt:
            score = cfg["weight"]
            reason = f"前{opposing}根反向K线→回调充分(+{score})"
        elif opposing >= cfg["min_opposing_bars"]:
            score = int(cfg["weight"] * 0.6)
            reason = f"前{opposing}根反向K线→回调确认(+{score})"
        elif opposing == 1:
            score = int(cfg["weight"] * 0.3)
            reason = f"仅1根反向K线→回调不充分(+{score})"
        else:
            score = 0
            reason = "无反向K线→不是有效的回调入场(+0)"

        return score, reason

    # ── PA7: Special K-line Recognition (5 pts) ───────────────

    def _score_pa7_special_kline(self, data: dict, PA: dict) -> tuple:
        cfg = PA["PA7_special_kline"]
        is_pin = data.get("is_pin_bar", False)
        is_inside = data.get("is_inside_bar", False)
        is_outside = data.get("is_outside_bar", False)
        is_strong = data.get("is_strong_trend_bar", False)
        is_bullish = data.get("is_bullish_bar", True)

        score = 0
        bar_type = "standard"

        if is_strong:
            score = cfg["weight"]
            bar_type = "strong_trend"
            direction = "多头强趋势K线" if is_bullish else "空头强趋势K线"
            reason = f"{direction}→阿布最重视的信号K线(+{score})"
        elif is_pin:
            score = int(cfg["weight"] * 0.75)
            bar_type = "pin_bar"
            ptype = "锤子线(看涨)" if is_bullish else "倒锤子(看跌)"
            reason = f"Pin Bar {ptype}→需背景确认(+{score})"
        elif is_outside:
            score = int(cfg["weight"] * 0.5)
            bar_type = "outside_bar"
            reason = f"外包线→多空博弈激烈，等下一根确认(+{score})"
        elif is_inside:
            score = int(cfg["weight"] * 0.3)
            bar_type = "inside_bar"
            reason = f"内包线→蓄力中，突破方向决定走势(+{score})"
        else:
            reason = "标准K线，无特殊形态(+0)"

        return score, reason, bar_type

    # ── PA8: H1/H2/L1/L2 Count (10 pts) ──────────────────────

    def _score_pa8_h_count(self, data: dict, PA: dict, market_state: str) -> tuple:
        cfg = PA["PA8_h_count"]
        hc = data.get("h_count", 0)
        lc = data.get("l_count", 0)

        score = 0
        reason = ""

        if "bull" in market_state:
            count = hc
            label = "H"
            if count >= 2 and count <= 3:
                # H2 or H3 — best
                score = cfg["H2_score"] if count == 2 else cfg["H3_score"]
                reason = f"H{count}入场→{'黄金标准' if count == 2 else '楔形旗形'}（牛趋势二段回调）(+{score})"
            elif count == 1:
                score = cfg["H1_score"]
                reason = f"H1入场→首次回调，常是陷阱(+{score})"
            elif count >= 4:
                score = cfg["H4_plus_score"]
                reason = f"H{count}→回调过深，趋势存疑(+{score})"
            else:
                reason = "无H信号→等待回调(+0)"
        elif "bear" in market_state:
            count = lc
            label = "L"
            if count >= 2 and count <= 3:
                score = cfg["H2_score"] if count == 2 else cfg["H3_score"]
                reason = f"L{count}入场→{'黄金标准' if count == 2 else '楔形旗形'}（熊趋势二段反弹）(+{score})"
            elif count == 1:
                score = cfg["H1_score"]
                reason = f"L1入场→首次反弹，常是陷阱(+{score})"
            elif count >= 4:
                score = cfg["H4_plus_score"]
                reason = f"L{count}→反弹过深，趋势存疑(+{score})"
            else:
                reason = "无L信号→等待反弹(+0)"
        elif "trading_range" in market_state.lower():
            # In range, either H or L count can be used
            best = max(hc, lc)
            if best >= 2:
                score = int(cfg["H2_score"] * 0.6)
                reason = f"区间内{best}段推拉→适用剥头皮(+{score})"
            elif best == 1:
                score = cfg["H1_score"] // 2
                reason = f"区间内推拉初段→谨慎(+{score})"
            else:
                reason = "区间内无明显推拉结构(+0)"
        else:
            reason = "市场状态不明→不计数(+0)"

        return score, reason, hc, lc

    # ── PA9: Wedge Pattern (6 pts) ────────────────────────────

    def _score_pa9_wedge(self, data: dict, PA: dict, market_state: str) -> tuple:
        cfg = PA["PA9_wedge_pattern"]
        wedge_detected = data.get("wedge_detected", False)
        wedge_type = data.get("wedge_type", "none")
        parabolic = data.get("parabolic_wedge", False)

        score = 0
        wtype_out = wedge_type

        if not wedge_detected:
            return 0, "未检测到楔形结构(+0)", "none"

        if parabolic:
            score = cfg["weight"]
            wtype_out = "parabolic"
            reason = f"抛物线楔形→抢购/抛售高潮，反转概率极大(+{score})"
        elif wedge_type in ("bull_wedge", "bear_wedge"):
            # Check validity: need to be in the right market state
            if "bull" in market_state and wedge_type == "bull_wedge":
                # Bull wedge in bull trend = bullish flag, not reversal
                score = int(cfg["weight"] * 0.5)
                reason = f"牛旗楔形→趋势中继(+{score})"
            elif "bear" in market_state and wedge_type == "bear_wedge":
                score = int(cfg["weight"] * 0.5)
                reason = f"熊旗楔形→趋势中继(+{score})"
            else:
                score = int(cfg["weight"] * 0.75)
                reason = f"{'牛' if wedge_type == 'bull_wedge' else '熊'}楔形→可能反转(+{score})"
        elif wedge_type == "nested":
            score = cfg["weight"]
            reason = f"嵌套楔形→多重时间周期共振，阿布最高胜率形态(+{score})"
        else:
            score = int(cfg["weight"] * 0.3)
            reason = f"楔形结构不明确(+{score})"

        return min(score, cfg["weight"]), reason, wtype_out

    # ── PA10: S/R Confluence (6 pts) ──────────────────────────

    def _score_pa10_sr(self, data: dict, PA: dict) -> tuple:
        cfg = PA["PA10_sr_confluence"]
        sr_count = data.get("sr_confluence_count", 0)

        if sr_count >= cfg["confluence_excellent"]:
            score = cfg["weight"]
            reason = f"{sr_count}重支撑/阻力共振→极强(+{score})"
        elif sr_count >= cfg["confluence_good"]:
            score = int(cfg["weight"] * 0.7)
            reason = f"{sr_count}重共振→较强(+{score})"
        elif sr_count >= cfg["confluence_min"]:
            score = int(cfg["weight"] * 0.4)
            reason = f"{sr_count}重共振→一般(+{score})"
        else:
            score = 0
            reason = "无支撑阻力共振(+0)"

        return score, reason, sr_count

    # ── PA11: Volume (3 pts) ──────────────────────────────────

    def _score_pa11_volume(self, data: dict, PA: dict) -> tuple:
        cfg = PA["PA11_volume"]
        vr = data.get("vol_ratio", 1)
        turnover = data.get("avg_turnover_5d", 0)

        score = 0
        reasons = []

        if cfg["min_vol_ratio"] <= vr <= cfg["max_vol_ratio"]:
            score += 2
            reasons.append(f"量比{vr:.1f}正常(+2)")
        elif vr < cfg["min_vol_ratio"]:
            score += 1
            reasons.append(f"缩量(量比{vr:.1f})→需等放量确认(+1)")

        if isinstance(turnover, float) and turnover < 100:
            if cfg["min_turnover"] <= turnover <= cfg["max_turnover"]:
                score += 1
                reasons.append(f"换手{turnover:.1%}健康(+1)")
        else:
            score += 1
            reasons.append("换手数据不可用(+1)")

        return score, "; ".join(reasons) if reasons else "量能异常(+0)"

    # ── PA12: Sector/Mainstream (3 pts) ───────────────────────

    def _score_pa12_sector(self, data: dict, sector: dict, PA: dict) -> tuple:
        cfg = PA["PA12_sector"]
        rank_pct = sector.get("rank_pct", 1.0)
        rank = sector.get("rank", 99)
        follower_count = sector.get("follower_count", 0)

        score = 0
        reasons = []

        if rank_pct <= cfg["sector_rank_top_pct"] or rank <= 10:
            score += 2
            reasons.append(f"板块排名前{cfg['sector_rank_top_pct']:.0%}(+2)")

        if rank <= cfg["leader_top_n"] and follower_count >= cfg["min_follower_count"]:
            score += 1
            result.leader_level = "leader"
            reasons.append(f"板块龙头(排名{rank},跟风{follower_count}只)(+1)")
        elif rank <= cfg["leader_top_n"]:
            score += 1
            result.leader_level = "top_only"
            reasons.append(f"板块前排(排名{rank})(+1)")

        return score, "; ".join(reasons) if reasons else "非主线(+0)"

    # ── PA13: Emotion Cycle (4 pts) ───────────────────────────

    def _score_pa13_emotion(self, PA: dict) -> tuple:
        cfg = PA["PA13_emotion"]
        lu = self.ctx.get("limit_up_count", 0)
        chain = self.ctx.get("max_chain_height", 0)

        if lu <= cfg["ice_limit_up_max"] and chain <= cfg["ice_chain_max"]:
            score = cfg["weight"]
            phase = "ice"
            reason = f"冰点期(涨停{lu},连板{chain})→最佳布局窗口(+{score})"
        elif lu <= cfg["diverge_limit_up_max"] and chain <= cfg["diverge_chain_max"]:
            score = cfg["weight"]
            phase = "diverge"
            reason = f"分歧期(涨停{lu},连板{chain})→最佳入场窗口(+{score})"
        elif lu < cfg["euphoria_limit_up_min"]:
            score = cfg["weight"] // 2
            phase = "consensus"
            reason = f"一致期(涨停{lu})→可追但控仓(+{score})"
        else:
            score = 0
            phase = "euphoria"
            reason = f"高潮期(涨停{lu})→禁止入场(X12)(+0)"

        return score, reason, phase

    # ═══════════════════════════════════════════════════════════
    # Strengthen Rules (v4.2: B2+B6 only, 0-10 pts)
    # ═══════════════════════════════════════════════════════════

    def _score_strengthen(self, result: ScoreResult, data: dict, sector: dict):
        B = self.rules["strengthen"]
        score = 0

        # B2: Divergence reversal (分歧转一致)
        prev_vr = data.get("prev_day_vol_ratio", 1)
        prev_ret = data.get("prev_day_ret", 0)
        today_vr = data.get("vol_ratio", 1)
        today_ret = data.get("today_ret", 0)
        b2 = (prev_vr > B["B2_divergence"]["prev_day_vol_min_ratio"]
              and prev_ret < 0
              and today_vr < B["B2_divergence"]["today_vol_max_ratio"]
              and today_ret > 0)
        if b2: score += B["B2_divergence"]["weight"]
        result.bonus_details["B2_divergence"] = b2

        # B6: Weak-to-strong (弱转强)
        ret_3d = data.get("pre_3d_return", data.get("pre_5d_return", 0) * 0.6)
        today_ret = data.get("today_ret", 0)
        today_vr2 = data.get("vol_ratio", 1)
        b6 = (ret_3d < B["B6_weak_to_strong"]["max_ret_3d"]
              and today_ret > B["B6_weak_to_strong"]["min_ret_today"]
              and today_vr2 > B["B6_weak_to_strong"]["min_vol_ratio"])
        if b6: score += B["B6_weak_to_strong"]["weight"]
        result.bonus_details["B6_weak_to_strong"] = b6

        result.bonus_score = score


# ─── Market Context Builder ─────────────────────────────────

def build_market_context(benchmark_data: Optional[dict] = None) -> dict:
    """Fetch market-wide data needed for PA13/X10-X12 scoring."""
    import time as _time

    ctx = {
        "limit_up_count": 0,
        "limit_down_count": 0,
        "max_chain_height": 0,
        "sector_leaderboard": {},
        "lhb_data": {},
        "benchmark": benchmark_data or {},
    }

    def _ak_call(fn, *args, max_tries=3, base_sleep=1.5, **kwargs):
        for attempt in range(max_tries):
            try:
                _time.sleep(base_sleep * (attempt + 0.5))
                return fn(*args, **kwargs)
            except Exception as e:
                if attempt < max_tries - 1:
                    wait = base_sleep * (2 ** attempt)
                    print(f"    akshare retry {attempt+1}/{max_tries} in {wait:.0f}s...")
                    _time.sleep(wait)
        return None

    # C5 → PA13: Limit-up pool
    try:
        from direct_api import get_limit_up_pool
        zt = get_limit_up_pool()
        if zt is not None and len(zt) > 0:
            ctx["limit_up_count"] = len(zt)
            ctx["max_chain_height"] = 1
    except Exception:
        try:
            import akshare as ak
            zt = _ak_call(ak.stock_zt_pool_em, date=None)
            if zt is not None and len(zt) > 0:
                ctx["limit_up_count"] = len(zt)
                ctx["max_chain_height"] = int(zt["连板数"].max()) if "连板数" in zt.columns else 1
        except Exception:
            pass

    # Sector leaderboard
    try:
        from direct_api import get_industry_sectors, get_sector_constituents
        sec_df = get_industry_sectors()
        if sec_df is not None and len(sec_df) > 0:
            sec_df = sec_df.sort_values("change_pct", ascending=False).head(15)
            for _, row in sec_df.iterrows():
                sector_name = row["name"]
                sector_code = row["code"]
                tickers_list = []
                if _time.time() - getattr(build_market_context, "_last_sector_call", 0) < 60:
                    pass
                else:
                    _time.sleep(1.5)
                    try:
                        cons = get_sector_constituents(sector_code)
                        if cons is not None:
                            tickers_list = cons["ticker"].tolist()
                    except Exception:
                        pass
                    build_market_context._last_sector_call = _time.time()
                ctx["sector_leaderboard"][sector_name] = {
                    "stocks": tickers_list,
                    "count": len(tickers_list),
                    "change_pct": row["change_pct"],
                }
    except Exception:
        pass

    # LHB data
    try:
        import akshare as ak
        lhb_df = _ak_call(ak.stock_lhb_stock_detail_date_em, date=None)
        if lhb_df is not None and len(lhb_df) > 0:
            for _, row in lhb_df.iterrows():
                ticker = str(row.get("代码", "")).zfill(6)
                if ticker not in ctx["lhb_data"]:
                    ctx["lhb_data"][ticker] = {"net_buy": 0, "seats": [], "has_institution": False}
                e = ctx["lhb_data"][ticker]
                e["net_buy"] += float(row.get("净买额", 0) or 0)
                seat = str(row.get("营业部名称", ""))
                if seat:
                    e["seats"].append(seat)
                if "机构" in seat:
                    e["has_institution"] = True
    except Exception:
        pass

    return ctx
