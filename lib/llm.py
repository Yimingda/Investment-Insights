"""DeepSeek 统一调用层 —— 全项目唯一的 LLM 出口（OpenAI 兼容端点）。

- 默认模型 deepseek-v4-flash（secrets/环境变量 DEEPSEEK_MODEL 可覆盖为 deepseek-v4-pro）。
- chat()：可选 JSON 模式。DeepSeek 只保证合法 JSON（json_object）、不保证严格 schema，
  且官方自认偶发返回空 content —— 故这里内嵌 schema 提示 + 稳健解析（围栏/截断/裸引号
  修复，沿用原 intel 的管线）+ required 校验 + 自动重试一次。
- 花费按 usage 的缓存命中/未命中分档计价（DeepSeek 上下文缓存自动生效，无需显式标记），
  并按日落盘 .spend_history.json，供「💰 API花费」页画趋势（本地账本口径）。
  注：官方高峰时段（北京 9-12 / 14-18）2 倍计价政策生效后，账本在高峰时段会低估一半。
"""
from __future__ import annotations

import json
import os
import threading
from datetime import date

BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"

# $/1M token：(输入·缓存命中, 输入·缓存未命中, 输出)
PRICE = {"deepseek-v4-flash": (0.0028, 0.14, 0.28),
         "deepseek-v4-pro": (0.003625, 0.435, 0.87)}

_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HISTORY = os.path.join(_DIR, ".spend_history.json")
_HLOCK = threading.Lock()
_KEEP_DAYS = 120          # 账本保留天数

LAST_FAIL = ""            # 诊断：最近一次 chat 失败原因


def _secret(name: str, default=None):
    try:
        import streamlit as st
        v = st.secrets.get(name, None)
        if v:
            return v
    except Exception:
        pass
    return os.environ.get(name, default)


def deepseek_key() -> str | None:
    k = _secret("DEEPSEEK_API_KEY")
    if k and isinstance(k, str) and k.startswith("sk-") and "xxxx" not in k:
        return k
    return None


def model_name(override: str | None = None) -> str:
    m = override or _secret("DEEPSEEK_MODEL") or DEFAULT_MODEL
    return m if str(m) in PRICE else DEFAULT_MODEL


def cost(mdl: str, usage) -> float:
    """按缓存命中/未命中分档的真实花费。无分档字段时按全未命中保守计。"""
    hit_p, miss_p, out_p = PRICE.get(mdl, PRICE[DEFAULT_MODEL])
    try:
        hit = getattr(usage, "prompt_cache_hit_tokens", None)
        miss = getattr(usage, "prompt_cache_miss_tokens", None)
        if hit is None or miss is None:
            hit, miss = 0, getattr(usage, "prompt_tokens", 0) or 0
        out = getattr(usage, "completion_tokens", 0) or 0
        return (hit * hit_p + miss * miss_p + out * out_p) / 1e6
    except Exception:
        return 0.0


# ── 本地花费账本（供花费页画趋势；与 intel/radar 的预算账本互不干扰）──
def record_spend(category: str, usd: float):
    if usd <= 0:
        return
    with _HLOCK:
        try:
            with open(_HISTORY, encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                d = {}
        except Exception:
            d = {}
        today = date.today().isoformat()
        day = d.setdefault(today, {})
        day[category] = round(day.get(category, 0.0) + usd, 6)
        if len(d) > _KEEP_DAYS:
            for k in sorted(d)[:len(d) - _KEEP_DAYS]:
                d.pop(k, None)
        try:
            with open(_HISTORY, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
        except Exception:
            pass


def spend_history() -> dict:
    """{日期: {用途: usd}}；无账本返回 {}。"""
    try:
        with open(_HISTORY, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


# ── 稳健 JSON 解析（迁自 intel.py，历经实测打磨）─────────────
def _close_brackets(s: str) -> str:
    """自动补全未闭合的引号/括号（模型偶发 JSON 尾部没写完）。"""
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


def parse_json(txt: str) -> dict | None:
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


def _required_ok(d: dict, schema: dict) -> bool:
    """轻量校验：顶层 required 字段齐全即通过（DeepSeek 无严格 json_schema 模式）。"""
    return all(k in d for k in (schema.get("required") or []))


# ── 对外主接口 ───────────────────────────────────────────────
def chat(prompt: str, *, system: str | None = None, api_key: str | None = None,
         model: str | None = None, max_tokens: int = 2000,
         schema: dict | None = None, category: str = "其他"):
    """单轮调用。返回 (结果, 实际花费USD)。

    - schema=None → 结果为纯文本 str（空/失败为 None）；
    - schema 给定 → JSON 模式，结果为 dict（解析或 required 校验失败自动重试 1 次）；
    - key 无效 → 结果为 "__AUTH__"（与原 intel 协议一致）。
    失败原因写入模块级 LAST_FAIL 供诊断。
    """
    global LAST_FAIL
    key = api_key or deepseek_key()
    if not key:
        LAST_FAIL = "no_key"
        return None, 0.0
    try:
        from openai import OpenAI
    except Exception:
        LAST_FAIL = "no_openai_sdk"
        return None, 0.0

    mdl = model_name(model)
    user = prompt
    if schema is not None:
        # json_object 模式要求 prompt 含 "json"；内嵌 schema 让结构尽量对齐
        user += ("\n\n请只输出一个 JSON 对象（不要输出任何其它文字），"
                 "字段结构必须符合以下 JSON Schema：\n"
                 + json.dumps(schema, ensure_ascii=False))
    messages = ([{"role": "system", "content": system}] if system else []) \
        + [{"role": "user", "content": user}]

    client = OpenAI(api_key=key, base_url=BASE_URL)
    total = 0.0
    LAST_FAIL = ""
    attempts = 2 if schema is not None else 1   # JSON 偶发空/坏 → 免费重试一次
    for attempt in range(attempts):
        try:
            kw = {"response_format": {"type": "json_object"}} if schema is not None else {}
            resp = client.chat.completions.create(
                model=mdl, max_tokens=max_tokens, messages=messages, **kw)
        except Exception as e:
            if type(e).__name__ == "AuthenticationError":
                LAST_FAIL = "auth"
                return "__AUTH__", total
            LAST_FAIL = f"exception:{type(e).__name__}:{str(e)[:180]}"
            return None, total
        c = cost(mdl, resp.usage)
        total += c
        record_spend(category, c)
        txt = (resp.choices[0].message.content or "").strip() if resp.choices else ""
        if schema is None:
            if txt:
                return txt, total
            LAST_FAIL = "empty_content"
            return None, total
        d = parse_json(txt)
        if d and _required_ok(d, schema):
            return d, total
        LAST_FAIL = f"bad_json(attempt {attempt + 1}, len={len(txt)})"
    return None, total
