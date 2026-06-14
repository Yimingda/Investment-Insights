"""品种模块基类 + 实时/模拟数据工具（单独成文件以避免循环导入）。"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

import streamlit as st

from lib import data, indicators
from lib.theme import DEFAULT_ACCENT
from lib.model import Snapshot, Indicator


class AssetModule:
    """品种基类。子类设置元信息并实现 build_snapshot()。"""
    id: str = ""
    name: str = ""
    icon: str = "📈"
    accent: str = DEFAULT_ACCENT
    price_prefix: str = "$"
    price_decimals: int = 2

    def fmt_price(self, p: float) -> str:
        return f"{self.price_prefix}{p:,.{self.price_decimals}f}"

    def build_snapshot(self, refresh: bool = False) -> Snapshot:  # pragma: no cover
        raise NotImplementedError

    # ── 共享指标：MACD（数据不足时返回 None，调用方忽略即可）──
    def macd_row(self, closes: list[float]) -> Indicator | None:
        res = indicators.macd(closes)
        if res is None:
            return None
        macd_line, _signal, hist = res
        if hist > 0:
            txt, cls = "金叉/多头动能", "badge-up"
        elif hist < 0:
            txt, cls = "死叉/空头动能", "badge-dn"
        else:
            txt, cls = "动能中性", "badge-neu"
        return Indicator("MACD(12,26,9)", self._fmt_macd(macd_line), txt, cls)

    @staticmethod
    def _fmt_macd(v: float) -> str:
        a = abs(v)
        if a < 1:
            return f"{v:.4f}"
        if a < 100:
            return f"{v:.2f}"
        return f"{v:,.0f}"

    # ── 共享工具：优先 yfinance 实时数据，失败则用模拟序列 ──
    def series_or_sim(self, ticker: str, anchors: list[float],
                      period: str = "3mo", refresh: bool = False):
        """返回 (收盘价 list, 日期 list, 是否实时)。"""
        res = data.yf_history(ticker, period=period)
        if res and res[0]:
            return res[0], res[1], True
        hist, dates = self.sim_fallback(anchors, refresh)
        return hist, dates, False

    def sim_fallback(self, anchors: list[float], refresh: bool = False):
        """模拟序列，持久化在 session_state。返回 (收盘价 list, 日期 list)。"""
        key = f"_hist_{self.id}"
        if key not in st.session_state:
            st.session_state[key] = [round(a * (1 + random.uniform(-0.01, 0.01)), 2)
                                     for a in anchors]
        elif refresh:
            cur = st.session_state[key][-1]
            nxt = round(cur * (1 + random.uniform(-0.015, 0.015)), 2)
            st.session_state[key].append(nxt)
            if len(st.session_state[key]) > 90:
                st.session_state[key].pop(0)
        hist = st.session_state[key]
        n = len(hist)
        dates = [(datetime.now() - timedelta(days=n - i)).strftime("%m/%d")
                 for i in range(n)]
        return hist, dates
