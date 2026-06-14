"""投资日历 —— 各品种需关注的投资大事日历。

数据策略（贴合全局降级哲学）：
  - 主源：Finnhub 财经日历 + 财报日历（需 FINNHUB_API_KEY；免费档可用）。
  - 始终包含：交易所/制度类可规则计算的事件（期权到期OPEX/三巫、CME比特币到期、LPR），
    这类事件财经日历通常不覆盖。
  - 无 key 或 API 失败：降级到规则计算的宏观事件（非农/中国CPI/PMI/两会等）。
对外只暴露 upcoming_for(asset_id, api_key, horizon_days)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import streamlit as st

# 资产 id
GOLD, CRYPTO, US, ASHARE, FOREX = "gold", "crypto", "us_equity", "a_share", "forex"
ALL = (GOLD, CRYPTO, US, ASHARE, FOREX)


@dataclass
class CalendarEvent:
    day: date
    title: str
    importance: int            # 1=低 2=中 3=高
    assets: tuple              # 影响的品种 id
    note: str = ""
    live: bool = False         # True=来自API真实日历, False=规则推算


# ── 日期工具 ─────────────────────────────────────────────────
def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """该月第 n 个 weekday（周一=0…周日=6）。"""
    d = date(year, month, 1)
    first = (weekday - d.weekday()) % 7
    return d + timedelta(days=first + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _months_in(today: date, end: date):
    y, m = today.year, today.month
    while date(y, m, 1) <= end:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


# ── 始终包含：交易所/制度类（规则计算，财经日历不覆盖）──────
def _exchange_events(today: date, end: date) -> list[CalendarEvent]:
    out = []
    for y, m in _months_in(today, end):
        opex = _nth_weekday(y, m, 4, 3)          # 第三个周五
        if m in (3, 6, 9, 12):
            out.append(CalendarEvent(opex, "美股季度期权到期（三巫日）", 3, (US, CRYPTO),
                                     "股指期货/期权同时到期，波动放大"))
        else:
            out.append(CalendarEvent(opex, "美股月度期权到期 (OPEX)", 2, (US,),
                                     "第三个周五，临近常有波动"))
        out.append(CalendarEvent(_last_weekday(y, m, 4), "CME 比特币期货/期权到期", 2, (CRYPTO,),
                                 "每月最后周五结算，注意多空博弈"))
        lpr = date(y, m, 20)
        out.append(CalendarEvent(lpr, "中国 LPR 报价", 3, (ASHARE, FOREX),
                                 "央行贷款市场报价利率，影响A股与人民币"))
    return out


# ── 降级用：规则计算的宏观事件（无 API 时使用）──────────────
def _macro_fallback(today: date, end: date) -> list[CalendarEvent]:
    out = []
    for y, m in _months_in(today, end):
        out.append(CalendarEvent(_nth_weekday(y, m, 4, 1), "美国非农就业 (NFP)", 3,
                                 (GOLD, US, FOREX, CRYPTO), "每月第一个周五，重磅数据"))
        out.append(CalendarEvent(date(y, m, 12), "美国 CPI 通胀数据", 3,
                                 (GOLD, US, FOREX, CRYPTO), "约每月中旬，重磅"))
        out.append(CalendarEvent(date(y, m, 27), "美国 PCE 物价指数", 2, (GOLD, US, FOREX),
                                 "美联储关注的通胀指标，约月末"))
        out.append(CalendarEvent(date(y, m, 9), "中国 CPI / PPI", 2, (ASHARE, FOREX),
                                 "约每月9-10日"))
        out.append(CalendarEvent(date(y, m, 1), "中国制造业 PMI", 2, (ASHARE,),
                                 "国家统计局月末/月初公布"))
    # 少量按年精选大事（近似日期）
    for y in {today.year, end.year}:
        for d0, title, imp, assets, note in [
            (date(y, 3, 5), "中国两会（全国人大开幕）", 3, (ASHARE, FOREX), "政策定调，约3月初"),
            (date(y, 8, 22), "Jackson Hole 全球央行年会", 2, (GOLD, US, FOREX), "约8月下旬"),
        ]:
            out.append(CalendarEvent(d0, title, imp, assets, note))
    return out


# ── 主源：Finnhub 财经日历 + 财报日历 ────────────────────────
_CTY = {"US": ("🇺🇸", (GOLD, US, FOREX, CRYPTO)), "CN": ("🇨🇳", (ASHARE, FOREX)),
        "EU": ("🇪🇺", (FOREX,)), "JP": ("🇯🇵", (FOREX,)), "GB": ("🇬🇧", (FOREX,))}
_KW_CN = [("Interest Rate", "利率决议"), ("Fed", "美联储"), ("FOMC", "FOMC"),
          ("CPI", "CPI通胀"), ("PCE", "PCE物价"), ("PPI", "PPI"), ("GDP", "GDP"),
          ("Nonfarm", "非农就业"), ("Payroll", "非农就业"), ("Unemployment", "失业率"),
          ("PMI", "PMI"), ("Retail Sales", "零售销售"), ("Loan Prime", "LPR")]
_MEGACAPS = {"AAPL": "苹果", "MSFT": "微软", "NVDA": "英伟达", "AMZN": "亚马逊",
             "GOOGL": "谷歌", "META": "Meta", "TSLA": "特斯拉"}


def _zh_title(flag: str, raw: str) -> str:
    for kw, zh in _KW_CN:
        if kw.lower() in raw.lower():
            return f"{flag} {zh}"
    return f"{flag} {raw}"


@st.cache_data(ttl=3600, show_spinner=False)
def _finnhub(today_iso: str, end_iso: str, api_key: str):
    """返回 list[CalendarEvent] 或 None。"""
    if not api_key:
        return None
    try:
        import requests
    except Exception:
        return None
    out = []
    try:
        r = requests.get("https://finnhub.io/api/v1/calendar/economic",
                         params={"token": api_key}, timeout=10)
        r.raise_for_status()
        for e in (r.json().get("economicCalendar") or []):
            cty = _CTY.get((e.get("country") or "").upper())
            if not cty:
                continue
            imp = {"3": 3, "high": 3, "2": 2, "medium": 2}.get(str(e.get("impact", "")).lower())
            if not imp:  # 仅保留中高影响，降噪
                continue
            try:
                d0 = date.fromisoformat((e.get("time") or "")[:10])
            except Exception:
                continue
            flag, assets = cty
            out.append(CalendarEvent(d0, _zh_title(flag, e.get("event", "")), imp, assets,
                                     "财经日历", live=True))
    except Exception:
        pass
    # 财报日历（权重股）
    try:
        r = requests.get("https://finnhub.io/api/v1/calendar/earnings",
                         params={"from": today_iso, "to": end_iso, "token": api_key}, timeout=10)
        r.raise_for_status()
        for e in (r.json().get("earningsCalendar") or []):
            sym = e.get("symbol", "")
            if sym not in _MEGACAPS:
                continue
            try:
                d0 = date.fromisoformat(e.get("date"))
            except Exception:
                continue
            out.append(CalendarEvent(d0, f"📊 {_MEGACAPS[sym]}({sym}) 财报", 3, (US,),
                                     "权重股财报，影响指数", live=True))
    except Exception:
        pass
    return out or None


# ── 对外接口 ─────────────────────────────────────────────────
def upcoming_for(asset_id: str, api_key: str | None = None,
                 horizon_days: int = 45, limit: int = 10) -> list[CalendarEvent]:
    today = date.today()
    end = today + timedelta(days=horizon_days)

    events = _exchange_events(today, end)
    api = _finnhub(today.isoformat(), end.isoformat(), api_key) if api_key else None
    events += api if api else _macro_fallback(today, end)

    # 过滤：与本品种相关 + 未来窗口内
    sel = [e for e in events if asset_id in e.assets and today <= e.day <= end]
    # 去重（同日同标题）
    seen, uniq = set(), []
    for e in sorted(sel, key=lambda x: (x.day, -x.importance)):
        k = (e.day, e.title)
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    return uniq[:limit]


def any_live(api_key: str | None) -> bool:
    """供 UI 标注日历是否来自真实 API。"""
    if not api_key:
        return False
    today = date.today()
    return bool(_finnhub(today.isoformat(), (today + timedelta(days=45)).isoformat(), api_key))
