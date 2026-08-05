"""DeepSeek 客户端 + 客户端侧 web_search / web_fetch 工具循环（Anthropic 的替身）。

为什么存在：面板原本用 Anthropic 的**服务端** web_search / web_fetch —— 检索循环
由 Anthropic 跑完再把结果给我们。DeepSeek 的接口与 OpenAI 兼容、支持 function
calling，但**没有**内置检索，所以循环得我们自己跑：

    模型请求 web_search(query) → 我们调 Tavily → 把结果回灌 → 重复
    （最多 max_searches 次）→ 模型输出最终答案。

路由约定（全项目一致）：模型名以 "claude" 开头 → 走原 Anthropic 路径；
否则 → 走这里。想回滚只需把模型名设回 claude-*，不用改代码。

成本：DeepSeek V4 Flash $0.14/$0.28 per MTok，约为 Sonnet 的 1/20。

密钥（Streamlit st.secrets 优先，其次环境变量；本模块**不读任何 .env 文件**）：
  DEEPSEEK_API_KEY   必填（https://platform.deepseek.com）
  DEEPSEEK_BASE_URL  可选，默认 https://api.deepseek.com
  TAVILY_API_KEY     可选；缺失时调用仍能跑，只是无法联网 —— 模型只能用训练知识，
                     财务/政策数据可能滞后（提示词里会告知模型这一点）。
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date

import requests

DEFAULT_MODEL = "deepseek-v4-flash"

# $/1M token (input, output)。DeepSeek 没有 Batches API（无五折），但单价便宜约 20 倍。
PRICE = {
    "deepseek-v4-flash": (0.14, 0.28),
}
_PRICE_FALLBACK = (0.14, 0.28)

# V4 Flash 默认思考，且 reasoning_content 计入 max_tokens —— 预算给小了(4k)会被
# 思维链吃光、正文空返回。每轮至少给这么多余量。
_MIN_BUDGET = 8000
# 上限：调用方沿用的是 Anthropic 口径的 max_tokens(16000/12000，因为服务端检索编排
# 也算输出 token)；DeepSeek 的检索在独立轮次里，单轮不需要那么大，且超过模型上限会
# 直接 400。夹到 8192(可用 DEEPSEEK_MAX_TOKENS 调大)。
_MAX_BUDGET_DEFAULT = 8192

_HTTP_TIMEOUT = 300

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """DeepSeek 调用失败（HTTP/协议层）。"""


class LLMAuthError(LLMError):
    """密钥无效/被拒（401/403）—— 调用方一般映射成 "__AUTH__"。"""


# ── 配置读取（st.secrets → 环境变量；绝不读 .env）──────────────
def secret(name: str, default=None):
    try:
        import streamlit as st
        v = st.secrets.get(name)
        if v:
            return v
    except Exception:
        pass
    return os.environ.get(name, default)


def base_url() -> str:
    return str(secret("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")


def is_claude(model: str | None) -> bool:
    """模型路由的唯一判据：claude* → Anthropic 路径，其余 → DeepSeek 路径。"""
    return str(model or "").startswith("claude")


def configured_model(default: str = DEFAULT_MODEL) -> str:
    """全局模型名。沿用旧的 ANTHROPIC_MODEL 作为覆盖键（老配置不用改），
    另外支持更中性的 LLM_MODEL。设成 claude-* 即回滚到 Anthropic。"""
    return str(secret("LLM_MODEL") or secret("ANTHROPIC_MODEL") or default)


def _clean(k) -> str:
    if not isinstance(k, str):
        return ""
    k = k.strip()
    return "" if (not k or "xxxx" in k) else k


def anthropic_key() -> str:
    k = _clean(secret("ANTHROPIC_API_KEY"))
    return k if k.startswith("sk-ant-") else ""


def deepseek_key() -> str:
    return _clean(secret("DEEPSEEK_API_KEY"))


def api_key_for(model: str | None = None) -> str:
    """按路由返回当前该用的 key（Anthropic 或 DeepSeek）；未配置→""。"""
    m = model or configured_model()
    return anthropic_key() if is_claude(m) else deepseek_key()


def tavily_key() -> str:
    return _clean(secret("TAVILY_API_KEY"))


# ── 用量与成本 ────────────────────────────────────────────────
class Usage:
    """与 anthropic 的 usage 对象字段兼容，便于沿用各处的 cost() 记账。"""

    __slots__ = ("input_tokens", "output_tokens",
                 "cache_creation_input_tokens", "cache_read_input_tokens")

    def __init__(self, input_tokens: int = 0, output_tokens: int = 0):
        self.input_tokens = int(input_tokens)
        self.output_tokens = int(output_tokens)
        self.cache_creation_input_tokens = 0
        self.cache_read_input_tokens = 0

    def add(self, d) -> None:
        if not isinstance(d, dict):
            return
        self.input_tokens += int(d.get("prompt_tokens") or 0)
        self.output_tokens += int(d.get("completion_tokens") or 0)

    def __repr__(self):
        return f"Usage(in={self.input_tokens}, out={self.output_tokens})"


def cost(model: str, usage) -> float:
    """USD。仅用于 DeepSeek 路径；Claude 路径各模块有自己的（含缓存折扣）算法。"""
    pin, pout = PRICE.get(str(model), _PRICE_FALLBACK)
    try:
        it = getattr(usage, "input_tokens", 0) or 0
        ot = getattr(usage, "output_tokens", 0) or 0
        return (it * pin + ot * pout) / 1e6
    except Exception:
        return 0.0


# ── 客户端侧联网工具（Tavily）────────────────────────────────
_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "搜索互联网获取最新信息（财报、公告、政策、新闻、行情）。"
                       "Search the web for current information.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "搜索关键词 / search query"}},
            "required": ["query"],
        },
    },
}

_FETCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_fetch",
        "description": "抓取指定 URL 的正文内容（读原文用）。若抓取失败请改用 web_search。",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "要抓取的网页地址"}},
            "required": ["url"],
        },
    },
}

_NO_SEARCH_NOTE = ("搜索不可用：未配置 TAVILY_API_KEY。请基于已有知识回答，"
                   "并说明数据可能滞后。")


def _tavily_search(query: str, max_results: int = 6) -> str:
    """一次 Tavily 检索 → 回灌给模型的纯文本结果块。"""
    if not tavily_key():
        return _NO_SEARCH_NOTE
    if not query:
        return "(空查询)"
    try:
        r = requests.post("https://api.tavily.com/search",
                          json={"api_key": tavily_key(), "query": query,
                                "max_results": max_results, "search_depth": "basic"},
                          timeout=30)
        r.raise_for_status()
        results = (r.json() or {}).get("results") or []
    except Exception as exc:
        return f"搜索失败: {str(exc)[:120]}。请基于已有知识继续。"
    if not results:
        return "(无搜索结果)"
    return "\n\n".join(
        f"[{it.get('title', '')}] {it.get('url', '')}\n{str(it.get('content', ''))[:800]}"
        for it in results)


def _tavily_extract(url: str) -> str:
    """抓取单篇原文（Tavily Extract）。失败时回一句提示，让模型改走搜索。"""
    if not tavily_key():
        return _NO_SEARCH_NOTE
    if not url:
        return "(空链接)"
    try:
        r = requests.post("https://api.tavily.com/extract",
                          json={"api_key": tavily_key(), "urls": [url]}, timeout=45)
        r.raise_for_status()
        j = r.json() or {}
        for it in (j.get("results") or []):
            body = str(it.get("raw_content") or "").strip()
            if body:
                return f"[{it.get('url', url)}]\n{body[:12000]}"
        return "抓取失败（可能是跳转/付费墙）。请改用 web_search 按标题搜索原文。"
    except Exception as exc:
        return f"抓取失败: {str(exc)[:120]}。请改用 web_search 按标题搜索原文。"


# ── JSON 抽取 ────────────────────────────────────────────────
def extract_json(text: str) -> dict | None:
    """从模型输出里抠出第一个 JSON 对象（容忍代码围栏与前后缀）。"""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    raw = fenced.group(1) if fenced else None
    if raw is None:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            raw = text[start:end + 1]
    if raw is None:
        return None
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else None
    except json.JSONDecodeError:
        return None


def _schema_note(schema: dict) -> str:
    """DeepSeek 没有 Anthropic 的结构化输出(json_schema)保证 —— 把 schema 写进
    提示词里，配合调用方原有的容错解析。"""
    return ("\n\n只输出一个 JSON 对象，且严格符合下面的 JSON Schema；"
            "不要输出 markdown 代码围栏，不要任何解释文字：\n"
            + json.dumps(schema, ensure_ascii=False))


# ── 单轮请求 ─────────────────────────────────────────────────
def _budget(max_tokens: int) -> int:
    try:
        ceiling = int(secret("DEEPSEEK_MAX_TOKENS") or _MAX_BUDGET_DEFAULT)
    except Exception:
        ceiling = _MAX_BUDGET_DEFAULT
    return min(max(int(max_tokens or 0), _MIN_BUDGET), max(ceiling, _MIN_BUDGET))


def _post_chat(model: str, messages: list[dict], tools: list | None,
               max_tokens: int, api_key: str, usage: Usage) -> dict:
    body: dict = {"model": model, "messages": messages,
                  "max_tokens": _budget(max_tokens)}
    if tools:
        body["tools"] = tools
    r = requests.post(f"{base_url()}/chat/completions",
                      headers={"Authorization": f"Bearer {api_key}"},
                      json=body, timeout=_HTTP_TIMEOUT)
    if r.status_code in (401, 403):
        raise LLMAuthError(f"DeepSeek HTTP {r.status_code}: {r.text[:200]}")
    if r.status_code != 200:
        # 402 的响应体是 "Insufficient Balance" —— 保留原文，便于上层识别断粮。
        raise LLMError(f"DeepSeek HTTP {r.status_code}: {r.text[:300]}")
    data = r.json() or {}
    usage.add(data.get("usage"))
    choices = data.get("choices") or []
    if not choices:
        raise LLMError(f"DeepSeek empty choices: {str(data)[:300]}")
    if choices[0].get("finish_reason") == "length":
        # 思维链把预算吃完了 —— 正文可能被截断（调用方的 JSON 解析多半会失败）
        log.warning("DeepSeek hit the token budget (finish_reason=length) — answer may be truncated")
    return choices[0].get("message") or {}


# ── 对外主接口 ───────────────────────────────────────────────
def call_text(model: str, prompt: str, *, system: str | None = None,
              allow_search: bool = False, allow_fetch: bool = False,
              max_tokens: int = 4000, max_searches: int = 2,
              schema: dict | None = None, api_key: str | None = None,
              usage: Usage | None = None) -> tuple[str | None, Usage]:
    """调用 DeepSeek，返回 (最终文本, 用量)。

    allow_search/allow_fetch 打开时跑客户端检索循环（合计最多 max_searches 次工具调用）。
    传入 usage 可在异常时仍拿到已产生的 token 用量（便于账本结算）。
    失败抛 LLMError / LLMAuthError。
    """
    usage = usage if usage is not None else Usage()
    key = api_key or deepseek_key()
    if not key:
        raise LLMAuthError("DEEPSEEK_API_KEY 未配置")

    sys_txt = system or ""
    if allow_search or allow_fetch:
        # 模型没有时钟，"最新一期""近 12 个月"这类要求需要锚点。
        sys_txt = (sys_txt + f"\n（今天是 {date.today().isoformat()}。）").strip()
    if schema:
        prompt = prompt + _schema_note(schema)

    messages: list[dict] = []
    if sys_txt:
        messages.append({"role": "system", "content": sys_txt})
    messages.append({"role": "user", "content": prompt})

    tools = []
    if allow_search:
        tools.append(_SEARCH_TOOL)
    if allow_fetch:
        tools.append(_FETCH_TOOL)

    used = 0
    for _round in range(max_searches + 2):        # 工具轮 + 最后一轮出答案
        active = tools if (tools and used < max_searches) else None
        msg = _post_chat(model, messages, active, max_tokens, key, usage)
        calls = msg.get("tool_calls") or []
        if not calls:
            return (msg.get("content") or "").strip() or None, usage
        messages.append({"role": "assistant", "content": msg.get("content") or "",
                         "tool_calls": calls})
        for c in calls:                            # 本轮每个工具调用都要有 tool 回复
            fn = c.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            used += 1
            if fn.get("name") == "web_fetch":
                out = _tavily_extract(str(args.get("url") or ""))
            else:
                out = _tavily_search(str(args.get("query") or ""))
            messages.append({"role": "tool", "tool_call_id": c.get("id"), "content": out})
    return None, usage      # 检索循环耗尽仍未给出最终答案


def call_json(model: str, prompt: str, **kw) -> tuple[dict | None, Usage]:
    """同 call_text，但把最终文本解析成 dict（解析失败返回 None）。"""
    txt, usage = call_text(model, prompt, **kw)
    return extract_json(txt or ""), usage
