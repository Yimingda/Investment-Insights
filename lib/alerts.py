"""跨品种阈值实时预警 —— 轻量扫描全部品种的主价格序列，汇总触发的预警。

只取每个品种的主价格序列（与各页共用缓存，无额外网络成本），
计算 MA / RSI / 单日涨跌等通用阈值。数据拿不到的品种自动跳过。
"""
from __future__ import annotations

from . import indicators


def scan(modules) -> list[tuple]:
    """返回 [(module, 预警等级cls, 文本), ...]。等级用 theme 的 alert-* 类。"""
    out = []
    for m in modules:
        try:
            series = m.scan_series()
        except Exception:
            series = None
        if not series or len(series) < 15:
            continue
        price = series[-1]
        ma = indicators.sma(series, 200 if len(series) >= 60 else 30)
        rsi = indicators.rsi(series, 14)
        chg = indicators.pct_change(series, 1)

        if ma and price < ma:
            out.append((m, "alert-warn", f"{m.icon} {m.name} 跌破均线（{m.fmt_price(ma)}）"))
        if rsi is not None and rsi > 72:
            out.append((m, "alert-warn", f"{m.icon} {m.name} RSI {rsi:.0f} 超买"))
        elif rsi is not None and rsi < 28:
            out.append((m, "alert-up", f"{m.icon} {m.name} RSI {rsi:.0f} 超卖（关注反弹）"))
        if abs(chg) >= 3:
            cls = "alert-dn" if chg < 0 else "alert-up"
            out.append((m, cls, f"{m.icon} {m.name} 单日 {chg:+.1f}%"))
    return out
