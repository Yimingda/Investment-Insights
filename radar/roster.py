"""追踪名单持久化 —— 用户在"管理人员"页的选择(增减/自定义)存到本地。"""
from __future__ import annotations

import json
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".roster.json")


def load(default_active: list[str]) -> tuple[list[str], list[dict]]:
    """返回 (追踪的人物名 list, 自定义人物 dict list)；无文件→默认全部、无自定义。"""
    try:
        with open(_PATH, encoding="utf-8") as f:
            d = json.load(f)
        active = d.get("active")
        custom = d.get("custom") or []
        return (list(active) if active is not None else list(default_active),
                [c for c in custom if isinstance(c, dict) and c.get("name") and c.get("en")])
    except Exception:
        return list(default_active), []


def save(active: list[str], custom: list[dict]) -> bool:
    try:
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump({"active": list(active), "custom": list(custom)}, f, ensure_ascii=False)
        return True
    except Exception:
        return False
