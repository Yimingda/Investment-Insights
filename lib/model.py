"""统一数据模型 —— 所有品种模块都产出一个 Snapshot，由共享渲染器消费。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── 展示用的小结构 ───────────────────────────────────────────
@dataclass
class Indicator:
    """指标表中的一行：名称 + 数值 + 状态徽章。"""
    name: str
    value: str
    badge_text: str
    badge_cls: str  # badge-up / badge-dn / badge-warn / badge-neu


@dataclass
class Strategy:
    """策略 Tab：标题 + Markdown 正文。"""
    title: str
    body_md: str


@dataclass
class Related:
    """相关资产监控的一行。"""
    name: str
    value: str   # 已格式化好的显示字符串
    change: str  # 已格式化好的涨跌字符串
    up: bool


@dataclass
class KPI:
    label: str
    value: str
    sub: str = ""


@dataclass
class Alert:
    cls: str   # alert-up / alert-warn / alert-dn
    text: str


@dataclass
class Snapshot:
    """一个品种在某一时刻的完整快照，喂给统一 Dashboard 渲染器。"""
    # 价格
    price: float
    price_fmt: str               # 已格式化的价格（含货币符号/小数位）
    history: list[float]
    dates: list[str]
    change: float
    change_pct: float

    # 评分
    score: int
    score_label: str
    score_color: str

    # 面板内容
    kpis: list[KPI]
    alerts: list[Alert]
    indicators: list[Indicator]
    strategies: list[Strategy]
    related: list[Related]

    # 走势图参考线（如 MA200）
    ma_ref: Optional[float] = None
    ma_label: str = ""

    # 品种专属卡片：(标题, 内部 HTML)，渲染在底部行
    extra_cards: list[tuple[str, str]] = field(default_factory=list)

    # 数据源状态
    data_live: bool = False
    source_note: str = ""

    # AI 分析所需的结构化上下文（喂给 Claude / 规则引擎）
    ai_facts: dict = field(default_factory=dict)


# ── 评分 → 标签/颜色（全品种共享）────────────────────────────
def score_label(score: int) -> tuple[str, str]:
    if score >= 65:
        return "积极看多", "#3dba6a"
    if score >= 50:
        return "温和看多", "#3dba6a"
    if score >= 40:
        return "中性观望", "#e08030"
    if score >= 30:
        return "偏空谨慎", "#e08030"
    return "明显看空", "#e05555"


def clamp_score(s: float) -> int:
    return max(5, min(95, round(s)))
