"""每日 API 花费保护 —— 文件账本 + 原子预留/结算，超额自动暂停付费调用。

只保护付费调用：AI 摘要 / AI 精读(含联网检索) / twitterapi.io 推文。
账本按本地日期自动归零；线程安全(warm 用线程池并发摘要/推文)。

2026-08 起模型可能是 DeepSeek（便宜约 20 倍）：EST_* 常量按 Claude 口径给，
调用前用 est(base, model) 按模型缩放预留额，真实花费仍按 token 结算。
"""
from __future__ import annotations

import json
import os
import threading
from datetime import date

_LOCK = threading.Lock()
_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".spend_ledger.json")
_CAP = 0.20  # 每日上限(USD)，由 app 启动时 set_cap() 覆盖

# 单次调用的成本估算(USD)，用于预留；Claude 之后按真实 token 结算
EST_SUMMARY = 0.004       # Sonnet 短摘要实测约 $0.003/条
EST_DEEP = 0.045          # 含联网检索的粗估上限
EST_TWEET = 0.003
WEB_SEARCH_FEE = 0.02     # 精读每次联网检索的粗略附加(token 用量统计不含)

# 模型价格 $/1M token (input, output)
_PRICE = {
    "claude-opus-4-8": (5.0, 25.0), "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0), "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-5": (3.0, 15.0),  # intro $2/$10 到 2026-08-31,按目录价保守预留
    "claude-haiku-4-5": (1.0, 5.0),
    "deepseek-v4-flash": (0.14, 0.28),   # 约 Sonnet 的 1/20（且无 Batch 五折可用）
}
_DS_EST_SCALE = 0.05     # DeepSeek 路径的预留额缩放系数


def est(base: float, model: str | None = None) -> float:
    """按模型缩放预留额：claude* 用原值，DeepSeek 等按 _DS_EST_SCALE 缩小。"""
    if model and not str(model).startswith("claude"):
        return round(base * _DS_EST_SCALE, 5)
    return base


def set_cap(v: float):
    global _CAP
    try:
        _CAP = max(0.0, float(v))
    except Exception:
        pass


def cap() -> float:
    return _CAP


def _load() -> dict:
    try:
        with open(_PATH, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    if d.get("date") != date.today().isoformat():
        d = {"date": date.today().isoformat(), "spent": 0.0}
    return d


def _save(d: dict):
    try:
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        pass


def spent_today() -> float:
    with _LOCK:
        return float(_load().get("spent", 0.0))


def remaining() -> float:
    return max(0.0, _CAP - spent_today())


def reserve(est: float) -> bool:
    """原子预留 est：今日花费 + est 不超上限则记账并返回 True，否则 False。"""
    with _LOCK:
        d = _load()
        if d.get("spent", 0.0) + est > _CAP:
            _save(d)            # 可能只是刷新了日期
            return False
        d["spent"] = round(d.get("spent", 0.0) + est, 6)
        _save(d)
        return True


def settle(est: float, actual: float):
    """用真实成本替换之前预留的 est（actual<est 即退款）。"""
    with _LOCK:
        d = _load()
        d["spent"] = round(max(0.0, d.get("spent", 0.0) - est + max(0.0, actual)), 6)
        _save(d)


def claude_cost(model: str, usage) -> float:
    """按 token 计价（名字沿用历史，现在同时给 DeepSeek 记账）。"""
    pin, pout = _PRICE.get(model, (5.0, 25.0) if str(model).startswith("claude") else (0.14, 0.28))
    it = getattr(usage, "input_tokens", 0) or 0
    ot = getattr(usage, "output_tokens", 0) or 0
    return (it * pin + ot * pout) / 1e6
