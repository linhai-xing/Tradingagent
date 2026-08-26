"""Trist Selector v4.0 — Entry Signal Detection (阿布价格行为学)
新增：信号K线/入场K线区分 + H1/H2/L1/L2计数 + 楔形识别 + 执行门禁
"""
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class EntrySignal:
    name: str
    description: str
    confidence: str    # "high" | "medium" | "low"
    scenario: str


@dataclass
class SignalBarResult:
    """信号K线检测结果 — 阿布核心：信号K线≠入场K线"""
    is_valid: bool = False
    quality: str = "poor"           # "excellent" | "good" | "fair" | "poor"
    bar_type: str = "standard"      # "strong_trend" | "pin_bar" | "inside_bar" | "outside_bar" | "standard"
    direction: str = "neutral"      # "bullish" | "bearish" | "neutral"
    close_position: float = 0.5     # 0-1, where in the bar range did it close
    body_ratio: float = 0.0         # body / total range
    upper_shadow_ratio: float = 0.0
    lower_shadow_ratio: float = 0.0
    high: float = 0.0               # signal bar high (for buy stop placement)
    low: float = 0.0                # signal bar low (for sell stop / stop loss)
    close: float = 0.0
    open: float = 0.0
    opposing_bars: int = 0          # consecutive opposing bars before signal
    description: str = ""


@dataclass
class EntryGateResult:
    """入场门禁结果 — 阿布核心：信号K线之后才入场"""
    gate_a_passed: bool = False     # GATE-A: price broke signal bar extreme
    gate_b_passed: bool = False     # GATE-B: entry bar close confirms direction
    entry_trigger_price: float = 0.0  # buy stop / sell stop level
    stop_loss_price: float = 0.0      # stop loss level
    entry_bar_close: float = 0.0
    recommendation: str = ""


def detect_signal_bar(kline_data: Dict) -> SignalBarResult:
    """检测最近一根已完成K线是否为有效的信号K线。

    阿布标准：
    1. 收盘在K线极端位置（顶部/底部 1/3）
    2. 实体饱满（body > 40% of range）
    3. 影线方向有利于趋势
    4. 前有反向K线确认回调

    Args:
        kline_data: {closes, opens, highs, lows, volumes}
    Returns:
        SignalBarResult with quality assessment
    """
    closes = np.array(kline_data.get("closes", []), dtype=float)
    opens = np.array(kline_data.get("opens", []), dtype=float)
    highs = np.array(kline_data.get("highs", []), dtype=float)
    lows = np.array(kline_data.get("lows", []), dtype=float)

    if len(closes) < 5:
        return SignalBarResult()

    result = SignalBarResult()

    # Analyze the last completed bar as potential signal bar
    idx = -1
    c = closes[idx]
    o = opens[idx]
    h = highs[idx]
    l = lows[idx]

    result.high = float(h)
    result.low = float(l)
    result.close = float(c)
    result.open = float(o)

    total_range = h - l
    if total_range <= 0:
        return result

    body = abs(c - o)
    upper_shadow = h - max(c, o)
    lower_shadow = min(c, o) - l

    # Direction
    is_bullish = c > o
    result.direction = "bullish" if is_bullish else "bearish"
    result.body_ratio = float(body / total_range)
    result.upper_shadow_ratio = float(upper_shadow / total_range)
    result.lower_shadow_ratio = float(lower_shadow / total_range)

    # Close position in range (1 = at top, 0 = at bottom)
    result.close_position = float((c - l) / total_range)

    # ── Special K-line type detection ──
    # Strong trend bar: body > 70%, close at extreme, tiny opposite shadow
    if result.body_ratio >= 0.70:
        if is_bullish and result.upper_shadow_ratio <= 0.10:
            result.bar_type = "strong_trend"
        elif not is_bullish and result.lower_shadow_ratio <= 0.10:
            result.bar_type = "strong_trend"

    # Pin Bar: one long shadow (>2x body), tiny other shadow
    if result.bar_type == "standard":
        if is_bullish and lower_shadow > body * 2 and upper_shadow < body * 0.3:
            result.bar_type = "pin_bar"
        elif not is_bullish and upper_shadow > body * 2 and lower_shadow < body * 0.3:
            result.bar_type = "pin_bar"

    # Inside Bar: contained within previous bar
    if len(highs) >= 2:
        if h < highs[-2] and l > lows[-2]:
            result.bar_type = "inside_bar"

    # Outside Bar: engulfs previous bar
    if len(highs) >= 2:
        if h > highs[-2] and l < lows[-2]:
            result.bar_type = "outside_bar"

    # ── Opposing bars before signal ──
    result.opposing_bars = _count_opposing_bars(closes, opens, is_bullish)

    # ── Quality assessment ──
    quality_score = 0

    # Close position (40%)
    if result.close_position >= 0.85 or result.close_position <= 0.15:
        quality_score += 40
    elif result.close_position >= 0.67 or result.close_position <= 0.33:
        quality_score += 25
    elif result.close_position >= 0.50 or result.close_position <= 0.50:
        quality_score += 10

    # Body strength (30%)
    if result.body_ratio >= 0.60:
        quality_score += 30
    elif result.body_ratio >= 0.40:
        quality_score += 20
    elif result.body_ratio >= 0.25:
        quality_score += 10

    # Bar type bonus (15%)
    if result.bar_type == "strong_trend":
        quality_score += 15
    elif result.bar_type == "pin_bar":
        quality_score += 10
    elif result.bar_type == "outside_bar":
        quality_score += 5
    elif result.bar_type == "inside_bar":
        quality_score += 3

    # Opposing bars (15%)
    if result.opposing_bars >= 3:
        quality_score += 15
    elif result.opposing_bars >= 2:
        quality_score += 10
    elif result.opposing_bars >= 1:
        quality_score += 5

    if quality_score >= 75:
        result.quality = "excellent"
        result.is_valid = True
    elif quality_score >= 55:
        result.quality = "good"
        result.is_valid = True
    elif quality_score >= 35:
        result.quality = "fair"
        result.is_valid = True
    else:
        result.quality = "poor"

    # Build description
    type_names = {
        "strong_trend": "强趋势K线",
        "pin_bar": "Pin Bar(锤子线/倒锤子)",
        "inside_bar": "内包线",
        "outside_bar": "外包线",
        "standard": "标准K线",
    }
    dir_name = "多头" if is_bullish else "空头"
    result.description = (
        f"{dir_name}{type_names.get(result.bar_type, '标准K线')} | "
        f"收盘位置{result.close_position:.0%} | 实体{result.body_ratio:.0%} | "
        f"前{result.opposing_bars}根反向K线 | "
        f"质量:{result.quality}"
    )

    return result


def _count_opposing_bars(closes: np.ndarray, opens: np.ndarray, is_bullish: bool) -> int:
    """Count consecutive opposing bars before the current signal bar."""
    count = 0
    # Start from second-to-last bar, go backwards
    for i in range(len(closes) - 2, max(len(closes) - 10, -1), -1):
        bar_bullish = closes[i] > opens[i]
        if is_bullish and not bar_bullish:  # looking for bearish bars before bullish signal
            count += 1
        elif not is_bullish and bar_bullish:  # looking for bullish bars before bearish signal
            count += 1
        else:
            break
    return count


def count_h_l_signals(kline_data: Dict, market_state: str = "unknown") -> Tuple[int, int, str]:
    """Count H1/H2/L1/L2 signals from bar-by-bar analysis.

    阿布数K法：
    - 牛趋势中：统计回调段数。每次价格低点更低然后高点上破前K高点 = 一次H信号
    - 熊趋势中：统计反弹段数。每次价格高点更高然后低点下破前K低点 = 一次L信号

    Args:
        kline_data: raw K-line arrays
        market_state: "trend_bull" | "trend_bear" | "trading_range" | "unknown"

    Returns:
        (h_count, l_count, description)
    """
    closes = np.array(kline_data.get("closes", []), dtype=float)
    highs = np.array(kline_data.get("highs", []), dtype=float)
    lows = np.array(kline_data.get("lows", []), dtype=float)

    h_count = 0
    l_count = 0
    description = ""

    if len(closes) < 20:
        return 0, 0, "K线数据不足"

    # Determine trend direction from EMA
    ema20 = _calc_ema(closes, 20)

    # ── Count H signals (for bull trend: pullback legs) ──
    # Look for: price making lower lows (pullback), then a bar's high breaking
    # above prior bar's high (H signal)
    lookback = min(20, len(closes) - 1)
    in_pullback = False
    pullback_low_idx = 0
    recent_highs_break = 0

    for i in range(len(closes) - lookback, len(closes)):
        bar_high = highs[i]
        prev_high = highs[i - 1] if i > 0 else bar_high
        bar_low = lows[i]
        prev_low = lows[i - 1] if i > 0 else bar_low
        bar_close = closes[i]

        # Detect pullback start: price starts making lower lows while below EMA
        if bar_low < prev_low and bar_close < ema20[i] if i < len(ema20) else False:
            in_pullback = True
            pullback_low_idx = i

        # Detect H signal: bar's high breaks above prior bar's high (end of pullback leg)
        if bar_high > prev_high:
            if in_pullback or recent_highs_break > 0:
                # Count as a new H signal
                h_count += 1
                recent_highs_break = h_count
                in_pullback = False

    # ── Count L signals (for bear trend: rally legs) ──
    in_rally = False
    recent_lows_break = 0

    for i in range(len(closes) - lookback, len(closes)):
        bar_high = highs[i]
        prev_high = highs[i - 1] if i > 0 else bar_high
        bar_low = lows[i]
        prev_low = lows[i - 1] if i > 0 else bar_low
        bar_close = closes[i]

        # Detect rally start
        if bar_high > prev_high and bar_close > ema20[i] if i < len(ema20) else False:
            in_rally = True

        # Detect L signal: bar's low breaks below prior bar's low
        if bar_low < prev_low:
            if in_rally or recent_lows_break > 0:
                l_count += 1
                recent_lows_break = l_count
                in_rally = False

    # Format description
    if "bull" in market_state:
        if h_count == 0:
            description = "无H信号→等待回调"
        elif h_count == 1:
            description = f"H1→首次回调，常是陷阱"
        elif h_count == 2:
            description = f"H2→黄金标准！二段回调入场"
        elif h_count == 3:
            description = f"H3→楔形旗形，高概率"
        else:
            description = f"H{h_count}→回调过深"
    elif "bear" in market_state:
        if l_count == 0:
            description = "无L信号→等待反弹"
        elif l_count == 1:
            description = f"L1→首次反弹，常是陷阱"
        elif l_count == 2:
            description = f"L2→黄金标准！二段反弹入场"
        elif l_count == 3:
            description = f"L3→楔形旗形，高概率"
        else:
            description = f"L{l_count}→反弹过深"
    else:
        description = f"H{h_count}/L{l_count}→区间或不明"

    return h_count, l_count, description


def detect_wedge(kline_data: Dict) -> Tuple[bool, str, bool]:
    """Detect wedge (楔形) patterns from recent price action.

    阿布楔形分类：
    - bull_wedge: 下降楔形（牛旗），看涨
    - bear_wedge: 上升楔形（熊旗），看跌
    - parabolic: 抛物线楔形，加速消耗后剧烈反转
    - nested: 嵌套楔形，大楔形内的子楔形

    Returns:
        (is_wedge, wedge_type, is_parabolic)
    """
    closes = np.array(kline_data.get("closes", []), dtype=float)
    highs = np.array(kline_data.get("highs", []), dtype=float)
    lows = np.array(kline_data.get("lows", []), dtype=float)

    if len(closes) < 20:
        return False, "none", False

    lookback = min(30, len(closes))

    # Find swing highs and lows over lookback period
    swing_highs = []
    swing_lows = []

    for i in range(len(closes) - lookback + 2, len(closes) - 1):
        # Local swing high: higher than neighbors
        if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
            swing_highs.append((i, highs[i]))
        # Local swing low: lower than neighbors
        if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            swing_lows.append((i, lows[i]))

    # Need at least 3 swing points for a wedge
    if len(swing_highs) < 3 and len(swing_lows) < 3:
        return False, "none", False

    # ── Check for rising wedge (bear flag) ──
    # Higher swing highs + higher swing lows converging
    if len(swing_highs) >= 3 and len(swing_lows) >= 3:
        recent_highs = swing_highs[-3:]
        recent_lows = swing_lows[-3:]

        h_values = [h[1] for h in recent_highs]
        l_values = [ll[1] for ll in recent_lows]

        h_rising = h_values[-1] > h_values[0]
        l_rising = l_values[-1] > l_values[0]
        h_slope = (h_values[-1] - h_values[0]) / (h_values[0] + 0.01)
        l_slope = (l_values[-1] - l_values[0]) / (l_values[0] + 0.01)

        # Rising wedge: both rising but lows rising faster (converging)
        if h_rising and l_rising and l_slope > h_slope:
            # Check for parabolic acceleration
            parabolic = (h_slope > 0.30) and (l_slope > 0.30)
            return True, "bear_wedge" if not parabolic else "parabolic", parabolic

        # Falling wedge: both falling but highs falling faster (converging)
        h_falling = h_values[-1] < h_values[0]
        l_falling = l_values[-1] < l_values[0]
        h_slope_neg = abs((h_values[0] - h_values[-1]) / (h_values[0] + 0.01))
        l_slope_neg = abs((l_values[0] - l_values[-1]) / (l_values[0] + 0.01))

        if h_falling and l_falling and h_slope_neg > l_slope_neg:
            parabolic = (h_slope_neg > 0.30) and (l_slope_neg > 0.30)
            return True, "bull_wedge" if not parabolic else "parabolic", parabolic

    # ── Simplified: check 3-push structure from consecutive swing points ──
    if len(swing_highs) >= 3:
        h_vals = [h[1] for h in swing_highs[-3:]]
        if h_vals[-1] > h_vals[-2] > h_vals[-3]:
            return True, "bear_wedge", False

    if len(swing_lows) >= 3:
        l_vals = [ll[1] for ll in swing_lows[-3:]]
        if l_vals[-1] < l_vals[-2] < l_vals[-3]:
            return True, "bull_wedge", False

    return False, "none", False


def compute_entry_gates(kline_data: Dict, signal_bar: SignalBarResult,
                         direction: str = "buy") -> EntryGateResult:
    """Compute entry gates (阿布入场门禁).

    GATE-A: 价格突破信号K线极值 → 入场触发
    GATE-B: 入场K线收盘确认方向 → 持仓确认

    操作流程：
    1. 今天收盘后识别信号K线
    2. 明天挂止损单在信号K线高/低点外1 tick
    3. 价格触发 → GATE-A通过（入场）
    4. 入场当日收盘价确认方向 → GATE-B通过（持仓）

    Args:
        kline_data: raw K-line arrays
        signal_bar: detected signal bar result
        direction: "buy" or "sell"

    Returns:
        EntryGateResult with gate status and levels
    """
    result = EntryGateResult()

    if not signal_bar.is_valid:
        result.recommendation = "无有效信号K线，不入场"
        return result

    closes = np.array(kline_data.get("closes", []), dtype=float)
    highs = np.array(kline_data.get("highs", []), dtype=float)
    lows = np.array(kline_data.get("lows", []), dtype=float)

    tick_size = 0.01  # default tick for most stocks

    if direction == "buy":
        # Buy stop above signal bar high
        result.entry_trigger_price = round(signal_bar.high + tick_size, 2)
        result.stop_loss_price = round(signal_bar.low - tick_size, 2)

        # Check if last bar (entry bar) broke above signal bar high
        if len(highs) >= 1:
            last_high = highs[-1]
            if last_high >= result.entry_trigger_price:
                result.gate_a_passed = True
                # GATE-B: did entry bar close bullish?
                if len(closes) >= 1 and len(opens := np.array(kline_data.get("opens", []), dtype=float)) >= 1:
                    if closes[-1] > opens[-1] and closes[-1] > signal_bar.high:
                        result.gate_b_passed = True
                        result.recommendation = "入场触发+收盘确认→持仓"
                    else:
                        result.recommendation = "入场触发但收盘未确认→减仓观察"
            else:
                result.recommendation = f"挂买单@{result.entry_trigger_price}，止损@{result.stop_loss_price}，等待触发"
    else:
        # Sell stop below signal bar low
        result.entry_trigger_price = round(signal_bar.low - tick_size, 2)
        result.stop_loss_price = round(signal_bar.high + tick_size, 2)

        if len(lows) >= 1:
            last_low = lows[-1]
            if last_low <= result.entry_trigger_price:
                result.gate_a_passed = True
                if len(closes) >= 1 and len(opens := np.array(kline_data.get("opens", []), dtype=float)) >= 1:
                    if closes[-1] < opens[-1] and closes[-1] < signal_bar.low:
                        result.gate_b_passed = True
                        result.recommendation = "入场触发+收盘确认→持仓"
                    else:
                        result.recommendation = "入场触发但收盘未确认→减仓观察"
            else:
                result.recommendation = f"挂卖单@{result.entry_trigger_price}，止损@{result.stop_loss_price}，等待触发"

    result.entry_bar_close = float(closes[-1]) if len(closes) > 0 else 0.0

    return result


def detect_entry_signals(kline_data: Dict, ticker: str = "") -> List[EntrySignal]:
    """Detect entry signals from daily K-line data.

    v4.0: Includes traditional signals + 阿布 signal bar detection.
    """
    signals = []

    closes = kline_data.get("closes", [])
    opens = kline_data.get("opens", [])
    highs = kline_data.get("highs", [])
    lows = kline_data.get("lows", [])
    volumes = kline_data.get("volumes", [])

    if len(closes) < 20:
        return signals

    closes_arr = np.array(closes, dtype=float)
    opens_arr = np.array(opens, dtype=float) if opens else closes_arr
    highs_arr = np.array(highs, dtype=float) if highs else closes_arr
    lows_arr = np.array(lows, dtype=float) if lows else closes_arr
    volumes_arr = np.array(volumes, dtype=float)

    # ── 阿布信号K线检测 ──
    sig_bar = detect_signal_bar(kline_data)
    if sig_bar.is_valid:
        signals.append(EntrySignal(
            name=f"信号K线({sig_bar.bar_type})",
            description=sig_bar.description,
            confidence="high" if sig_bar.quality in ("excellent", "good") else "medium",
            scenario="阿布价格行为学：信号K线确认，次日挂止损单等待入场K线触发"
        ))

        # Add entry gate info
        gates = compute_entry_gates(kline_data, sig_bar,
                                     direction="buy" if sig_bar.direction == "bullish" else "sell")
        signals.append(EntrySignal(
            name="入场门禁",
            description=gates.recommendation,
            confidence="high" if gates.gate_a_passed else "medium",
            scenario=f"GATE-A({'+' if gates.gate_a_passed else 'x'}) GATE-B({'+' if gates.gate_b_passed else 'x'}) | 入场价:{gates.entry_trigger_price} 止损:{gates.stop_loss_price}"
        ))

    # ── H1/H2/L1/L2 信号 ──
    hc, lc, h_desc = count_h_l_signals(kline_data)
    if hc >= 2 or lc >= 2:
        signals.append(EntrySignal(
            name=f"H{hc}/L{lc}计数",
            description=h_desc,
            confidence="high" if (hc == 2 or lc == 2) else "medium",
            scenario="阿布数K法：H2/L2是黄金标准入场点"
        ))

    # ── 楔形信号 ──
    is_wedge, wtype, parabolic = detect_wedge(kline_data)
    if is_wedge:
        wname = {"bull_wedge": "牛旗楔形", "bear_wedge": "熊旗楔形", "parabolic": "抛物线楔形"}.get(wtype, "楔形")
        signals.append(EntrySignal(
            name=wname,
            description="三推结构确认" + ("→加速消耗!反转概率极大" if parabolic else ""),
            confidence="high" if parabolic else "medium",
            scenario="阿布楔形交易：抛物线楔形=抢购/抛售高潮"
        ))

    # MAs
    ma5 = np.concatenate([np.full(4, np.nan), np.convolve(closes_arr, np.ones(5)/5, mode='valid')])
    vol_ma5 = np.concatenate([np.full(4, np.nan), np.convolve(volumes_arr, np.ones(5)/5, mode='valid')])

    today_close = closes_arr[-1]
    today_open = opens_arr[-1]
    today_high = highs_arr[-1]
    today_low = lows_arr[-1]
    today_vol = volumes_arr[-1]
    yesterday_close = closes_arr[-2]
    yesterday_open = opens_arr[-2]
    yesterday_vol = volumes_arr[-2]

    ma5_today = ma5[-1] if not np.isnan(ma5[-1]) else today_close
    vol_ma5_today = vol_ma5[-1] if not np.isnan(vol_ma5[-1]) else today_vol

    above_ma5 = today_close > ma5_today
    gain_pct = (today_close / yesterday_close - 1)
    body_pct = abs(today_close - today_open) / today_open if today_open > 0 else 0
    high_low_range = (today_high - today_low)
    close_in_range = (today_close - today_low) / high_low_range if high_low_range > 0 else 1.0
    vol_vs_ma5 = today_vol / vol_ma5_today if vol_ma5_today > 0 else 1.0

    # === S1: 缩量十字星 ===
    if above_ma5 and body_pct < 0.008 and vol_vs_ma5 < 0.6:
        signals.append(EntrySignal(
            name="缩量十字星",
            description=f"股价{today_close:.2f}在MA5({ma5_today:.2f})上方收十字星，量缩至均量{vol_vs_ma5*100:.0f}%",
            confidence="high",
            scenario="趋势中继，最佳低吸点"
        ))

    # === S2: MA5支撑确认 ===
    low_near_ma5 = abs(today_low - ma5_today) / ma5_today < 0.015 if ma5_today > 0 else False
    bullish_candle = today_close > today_open and today_close > yesterday_close

    if low_near_ma5 and bullish_candle and above_ma5:
        signals.append(EntrySignal(
            name="MA5支撑确认",
            description=f"股价回踩MA5({ma5_today:.2f})不破，低点{today_low:.2f}，收阳线确认",
            confidence="high",
            scenario="强势股回调买入"
        ))

    # === S3: 放量突破 ===
    vol_surge = vol_vs_ma5 > 1.5
    price_break = gain_pct > 0.02
    very_strong = gain_pct > 0.07

    if ((vol_surge and price_break) or very_strong) and above_ma5 and close_in_range > 0.85:
        signals.append(EntrySignal(
            name="放量突破",
            description=f"量比{vol_vs_ma5:.1f}，涨幅{gain_pct*100:.1f}%，强势突破",
            confidence="high" if vol_surge else "medium",
            scenario="突破确认，右侧追入"
        ))

    # === S4: 分歧转一致 ===
    y_bearish = yesterday_close < yesterday_open
    y_high_vol = yesterday_vol > vol_ma5[-2] * 1.2 if len(vol_ma5) >= 2 and not np.isnan(vol_ma5[-2]) else False
    t_reversal = today_close > yesterday_close and today_open <= yesterday_close
    t_low_vol = vol_vs_ma5 < 0.8

    if y_bearish and y_high_vol and t_reversal:
        confidence = "high" if t_low_vol else "medium"
        signals.append(EntrySignal(
            name="分歧转一致",
            description=f"前日放量阴线→今日反包收{today_close:.2f}，分歧转一致",
            confidence=confidence,
            scenario="分歧转一致最佳切入点"
        ))

    # === S5: 尾盘缩量企稳 ===
    if close_in_range > 0.7 and vol_vs_ma5 < 1.0 and above_ma5:
        signals.append(EntrySignal(
            name="尾盘缩量企稳",
            description=f"收盘价{today_close:.2f}接近高点{today_high:.2f}，缩量站稳MA5",
            confidence="medium",
            scenario="下午尾盘确认买入"
        ))

    # === S6: 强势突破 ===
    overextended_20d = (today_close / closes_arr[-min(21, len(closes_arr))] - 1) > 0.30

    if gain_pct > 0.05 and close_in_range > 0.7 and above_ma5 and not overextended_20d:
        confidence = "high" if vol_vs_ma5 > 1.0 else "medium"
        signals.append(EntrySignal(
            name="强势突破",
            description=f"涨幅{gain_pct*100:.1f}%，收盘{today_close:.2f}接近最高{today_high:.2f}",
            confidence=confidence,
            scenario="趋势加速启动，次日开盘顺势介入"
        ))

    # === S10: 机构洗盘V转 ===
    ma10 = np.concatenate([np.full(9, np.nan), np.convolve(closes_arr, np.ones(10)/10, mode='valid')])
    ma10_today = ma10[-1] if not np.isnan(ma10[-1]) else today_close
    ma20_arr = np.concatenate([np.full(19, np.nan), np.convolve(closes_arr, np.ones(20)/20, mode='valid')])
    ma20_today = ma20_arr[-1] if not np.isnan(ma20_arr[-1]) else today_close

    low_near_ma10 = abs(today_low - ma10_today) / ma10_today < 0.02 if ma10_today > 0 else False
    above_ma10 = today_close > ma10_today
    lower_shadow = (min(today_open, today_close) - today_low) / today_open if today_open > 0 else 0
    has_long_shadow = lower_shadow > 0.03
    in_uptrend = today_close > ma20_today
    vol_not_panic = vol_vs_ma5 < 2.0

    if (low_near_ma10 or (today_low < ma10_today and above_ma10)) and above_ma10 and in_uptrend and vol_not_panic:
        if has_long_shadow or (today_low < ma10_today and above_ma10):
            signals.append(EntrySignal(
                name="机构洗盘V转",
                description=f"最低{today_low:.2f}触及MA10({ma10_today:.2f})后V转，下影线{lower_shadow*100:.1f}%",
                confidence="high",
                scenario="机构洗盘经典手法；历史胜率80%"
            ))

    return signals


def get_entry_recommendation(signals: List[EntrySignal]) -> Dict:
    """Generate entry recommendation based on detected signals."""
    high_conf = [s for s in signals if s.confidence == "high"]
    medium_conf = [s for s in signals if s.confidence == "medium"]

    # Check for 阿布 signal bar + H2/L2 combination (highest priority)
    has_signal_bar = any("信号K线" in s.name for s in signals)
    has_h2 = any("H2" in s.name or "L2" in s.name for s in signals if "H" in s.name)
    has_wedge = any("楔形" in s.name for s in signals)

    if has_signal_bar and has_h2:
        action = "ready"
        msg = "【阿布黄金组合】信号K线 + H2/L2！最高优先级入场"
    elif has_signal_bar and has_wedge:
        action = "ready"
        msg = "【阿布楔形组合】信号K线 + 楔形结构！高概率入场"
    elif high_conf:
        action = "ready"
        msg = f"发现{len(high_conf)}个高置信入场信号，可立即执行"
    elif medium_conf:
        action = "watch"
        msg = f"发现{len(medium_conf)}个中等置信信号，建议观察确认"
    else:
        action = "wait"
        msg = "未发现入场信号，等待"

    return {
        "action": action,
        "message": msg,
        "high_confidence": [s.name for s in high_conf],
        "medium_confidence": [s.name for s in medium_conf],
        "all_signals": [{"name": s.name, "confidence": s.confidence, "desc": s.description} for s in signals],
        "abu_combo": {
            "has_signal_bar": has_signal_bar,
            "has_h2": has_h2,
            "has_wedge": has_wedge,
        }
    }


def _calc_ema(data: np.ndarray, period: int) -> np.ndarray:
    """Calculate EMA for given period."""
    if len(data) < period:
        return np.full(len(data), np.mean(data))
    alpha = 2 / (period + 1)
    ema = np.zeros(len(data))
    ema[0] = data[0]
    for i in range(1, len(data)):
        ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]
    return ema
