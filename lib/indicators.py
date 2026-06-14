"""纯函数：技术指标计算。输入价格序列，输出标量，无副作用、无外部依赖。"""
from __future__ import annotations


def sma(values: list[float], window: int) -> float | None:
    """简单移动均线。数据不足时取全部可用值。"""
    if not values:
        return None
    w = min(window, len(values))
    seg = values[-w:]
    return sum(seg) / len(seg)


def rsi(values: list[float], period: int = 14) -> float | None:
    """相对强弱指标（Wilder 平滑的简化版）。数据不足返回 None。"""
    if len(values) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    # 用最近 period 段的均值
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 1)


def pct_change(values: list[float], lookback: int = 1) -> float:
    """相对 lookback 根之前的百分比变化。"""
    if len(values) <= lookback:
        return 0.0
    prev = values[-1 - lookback]
    if prev == 0:
        return 0.0
    return (values[-1] - prev) / prev * 100


def abs_change(values: list[float], lookback: int = 1) -> float:
    if len(values) <= lookback:
        return 0.0
    return values[-1] - values[-1 - lookback]


def _ema_series(values: list[float], period: int) -> list[float]:
    """指数移动均线序列。"""
    k = 2 / (period + 1)
    out, e = [], values[0]
    for i, v in enumerate(values):
        e = v if i == 0 else v * k + e * (1 - k)
        out.append(e)
    return out


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """返回 (MACD线, 信号线, 柱状值hist) 最新值；数据不足返回 None。"""
    if len(values) < slow + signal:
        return None
    ef = _ema_series(values, fast)
    es = _ema_series(values, slow)
    macd_line = [a - b for a, b in zip(ef, es)]
    sig = _ema_series(macd_line, signal)
    return macd_line[-1], sig[-1], macd_line[-1] - sig[-1]


def drawdown_from_high(values: list[float]) -> float:
    """距区间最高点的回撤百分比（负值或 0）。"""
    if not values:
        return 0.0
    high = max(values)
    if high == 0:
        return 0.0
    return (values[-1] - high) / high * 100
