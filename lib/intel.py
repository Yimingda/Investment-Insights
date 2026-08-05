"""个股深度情报 —— 决策日历 / 最新财报分析 / 半年大事 / 行业政策累计。

- 内容型数据由 DeepSeek 生成（手动按钮触发），结果存盘 .intel.json 复用。
  检索材料由 lib/websearch.py 先行抓取（Google News RSS）再拼进 prompt ——
  DeepSeek API 无服务端联网检索，改为「先检索、后生成」两段式。
- 政策按行业归组（12 只 → 9 个行业），同行业共享一份，省生成费用。
- 独立每日预算 INTEL_BUDGET_USD（默认 $1.00），与人物雷达的预算分开记账。
- 财报披露日等有法定窗口的，用 rule_calendar() 免费兜底（不依赖 AI）。
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import date, datetime, timedelta

_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATH = os.path.join(_DIR, ".intel.json")                 # 本地手动生成(gitignore)
_BASE_PATH = os.path.join(_DIR, "data", "intel.json")     # 夜间批量刷新提交进仓库(共享层)
_LEDGER = os.path.join(_DIR, ".intel_ledger.json")
_LOCK = threading.Lock()

EST_STOCK = 0.03     # 单只个股情报粗估（DeepSeek v4-flash，检索走免费 RSS）
EST_POLICY = 0.02    # 单个行业政策粗估

# ── 行业归组（政策共享粒度）─────────────────────────────────
INDUSTRY_OF = {
    "002352": "物流快递", "600036": "银行", "601166": "银行",
    "600050": "运营商/算力", "600941": "运营商/算力",
    "600089": "电力设备/新能源", "600104": "汽车", "601633": "汽车",
    "600276": "医药", "600729": "零售消费", "601336": "保险", "603501": "半导体",
}


def industry_of(code: str) -> str:
    return INDUSTRY_OF.get(str(code).strip(), "其它")


# ── 每日预算（独立于雷达）───────────────────────────────────
def _cap() -> float:
    try:
        import streamlit as st
        v = st.secrets.get("INTEL_BUDGET_USD", None)
    except Exception:
        v = None
    if v is None:
        v = os.environ.get("INTEL_BUDGET_USD")
    try:
        return max(0.0, float(v)) if v is not None else 1.00
    except Exception:
        return 1.00


def _ledger_load() -> dict:
    today = date.today().isoformat()
    try:
        with open(_LEDGER, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("date") == today:
            return d
    except Exception:
        pass
    return {"date": today, "spent": 0.0}


def _ledger_save(d: dict):
    try:
        with open(_LEDGER, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        pass


def spent_today() -> float:
    with _LOCK:
        return float(_ledger_load().get("spent", 0.0))


def budget_cap() -> float:
    return _cap()


def _reserve(est: float) -> bool:
    with _LOCK:
        d = _ledger_load()
        if d["spent"] + est > _cap():
            return False
        d["spent"] += est
        _ledger_save(d)
        return True


def _settle(est: float, actual: float):
    with _LOCK:
        d = _ledger_load()
        d["spent"] = max(0.0, d["spent"] - est + max(0.0, actual))
        _ledger_save(d)


def _dump_debug(txt: str | None):
    """解析失败时把模型原文落盘，便于诊断（覆盖式，只留最近一次）。"""
    try:
        with open(os.path.join(_DIR, ".intel_debug_last.txt"), "w", encoding="utf-8") as f:
            f.write(txt or "(空)")
    except Exception:
        pass


# ── 结果持久化 ───────────────────────────────────────────────
def _load_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _ts(rec) -> float:
    try:
        return float(rec.get("generated_at") or 0)
    except Exception:
        return 0.0


def _load_all() -> dict:
    """合并视图：仓库共享层(data/intel.json，夜间批量提交) + 本地手动生成层，
    同一 key 取 generated_at 较新者。云端重启后共享层仍在 → 情报不丢。
    脏记录(非 dict / generated_at 非法)逐条跳过，绝不让一条脏数据拖垮整页。"""
    base, local = _load_json(_BASE_PATH), _load_json(_PATH)
    out: dict = {}
    for kind in set(list(base.keys()) + list(local.keys())):
        b = base.get(kind) if isinstance(base.get(kind), dict) else {}
        l = local.get(kind) if isinstance(local.get(kind), dict) else {}
        merged = {k: v for k, v in b.items() if isinstance(v, dict)}
        for k, v in l.items():
            if not isinstance(v, dict):
                continue
            if k not in merged or _ts(v) >= _ts(merged[k]):
                merged[k] = v
        out[kind] = merged
    return out


def _save_local(d: dict):
    try:
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except Exception:
        pass


def get_stock(code: str) -> dict | None:
    return _load_all().get("stocks", {}).get(str(code))


def get_policy(industry: str) -> dict | None:
    return _load_all().get("policies", {}).get(industry)


def _put(kind: str, key: str, val: dict):
    with _LOCK:
        d = _load_json(_PATH)          # 只写本地层，不把共享层复制进来
        d.setdefault(kind, {})[key] = val
        _save_local(d)


def age_str(ts: float | None) -> str:
    if not ts:
        return "未生成"
    h = (time.time() - ts) / 3600
    if h < 1:
        return f"{h*60:.0f} 分钟前"
    if h < 48:
        return f"{h:.0f} 小时前"
    return f"{h/24:.0f} 天前"


# ── 规则日历（免费兜底：A股法定披露窗口等）───────────────────
def rule_calendar(code: str, today: date | None = None) -> list[dict]:
    """未来的法定财报披露窗口（中报 8/31 前、三季报 10/31 前、年报+一季报 4/30 前）。"""
    t = today or date.today()
    y = t.year
    wins = [
        (date(y, 1, 1), date(y, 4, 30), "年报 + 一季报披露窗口", "全年业绩与分红方案落地"),
        (date(y, 7, 1), date(y, 8, 31), "半年报披露窗口", "中期业绩证实/证伪基本面，是加减仓关键判断点"),
        (date(y, 10, 1), date(y, 10, 31), "三季报披露窗口", "验证下半年经营趋势"),
        (date(y + 1, 1, 1), date(y + 1, 4, 30), "年报 + 一季报披露窗口", "全年业绩与分红方案落地"),
    ]
    out = []
    for start, end, name, why in wins:
        if end >= t:
            out.append({"date": end.isoformat(), "when": f"{start.month}月~{end.month}月{end.day}日前",
                        "event": name, "why": why, "src": "规则"})
    return out[:3]


# ── DeepSeek 生成（检索材料先行，见 lib/websearch.py）────────
# 输出 schema —— DeepSeek 只保证合法 JSON，结构对齐靠 llm.chat 内嵌提示 + 校验重试

_STOCK_SCHEMA = {
    "type": "object",
    "properties": {
        "calendar": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD，不确定填空串"},
                "when": {"type": "string", "description": "显示用时间，如 8月下旬"},
                "event": {"type": "string"},
                "why": {"type": "string", "description": "为何影响加减仓决策，≤40字"},
            },
            "required": ["date", "when", "event", "why"],
            "additionalProperties": False}},
        "earnings": {"type": "object", "properties": {
            "period": {"type": "string", "description": "如 2026年一季报"},
            "summary": {"type": "string", "description": "营收/净利同比与利润率，≤80字"},
            "beat": {"type": "string", "enum": ["超预期", "符合预期", "低于预期", "存在分歧"]},
            "highlights": {"type": "array", "items": {"type": "string"}},
            "risks": {"type": "array", "items": {"type": "string"}},
            "verdict": {"type": "string", "description": "以 利多/中性/利空 开头的一句话结论"},
        }, "required": ["period", "summary", "beat", "highlights", "risks", "verdict"],
            "additionalProperties": False},
        "events": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD 或 YYYY-MM"},
                "event": {"type": "string", "description": "≤40字"},
                "impact": {"type": "string", "enum": ["+", "-", "0"]},
                "note": {"type": "string", "description": "对股价影响，≤30字"},
            },
            "required": ["date", "event", "impact", "note"],
            "additionalProperties": False}},
    },
    "required": ["calendar", "earnings", "events"],
    "additionalProperties": False,
}

_POLICY_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM"},
                "policy": {"type": "string", "description": "政策/文件/动向，≤40字"},
                "direction": {"type": "string", "enum": ["利多", "利空", "中性"]},
                "impact": {"type": "string", "description": "对行业股价的影响机制，≤40字"},
            },
            "required": ["date", "policy", "direction", "impact"],
            "additionalProperties": False}},
    },
    "required": ["items"],
    "additionalProperties": False,
}
def stock_prompt(code: str, name: str, material: str = "", today: str | None = None) -> str:
    """个股情报生成 prompt（交互与夜间批量共用同一份，保证口径一致）。

    material：websearch.stock_material() 拼好的检索材料（新闻标题+日期）；空则如实降级。"""
    today = today or date.today().isoformat()
    mat = material.strip() or "（本次未取到任何检索材料）"
    return f"""你是严谨的 A 股研究助理。今天是 {today}。以下是关于上市公司「{name}（{code}）」的最新检索材料（新闻标题与日期，可能不全）：

{mat}

请结合上述材料与你已知的可靠公开信息，完成三项任务，只输出一个 JSON（中文内容，不要输出 JSON 以外的任何文字）：

1. calendar：未来 1-6 个月内影响“加仓/减仓/持有”决策的关键事件（3-6 条）：财报披露、分红除权、股东大会、限售解禁、重要产品/订单/行业节点等。确切日期填 date(YYYY-MM-DD)，不确定的 date 填 ""、只填 when（如"8月下旬"）。
2. earnings：最新一期已披露财报（写明哪一期）的分析：营收与净利同比、关键利润率变化、超/低于预期、2-4 条核心亮点、2-3 条风险、一句话结论 verdict（利多/中性/利空 开头）。
3. events：过去 6 个月对股价有实际影响的大事（5-8 条，按时间倒序）：公告、订单、政策冲击、管理层/股权变动等；impact 用 "+"（利多）/"-"（利空）/"0"（中性）。
材料中没有且你不确定的就不写，禁止编造日期与数字。"""


def policy_prompt(industry: str, material: str = "", today: str | None = None) -> str:
    """行业政策生成 prompt（交互与夜间批量共用）。"""
    today = today or date.today().isoformat()
    mat = material.strip() or "（本次未取到任何检索材料）"
    return f"""你是严谨的 A 股研究助理。今天是 {today}。以下是关于中国「{industry}」行业政策/监管动向的最新检索材料（新闻标题与日期，可能不全）：

{mat}

请结合上述材料与你已知的可靠公开信息，整理近 12 个月出台或持续生效、对 A 股该行业股价有实际影响的重要政策/监管动向（6-10 条，按时间倒序）。只输出一个 JSON，不要其它文字：
{{"items":[{{"date":"YYYY-MM","policy":"政策/文件/动向(≤40字)","direction":"利多/利空/中性","impact":"对行业股价的影响机制(≤40字)"}}]}}
材料中没有且你不确定的就不写，禁止编造。"""


def build_stock_rec(d: dict) -> dict:
    """把模型 JSON 清洗成个股情报记录（交互与夜间批量共用）。"""
    return {"generated_at": time.time(),
            "calendar": [x for x in d.get("calendar", []) if isinstance(x, dict) and x.get("event")][:8],
            "earnings": d.get("earnings") if isinstance(d.get("earnings"), dict) else None,
            "events": [x for x in d.get("events", []) if isinstance(x, dict) and x.get("event")][:10]}


def build_policy_rec(d: dict) -> dict:
    """把模型 JSON 清洗成行业政策记录（交互与夜间批量共用）。"""
    return {"generated_at": time.time(),
            "items": [x for x in d.get("items", []) if isinstance(x, dict) and x.get("policy")][:12]}


def gen_stock(code: str, name: str, api_key: str) -> dict | str | None:
    """生成单只个股情报：决策日历 + 最新财报分析 + 近半年大事。
    返回 dict；预算不足返回 "__BUDGET__"；key 无效返回 "__AUTH__"；失败返回 None。"""
    if not api_key:
        return None
    rec0 = get_stock(str(code))
    if rec0 and time.time() - float(rec0.get("generated_at") or 0) < 120:
        return rec0        # 双击/排队重复点击 → 2 分钟内直接回缓存，不重复计费
    if not _reserve(EST_STOCK):
        return "__BUDGET__"
    actual = 0.0
    try:
        from . import llm, websearch
        prompt = stock_prompt(str(code), name, websearch.stock_material(str(code), name))
        d, actual = llm.chat(prompt, api_key=api_key, max_tokens=8000,
                             schema=_STOCK_SCHEMA, category="个股情报")
        if d == "__AUTH__":
            return "__AUTH__"
        if not isinstance(d, dict):
            _dump_debug(f"(生成失败) fail={llm.LAST_FAIL}")
            return None
        rec = build_stock_rec(d)
        _put("stocks", str(code), rec)
        return rec
    except Exception:
        return None
    finally:
        _settle(EST_STOCK, actual)


def gen_policy(industry: str, api_key: str) -> dict | str | None:
    """生成/更新某行业的政策累计清单。返回 dict / "__BUDGET__" / "__AUTH__" / None。"""
    if not api_key:
        return None
    rec0 = get_policy(industry)
    if rec0 and time.time() - float(rec0.get("generated_at") or 0) < 120:
        return rec0        # 双击/排队重复点击 → 2 分钟内直接回缓存，不重复计费
    if not _reserve(EST_POLICY):
        return "__BUDGET__"
    actual = 0.0
    try:
        from . import llm, websearch
        prompt = policy_prompt(industry, websearch.policy_material(industry))
        d, actual = llm.chat(prompt, api_key=api_key, max_tokens=6000,
                             schema=_POLICY_SCHEMA, category="行业政策")
        if d == "__AUTH__":
            return "__AUTH__"
        if not isinstance(d, dict):
            _dump_debug(f"(生成失败) fail={llm.LAST_FAIL}")
            return None
        rec = build_policy_rec(d)
        _put("policies", industry, rec)
        return rec
    except Exception:
        return None
    finally:
        _settle(EST_POLICY, actual)


# ── 未来 N 天事件聚合（仪表盘用）────────────────────────────
def upcoming_events(codes_names: list[tuple[str, str]], days: int = 14) -> list[dict]:
    """合并规则日历 + 已生成的 AI 日历，取未来 N 天内可解析日期的事件。"""
    t = date.today()
    horizon = t + timedelta(days=days)
    out = []
    for code, name in codes_names:
        rows = list(rule_calendar(code, t))
        rec = get_stock(code)
        if rec:
            rows += rec.get("calendar", [])
        for r in rows:
            ds = str(r.get("date") or "")
            try:
                d = datetime.strptime(ds[:10], "%Y-%m-%d").date()
            except Exception:
                continue
            if t <= d <= horizon:
                out.append({"date": d.isoformat(), "code": code, "name": name,
                            "event": r.get("event", ""), "why": r.get("why", ""),
                            "days": (d - t).days})
    # 去重（同股同事件）+ 按日期排序
    seen, ded = set(), []
    for r in sorted(out, key=lambda x: x["date"]):
        k = (r["code"], r["event"])
        if k not in seen:
            seen.add(k)
            ded.append(r)
    return ded
