"""Anthropic API 花费监控 —— 调用 Cost Admin API 拉取真实花费。

接口：GET https://api.anthropic.com/v1/organizations/cost_report
  - 需 Admin API key（sk-ant-admin...），普通 key 无效；
  - 按天返回 USD（金额为"分"的十进制字符串，需 /100）；
  - group_by=description 时结果含解析出的 model 字段。
无 key/失败一律返回 None，由 UI 改用示例数据 + 配置指引。
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import streamlit as st

_COST_URL = "https://api.anthropic.com/v1/organizations/cost_report"


def is_admin_key(key) -> bool:
    return bool(key and isinstance(key, str) and key.startswith("sk-ant-admin"))


def _to_usd(amount) -> float:
    """金额为'分'的十进制字符串 → 美元。"""
    try:
        return float(amount) / 100.0
    except Exception:
        return 0.0


@st.cache_data(ttl=600, show_spinner=False)
def cost_report(admin_key: str, days: int = 30):
    """返回 {daily:[(YYYY-MM-DD, usd)], by_label:{label:usd}, total:usd} 或 None。"""
    if not is_admin_key(admin_key):
        return None
    try:
        import requests
    except Exception:
        return None
    try:
        end = (datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
               + timedelta(days=1))
        start = end - timedelta(days=days + 1)
        headers = {"x-api-key": admin_key, "anthropic-version": "2023-06-01",
                   "User-Agent": "InvestPanel/1.0"}
        daily: dict[str, float] = {}
        by_label: dict[str, float] = {}
        total = 0.0
        page = None
        for _ in range(20):  # 分页上限
            params = {
                "starting_at": start.strftime("%Y-%m-%dT00:00:00Z"),
                "ending_at": end.strftime("%Y-%m-%dT00:00:00Z"),
                "group_by[]": ["description"],
            }
            if page:
                params["page"] = page
            r = requests.get(_COST_URL, params=params, headers=headers, timeout=15)
            r.raise_for_status()
            j = r.json()
            for bucket in j.get("data", []):
                day = (bucket.get("starting_at") or "")[:10]
                for res in bucket.get("results", []):
                    amt = _to_usd(res.get("amount"))
                    if amt == 0:
                        continue
                    label = (res.get("model") or res.get("description")
                             or _ws_label(res.get("workspace_id")) or "其他")
                    daily[day] = daily.get(day, 0.0) + amt
                    by_label[label] = by_label.get(label, 0.0) + amt
                    total += amt
            if j.get("has_more") and j.get("next_page"):
                page = j["next_page"]
                continue
            break
        if total == 0:
            return {"daily": [], "by_label": {}, "total": 0.0}
        return {"daily": sorted(daily.items()), "by_label": by_label, "total": round(total, 2)}
    except Exception:
        return None


def _ws_label(ws_id):
    if ws_id is None:
        return "默认工作区"
    return f"工作区 {str(ws_id)[-6:]}"


def sample_report(days: int = 30):
    """无 key 时的示例数据，仅用于展示页面布局。"""
    today = datetime.now(timezone.utc).date()
    daily = []
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        v = max(0.0, random.uniform(0.4, 3.2) + (1.5 if d.weekday() < 5 else 0))
        daily.append((d.strftime("%Y-%m-%d"), round(v, 2)))
    total = sum(v for _, v in daily)
    by_label = {
        "claude-opus-4-8": round(total * 0.55, 2),
        "claude-sonnet-4-6": round(total * 0.22, 2),
        "claude-haiku-4-5": round(total * 0.08, 2),
        "Web Search Usage": round(total * 0.09, 2),
        "Code Execution Usage": round(total * 0.06, 2),
    }
    return {"daily": daily, "by_label": by_label, "total": round(total, 2)}
