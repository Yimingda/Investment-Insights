"""个股深度情报 —— 决策日历 / 最新财报分析 / 半年大事 / 行业政策累计。

- 内容型数据由 Claude + 联网搜索生成（手动按钮触发），结果存盘 .intel.json 复用。
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
_PATH = os.path.join(_DIR, ".intel.json")
_LEDGER = os.path.join(_DIR, ".intel_ledger.json")
_LOCK = threading.Lock()

EST_STOCK = 0.40     # 单只个股情报（日历+财报+大事）粗估（实测校准：3次检索+长上下文）
EST_POLICY = 0.30    # 单个行业政策粗估
_PRICE = {"claude-opus-4-8": (5.0, 25.0), "claude-sonnet-4-6": (3.0, 15.0),
          "claude-haiku-4-5": (1.0, 5.0)}
_SEARCH_FEE = 0.02   # 联网检索附加费粗估/次生成

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


def _cost(model: str, usage) -> float:
    pin, pout = _PRICE.get(model, (5.0, 25.0))
    try:
        return (usage.input_tokens * pin + usage.output_tokens * pout) / 1e6
    except Exception:
        return 0.0


def _dump_debug(txt: str | None):
    """解析失败时把模型原文落盘，便于诊断（覆盖式，只留最近一次）。"""
    try:
        with open(os.path.join(_DIR, ".intel_debug_last.txt"), "w", encoding="utf-8") as f:
            f.write(txt or "(空)")
    except Exception:
        pass


# ── 结果持久化 ───────────────────────────────────────────────
def _load_all() -> dict:
    try:
        with open(_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_all(d: dict):
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
        d = _load_all()
        d.setdefault(kind, {})[key] = val
        _save_all(d)


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


# ── Claude 联网生成 ─────────────────────────────────────────
def _model():
    try:
        import streamlit as st
        m = st.secrets.get("ANTHROPIC_MODEL", None)
    except Exception:
        m = None
    m = m or os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-6"
    # adaptive thinking / web_search_20260209 需 4.6+ 家族；haiku 等旧模型必 400 → 回退 sonnet
    ok = str(m).startswith(("claude-sonnet-4-6", "claude-opus-4-6", "claude-opus-4-7",
                            "claude-opus-4-8", "claude-fable"))
    return m if ok else "claude-sonnet-4-6"


def _call_web(prompt: str, api_key: str, max_tokens: int = 6000,
              max_searches: int = 3) -> tuple[str | None, float]:
    """带 web_search 的单次任务调用（pause_turn 循环）。返回 (文本, 实际花费)。

    成本护栏（实测教训：无限制搜索一次能烧 $1.8+）：
      - max_uses 硬限制检索次数；
      - pause_turn 最多续 2 次（每次续都重发全部上下文，输入 token 很贵）；
      - stop_reason=max_tokens 视为失败（输出被截断，JSON 不完整）。"""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    tools = [{"type": "web_search_20260209", "name": "web_search",
              "max_uses": max_searches}]
    mdl = _model()
    actual = _SEARCH_FEE * max_searches
    messages = [{"role": "user", "content": prompt}]
    # 不向外抛异常：中途失败也要把已产生的 actual 带回去结算（否则账本漏记真实花费）
    try:
        resp = client.messages.create(model=mdl, max_tokens=max_tokens,
                                      thinking={"type": "adaptive"},
                                      tools=tools, messages=messages)
        actual += _cost(mdl, resp.usage)
        for _ in range(2):
            if resp.stop_reason != "pause_turn":
                break
            messages.append({"role": "assistant", "content": resp.content})
            resp = client.messages.create(model=mdl, max_tokens=max_tokens,
                                          thinking={"type": "adaptive"},
                                          tools=tools, messages=messages)
            actual += _cost(mdl, resp.usage)
    except anthropic.AuthenticationError:
        return "__AUTH__", actual
    except Exception:
        return None, actual
    if resp.stop_reason == "max_tokens":      # 截断 → JSON 必坏，直接判失败
        return None, actual
    txt = "".join(getattr(b, "text", "") for b in resp.content
                  if getattr(b, "type", None) == "text").strip()
    return (txt or None), actual


def _close_brackets(s: str) -> str:
    """自动补全未闭合的引号/括号（模型偶发 end_turn 时 JSON 尾部没写完）。"""
    stack, instr, escp = [], False, False
    for ch in s:
        if instr:
            if escp:
                escp = False
            elif ch == "\\":
                escp = True
            elif ch == '"':
                instr = False
        else:
            if ch == '"':
                instr = True
            elif ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if stack:
                    stack.pop()
    if instr:
        s += '"'
    s = s.rstrip().rstrip(",")          # 尾逗号会让补全后的 JSON 非法
    for ch in reversed(stack):
        s += "}" if ch == "{" else "]"
    return s


def _escape_inner_quotes(s: str) -> str:
    """转义字符串值内部未转义的英文双引号（实测：模型写出 `央行"双降"落地` 之类）。

    判定：串内遇到 `"` 时看其后第一个非空白字符——是 , : } ] 或结尾 → 真正的收尾引号；
    否则视为内容引号，转义为 \\"。"""
    out, instr, escp, n = [], False, False, len(s)
    for idx, ch in enumerate(s):
        if not instr:
            if ch == '"':
                instr = True
            out.append(ch)
            continue
        if escp:
            out.append(ch)
            escp = False
            continue
        if ch == "\\":
            out.append(ch)
            escp = True
            continue
        if ch == '"':
            k = idx + 1
            while k < n and s[k] in " \t\r\n":
                k += 1
            if k >= n or s[k] in ",:}]":
                instr = False
                out.append(ch)
            else:
                out.append('\\"')
        else:
            out.append(ch)
    return "".join(out)


def _parse_json(txt: str) -> dict | None:
    """从模型输出里稳健地抠出 JSON（容忍围栏/前后缀/尾部截断/串内裸引号）。"""
    if not txt:
        return None
    s = txt.strip()
    if "```" in s:
        for seg in s.split("```"):
            seg = seg.strip()
            if seg.startswith("json"):
                seg = seg[4:].strip()
            if seg.startswith("{"):
                s = seg
                break
    i = s.find("{")
    if i < 0:
        return None
    s = s[i:]
    j = s.rfind("}")
    cands = ([s[:j + 1]] if j > 0 else []) + [_close_brackets(s)]
    if j > 0:
        cands.append(_close_brackets(s[:j + 1]))
    for c in cands:
        for attempt in (c, _escape_inner_quotes(c)):
            try:
                d = json.loads(attempt)
                if isinstance(d, dict):
                    return d
            except Exception:
                continue
    return None


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
    today = date.today().isoformat()
    prompt = f"""请联网搜索 A 股上市公司「{name}（{code}）」的最新信息（今天是 {today}），完成三项任务后，只输出一个 JSON（中文内容，不要输出 JSON 以外的任何文字）：

1. calendar：未来 1-6 个月内影响“加仓/减仓/持有”决策的关键事件（3-6 条）：财报披露、分红除权、股东大会、限售解禁、重要产品/订单/行业节点等。确切日期填 date(YYYY-MM-DD)，不确定的 date 填 ""、只填 when（如"8月下旬"）。
2. earnings：最新一期已披露财报（写明哪一期）的分析：营收与净利同比、关键利润率变化、超/低于预期、2-4 条核心亮点、2-3 条风险、一句话结论 verdict（利多/中性/利空 开头）。
3. events：过去 6 个月对股价有实际影响的大事（5-8 条，按时间倒序）：公告、订单、政策冲击、管理层/股权变动等；impact 用 "+"（利多）/"-"（利空）/"0"（中性）。

严格按此结构输出：
{{"calendar":[{{"date":"YYYY-MM-DD或空","when":"显示用时间","event":"事件","why":"为何影响决策(≤40字)"}}],
"earnings":{{"period":"如2026年一季报","summary":"营收/净利同比与利润率(≤80字)","beat":"超预期/符合/低于预期","highlights":["亮点"],"risks":["风险"],"verdict":"利多/中性/利空：一句话结论"}},
"events":[{{"date":"YYYY-MM-DD或YYYY-MM","event":"事件(≤40字)","impact":"+/-/0","note":"影响(≤30字)"}}]}}
所有信息须来自真实检索结果，不确定就不写，禁止编造日期。
【重要】最多检索 3 次；检索后直接输出上述 JSON，不要输出任何检索过程、分析说明等 JSON 以外的文字；
字符串值内部禁止使用英文双引号，需要引用时用「」。"""
    try:
        txt, actual = _call_web(prompt, api_key)
        if txt == "__AUTH__":
            return "__AUTH__"
        d = _parse_json(txt)
        if not d:
            _dump_debug(txt)
            return None
        rec = {"generated_at": time.time(),
               "calendar": [x for x in d.get("calendar", []) if isinstance(x, dict) and x.get("event")][:8],
               "earnings": d.get("earnings") if isinstance(d.get("earnings"), dict) else None,
               "events": [x for x in d.get("events", []) if isinstance(x, dict) and x.get("event")][:10]}
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
    today = date.today().isoformat()
    prompt = f"""请联网搜索中国「{industry}」行业近 12 个月（今天是 {today}）出台或持续生效的重要政策/监管动向，对 A 股该行业股价有实际影响的（6-10 条，按时间倒序）。只输出一个 JSON，不要其它文字：
{{"items":[{{"date":"YYYY-MM","policy":"政策/文件/动向(≤40字)","direction":"利多/利空/中性","impact":"对行业股价的影响机制(≤40字)"}}]}}
所有条目须来自真实检索结果，不确定就不写，禁止编造。
【重要】最多检索 3 次；检索后直接输出上述 JSON，不要输出任何检索过程、分析说明等 JSON 以外的文字；
字符串值内部禁止使用英文双引号，需要引用时用「」。"""
    try:
        txt, actual = _call_web(prompt, api_key, max_tokens=5000)
        if txt == "__AUTH__":
            return "__AUTH__"
        d = _parse_json(txt)
        if not d:
            _dump_debug(txt)
            return None
        rec = {"generated_at": time.time(),
               "items": [x for x in d.get("items", []) if isinstance(x, dict) and x.get("policy")][:12]}
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
