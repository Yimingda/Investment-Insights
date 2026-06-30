"""本地数据快照持久化 —— 抓取结果存盘，开页默认读本地数据。"""
from __future__ import annotations

import json
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".data_snapshot.json")


def load() -> tuple[float, dict]:
    """返回 (抓取时间戳 epoch, 数据缓存 dict)；无快照→(0, {})。"""
    try:
        with open(_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return float(d.get("fetched_at", 0) or 0), dict(d.get("data") or {})
    except Exception:
        return 0.0, {}


def save(fetched_at: float, data: dict) -> bool:
    try:
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump({"fetched_at": fetched_at, "data": data or {}},
                      f, ensure_ascii=False)
        return True
    except Exception:
        return False
