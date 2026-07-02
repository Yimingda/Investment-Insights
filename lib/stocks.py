"""A股个股分析 —— 自选股输入后，按代码实时取数并给评分 + 建议。

代码→yfinance：6 开头→.SS（沪），0/2/3 开头→.SZ（深），8/4 开头→.BJ（北交所）。
数据走 yfinance，云端可用；取不到则返回 {"ok": False}。
"""
from __future__ import annotations

import streamlit as st

from . import data, indicators


def to_ticker(code: str) -> str:
    code = code.strip().upper()
    if "." in code:
        return code
    head = code[:1]
    if head == "6":
        return code + ".SS"
    if head in ("0", "2", "3"):
        return code + ".SZ"
    if head in ("8", "4"):
        return code + ".BJ"
    return code + ".SS"


def _advice(score: int, price: float, ma60: float, rsi: float, name: str) -> str:
    if score >= 62 and price < ma60:
        return f"{name}信号偏多但价格仍在 60 日均线下方，适合分批左侧布局，单只仓位建议 ≤5%，严设止损。"
    if score >= 62:
        return f"{name}趋势与动能向好，可持有 / 逢回调加仓；不宜追高，单只仓位 ≤5%。"
    if score >= 45:
        return f"{name}信号中性，建议观望或小仓试探，等待量价或基本面催化明朗后再加仓。"
    if rsi < 30:
        return f"{name}已超卖，或有技术性反弹，但趋势未明前不宜重仓，可小仓博弈并设硬止损。"
    return f"{name}多项指标偏空，建议规避或等待企稳，不接飞刀。"


@st.cache_data(ttl=900, show_spinner=False)
def analyze(code: str, name: str = "") -> dict:
    t = to_ticker(code)
    display = name or code
    res = data.yf_history(t, period="1y")
    if not res or len(res[0]) < 20:
        return {"ok": False, "code": code, "ticker": t, "name": display}
    closes = res[0]
    price = closes[-1]
    prev = closes[-2] if len(closes) > 1 else price
    chg = price - prev
    chg_pct = chg / prev * 100 if prev else 0.0
    ma20 = indicators.sma(closes, 20)
    ma60 = indicators.sma(closes, 60) or ma20 or price
    rsi = indicators.rsi(closes, 14) or 50
    mom20 = indicators.pct_change(closes, 20)
    macd = indicators.macd(closes)

    s = 50
    s += 8 if price > ma60 else -8
    s += 5 if (ma20 and ma60 and ma20 > ma60) else -5
    s += 8 if rsi < 30 else (3 if rsi < 45 else (-8 if rsi > 70 else 0))
    s += 5 if mom20 > 5 else (-5 if mom20 < -5 else 0)
    if macd:
        s += 4 if macd[2] > 0 else -4
    score = max(5, min(95, round(s)))

    return {
        "ok": True, "code": code, "ticker": t, "name": display,
        "price": price, "chg": chg, "chg_pct": chg_pct,
        "ma20": ma20, "ma60": ma60, "rsi": rsi, "mom20": mom20,
        "macd_hist": (macd[2] if macd else None),
        "bullish_ma": bool(ma20 and ma60 and ma20 > ma60),
        "score": score, "advice": _advice(score, price, ma60, rsi, display),
        "closes": closes[-120:], "dates": res[1][-120:],   # 供持仓监控画图
        "drawdown": indicators.drawdown_from_high(closes[-120:]),
    }


def parse_entries(raw: str) -> list[tuple]:
    """'600519 贵州茅台, 300750 宁德时代' → [('600519','贵州茅台'), ('300750','宁德时代')]"""
    out = []
    for part in raw.replace("，", ",").replace("、", ",").replace("\n", ",").split(","):
        toks = part.split()
        if toks:
            out.append((toks[0], " ".join(toks[1:])))
    return out
