"""实时新闻 —— 为各品种抓取当前市场新闻头条，喂给 AI 分析并在页面展示。

数据源：A股用 akshare 中文快讯；其余用 Finnhub 分类新闻（需 FINNHUB_API_KEY）。
无源/失败一律返回 []，分析与页面照常工作（仅少了消息面）。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import streamlit as st

from . import data


@dataclass
class Headline:
    title: str
    source: str
    when: str
    url: str


# 品种 → Finnhub 新闻分类
_FINNHUB_CAT = {"crypto": "crypto", "forex": "forex",
                "gold": "general", "us_equity": "general"}


@st.cache_data(ttl=1800, show_spinner=False)
def _finnhub_news(category: str, api_key: str, limit: int):
    if not api_key:
        return []
    try:
        import requests
        r = requests.get("https://finnhub.io/api/v1/news",
                         params={"category": category, "token": api_key}, timeout=10)
        r.raise_for_status()
        out = []
        for it in (r.json() or [])[:limit]:
            ts = it.get("datetime")
            when = dt.datetime.fromtimestamp(ts).strftime("%m/%d %H:%M") if ts else ""
            out.append(Headline(str(it.get("headline", ""))[:120],
                                it.get("source", ""), when, it.get("url", "")))
        return out
    except Exception:
        return []


def headlines(asset_id: str, api_key: str | None = None, limit: int = 5) -> list[Headline]:
    # A股优先用中文快讯
    if asset_id == "a_share":
        raw = data.ak_global_news(limit)
        if raw:
            return [Headline(t, s, w, u) for (t, s, w, u) in raw]
    return _finnhub_news(_FINNHUB_CAT.get(asset_id, "general"), api_key, limit)
