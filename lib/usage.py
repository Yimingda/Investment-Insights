"""DeepSeek 花费监控 —— 账户余额(官方 API) + 本地调用账本。

DeepSeek 无 Cost Admin API（无法拉账户级别的按日账单），改为两条腿：
  - 余额：GET https://api.deepseek.com/user/balance（普通 API key 即可）；
  - 每日趋势/消耗结构：lib/llm.py 每次调用后落盘的本地账本 .spend_history.json
    （仅统计本部署发起的调用；云端文件系统临时，重启后账本从零开始）。
无 key/失败一律返回 None，由 UI 改用示例数据 + 配置指引。
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import streamlit as st

_BALANCE_URL = "https://api.deepseek.com/user/balance"


def has_key(key) -> bool:
    return bool(key and isinstance(key, str) and key.startswith("sk-"))


@st.cache_data(ttl=600, show_spinner=False)
def balance(api_key: str):
    """返回 {currency,total,granted,topped_up,available} 或 None。"""
    if not has_key(api_key):
        return None
    try:
        import requests
    except Exception:
        return None
    try:
        r = requests.get(_BALANCE_URL, timeout=10,
                         headers={"Authorization": f"Bearer {api_key}",
                                  "User-Agent": "InvestPanel/1.0"})
        r.raise_for_status()
        j = r.json() or {}
        infos = j.get("balance_infos") or []
        if not infos:
            return None
        b = next((x for x in infos if x.get("currency") == "CNY"), infos[0])
        return {"currency": b.get("currency", ""),
                "total": float(b.get("total_balance") or 0),
                "granted": float(b.get("granted_balance") or 0),
                "topped_up": float(b.get("topped_up_balance") or 0),
                "available": bool(j.get("is_available"))}
    except Exception:
        return None


def cost_report(days: int = 30):
    """返回 {daily:[(YYYY-MM-DD, usd)], by_label:{用途:usd}, total:usd} 或 None（无账本）。"""
    from . import llm
    hist = llm.spend_history()
    if not hist:
        return None
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days - 1)).isoformat()
    daily: dict[str, float] = {}
    by_label: dict[str, float] = {}
    total = 0.0
    for day, cats in hist.items():
        if not isinstance(cats, dict) or day < cutoff:
            continue
        for label, v in cats.items():
            try:
                v = float(v)
            except Exception:
                continue
            daily[day] = daily.get(day, 0.0) + v
            by_label[label] = by_label.get(label, 0.0) + v
            total += v
    if total <= 0:
        return None
    return {"daily": sorted(daily.items()), "by_label": by_label, "total": round(total, 4)}


def sample_report(days: int = 30):
    """无账本时的示例数据，仅用于展示页面布局。"""
    today = datetime.now(timezone.utc).date()
    daily = []
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        v = max(0.0, random.uniform(0.005, 0.06) + (0.03 if d.weekday() < 5 else 0))
        daily.append((d.strftime("%Y-%m-%d"), round(v, 3)))
    total = sum(v for _, v in daily)
    by_label = {
        "个股情报": round(total * 0.45, 3),
        "行情分析": round(total * 0.25, 3),
        "人物摘要": round(total * 0.15, 3),
        "人物精读": round(total * 0.10, 3),
        "行业政策": round(total * 0.05, 3),
    }
    return {"daily": daily, "by_label": by_label, "total": round(total, 3)}
