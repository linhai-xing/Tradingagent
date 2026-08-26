"""Trist Selector v4.1 — Execution Gate (执行门禁).
Three hard gates, independent of scoring. All must pass before any order.

Gate-A: Entry method (signal bar != entry bar)
Gate-B: Post-entry confirmation
Gate-C: Time window (afternoon only, per user's 75% win rate data)

Usage:
    from gate import check_all_gates
    result = check_all_gates('limit_order', entry_time='14:30')
    if result['blocked']:
        print('Gate failed, do not enter')
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
        return GateResult(
            "Gate-A", True, "突破挂单入场",
            f"信号K线{signal_bar_date}已确认，挂突破单"
        )
    elif entry_method == "auction":
        return GateResult(
            "Gate-A", False, "竞价买入",
            "信号K线≠入场K线，竞价买入=同一根K线既是信号又是入场"
        )
    elif entry_method == "chase":
        return GateResult(
            "Gate-A", False, "盘中追入",
            "价格已远离信号K线高低点，盈亏比恶化"
        )
    else:
        return GateResult(
            "Gate-A", False, "入场方式不明",
            f"未指定入场方式({entry_method})，请使用 limit_order"
        )


def check_gate_b(entry_kline_close: float, entry_price: float,
                 signal_direction: str = "long") -> GateResult:
    """
    Gate-B: Entry bar must close in the direction of the trade.
    If entry bar closes against the trade, reduce or exit.

    Args:
        entry_kline_close: closing price of the entry bar (after signal bar)
        entry_price: your fill price
        signal_direction: 'long' or 'short'
    """
    if entry_kline_close <= 0:
        return GateResult(
            "Gate-B", True, "入场K线未收盘",
            "盘中检查，收盘后再确认"
        )

    if signal_direction == "long":
        if entry_kline_close >= entry_price:
            return GateResult(
                "Gate-B", True, "入场K线收阳确认",
                f"收{entry_kline_close:.2f}>=入场{entry_price:.2f}，持仓"
            )
        else:
            return GateResult(
                "Gate-B", False, "入场K线反向",
                f"收{entry_kline_close:.2f}<入场{entry_price:.2f}，次日减仓或清仓"
            )
    else:  # short
        if entry_kline_close <= entry_price:
            return GateResult(
                "Gate-B", True, "入场K线收阴确认",
                f"收{entry_kline_close:.2f}<=入场{entry_price:.2f}，持仓"
            )
        else:
            return GateResult(
                "Gate-B", False, "入场K线反向",
                f"收{entry_kline_close:.2f}>入场{entry_price:.2f}，次日减仓或清仓"
            )


def check_gate_c(entry_time: str = "") -> GateResult:
    """
    Gate-C: Entry must be after 14:00 (user's 75% afternoon win rate).
    Morning entries (before 11:30) are rejected.

    Args:
        entry_time: 'HH:MM' format, or datetime string with time portion
    """
    if not entry_time:
        now = datetime.now()
        hour = now.hour
        minute = now.minute
    else:
        try:
            time_str = entry_time
            if ' ' in time_str:
                time_str = time_str.split(' ')[1]
            parts = time_str.split(':')
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        except (ValueError, IndexError):
            return GateResult(
                "Gate-C", True, "时间解析失败，默认通过",
                f"无法解析'{entry_time}'"
            )

    if hour >= 14:
        return GateResult(
            "Gate-C", True, "下午入场",
            f"{hour:02d}:{minute:02d} 下午执行（胜率75%）"
        )
    elif hour >= 11:
        return GateResult(
            "Gate-C", False, "午间/早盘尾段",
            f"{hour:02d}:{minute:02d} 上午买入胜率仅27%，等下午14:00后"
        )
    else:
        return GateResult(
            "Gate-C", False, "早盘买入",
            f"{hour:02d}:{minute:02d} 上午买入胜率仅27%，等下午14:00后"
        )


def check_all_gates(entry_method: str = "", entry_price: float = 0,
                    entry_kline_close: float = 0, entry_time: str = "",
                    signal_bar_date: str = "",
                    signal_direction: str = "long") -> dict:
    """
    Run all three gates. Returns dict with individual results and overall pass/fail.

    Args:
        entry_method: 'limit_order' | 'auction' | 'chase'
        entry_price: fill price (for Gate-B)
        entry_kline_close: entry bar close (for Gate-B, 0=not yet closed)
        entry_time: 'HH:MM' (for Gate-C)
        signal_bar_date: date string (for Gate-A display)
        signal_direction: 'long' or 'short'

    Returns:
        dict with keys: 'gates', 'all_pass', 'blocked'
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
