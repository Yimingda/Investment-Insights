"""数据源 —— 全部免费/可选，缺失一律优雅降级（返回空，不报错）。

  • 新闻/表态/采访  : Google News RSS（免费、无 key、按人名检索最新全球新闻）
  • X(推特) 推文    : twitterapi.io（默认；可在 secrets 配置其它服务的 base/key）
  • 采访/动态概要    : Claude 摘要（有 ANTHROPIC_API_KEY 才用，否则显示原标题）
"""
from __future__ import annotations

import streamlit as st

from . import budget


def secret(name: str, default=None):
    try:
        v = st.secrets.get(name)
        if v:
            return v
    except Exception:
        pass
    import os
    return os.environ.get(name, default)


def _req():
    try:
        import requests
        return requests
    except Exception:
        return None


# ── 新闻：Google News RSS（免费、无 key、按人名检索、限流宽松）──
def fetch_news(query: str, max_records: int = 6, timespan: str = "3d") -> list[dict]:
    """按检索词返回最新新闻 [{title,url,domain,seendate}]，失败→[]。

    用 Google News RSS 搜索（GDELT 限 1 req/5s，无法并发，已弃用）。
    """
    requests = _req()
    if requests is None:
        return []
    try:
        import urllib.parse as _u
        import xml.etree.ElementTree as ET
        url = (f"https://news.google.com/rss/search?q={_u.quote(query)}"
               f"&hl=en-US&gl=US&ceid=US:en")
        r = requests.get(url, timeout=12,
                         headers={"User-Agent": "Mozilla/5.0 (VoicesRadar)"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        out, seen = [], set()
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = item.findtext("link") or ""
            src = (item.findtext("source") or "").strip()
            pub = item.findtext("pubDate") or ""
            if not title or link in seen:
                continue
            seen.add(link)
            if src and title.endswith(f" - {src}"):       # 去掉标题尾部的来源
                title = title[: -len(src) - 3].strip()
            out.append({"title": title, "url": link, "domain": src, "seendate": pub})
            if len(out) >= max_records:
                break
        return out
    except Exception:
        return []


def fmt_seendate(s: str) -> str:
    """RFC822 pubDate → 'MM/DD HH:MM'。"""
    if not s:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).strftime("%m/%d %H:%M")
    except Exception:
        return s[:16]


# ── X 推文（twitterapi.io 默认；可配置其它服务）────────────────
def fetch_tweets(handle: str, api_key: str, limit: int = 5,
                 base: str | None = None) -> list[dict]:
    """返回某用户最新推文 [{text,created_at,url}]，无 key/失败→[]。

    默认对接 twitterapi.io；换其它服务时，把 base 指到对应端点并按需调整
    下方字段映射即可（响应里 tweets / data.tweets 都做了容错）。
    """
    if not api_key or not handle:
        return []
    requests = _req()
    if requests is None:
        return []
    if not budget.reserve(budget.EST_TWEET):     # 每日花费保护
        return []
    spent_ok = False
    try:
        url = base or "https://api.twitterapi.io/twitter/user/last_tweets"
        r = requests.get(url, params={"userName": handle},
                         headers={"X-API-Key": api_key}, timeout=12)
        r.raise_for_status()
        spent_ok = True
        d = r.json() or {}
        tweets = None
        if isinstance(d.get("data"), dict):
            tweets = d["data"].get("tweets")
        tweets = tweets or d.get("tweets") or d.get("results") or []
        import datetime as _dt

        def _txt(tw):
            # text 偶尔返回非字符串(布尔)；取转推/引用里的真实文本，否则跳过
            for k in ("text", "full_text"):
                v = tw.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            for nest, pre in (("retweeted_tweet", "🔁 "), ("quoted_tweet", "❝ ")):
                n = tw.get(nest)
                if isinstance(n, dict) and isinstance(n.get("text"), str) and n["text"].strip():
                    return pre + n["text"].strip()
            return ""

        def _when(s):
            # 返回 (显示串 'MM/DD HH:MM', 排序用 epoch)
            if not isinstance(s, str):
                return "", 0.0
            try:
                d = _dt.datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")
                return d.strftime("%m/%d %H:%M"), d.timestamp()
            except Exception:
                return s[:16], 0.0

        out = []
        for t in tweets[:limit]:
            txt = _txt(t)
            if not txt:
                continue
            tid = t.get("id") or t.get("id_str") or ""
            u = t.get("url") if isinstance(t.get("url"), str) else None
            u = u or (t.get("twitterUrl") if isinstance(t.get("twitterUrl"), str) else None)
            u = u or (f"https://x.com/{handle}/status/{tid}" if tid else f"https://x.com/{handle}")
            when, ts = _when(t.get("createdAt") or t.get("created_at"))
            out.append({"text": txt, "created_at": when, "ts": ts, "url": u})
        return out
    except Exception:
        return []
    finally:
        if not spent_ok:                         # 请求未成功 → 退款
            budget.settle(budget.EST_TWEET, 0.0)


# ── Claude 摘要（可选）──────────────────────────────────────
def summarize(name: str, articles: list[dict], api_key: str,
              model: str | None = None) -> str | None:
    """把某人物近期新闻标题提炼成 2–3 条中文要点；无 key/失败/超预算→None。"""
    if not api_key or not articles:
        return None
    mdl = model or "claude-sonnet-4-6"           # 默认 Sonnet（短摘要成本很低）
    if not budget.reserve(budget.EST_SUMMARY):   # 每日花费保护
        return None
    actual = 0.0
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        heads = "\n".join(f"- {a['title']} ({a['domain']})" for a in articles[:8])
        prompt = (f"以下是关于「{name}」近期的新闻标题。请用中文提炼 2–3 条要点，"
                  f"概括其最新表态 / 动态，每条一句话，聚焦对市场或行业有意义的信息；"
                  f"不要编造标题之外的内容。直接给要点，不要前言：\n{heads}")
        resp = client.messages.create(
            model=mdl, max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        actual = budget.claude_cost(mdl, resp.usage)
        txt = "".join(getattr(b, "text", "") for b in resp.content
                      if getattr(b, "type", None) == "text").strip()
        return txt or None
    except Exception:
        return None
    finally:
        budget.settle(budget.EST_SUMMARY, actual)   # 按真实 token 结算（失败则退款）


# ── 深度解读：让 Claude 用 web_search/web_fetch 联网读原文再提炼 ──
# Google 新闻链接是加密跳转，本地 requests 抓不到正文；交给 Claude 的
# 联网工具去找到并通读真实文章，鲁棒性远好于自己爬取。
def deep_read(name: str, title: str, url: str, api_key: str,
              model: str | None = None) -> str | None:
    if not api_key:
        return None
    try:
        import anthropic
    except Exception:
        return None
    if not budget.reserve(budget.EST_DEEP):     # 每日花费保护
        return "__BUDGET__"
    actual = budget.WEB_SEARCH_FEE              # 联网检索粗估(token 用量不含)
    try:
        client = anthropic.Anthropic(api_key=api_key)
        tools = [
            {"type": "web_search_20260209", "name": "web_search"},
            {"type": "web_fetch_20260209", "name": "web_fetch"},
        ]
        prompt = (
            f"请联网查找并通读下面这篇文章，然后做结构化精读。\n"
            f"人物：{name}\n标题：{title}\n链接（可先用 web_fetch 尝试，失败则用 "
            f"web_search 按标题/人物搜原文）：{url}\n\n"
            f"读完后用**中文**输出，忠于原文、不要臆造，原文没有的写“原文未提及”：\n"
            f"**核心观点**：1–2 句\n"
            f"**为什么 / 主要论据**：3–5 条要点\n"
            f"**建议 / 如何应对**：2–4 条\n"
            f"**对市场 / 行业影响**：1–2 句\n"
            f"最后附 1–3 条来源链接。"
        )
        mdl = model or "claude-opus-4-8"
        messages = [{"role": "user", "content": prompt}]
        resp = client.messages.create(model=mdl, max_tokens=3000,
                                      thinking={"type": "adaptive"},
                                      tools=tools, messages=messages)
        actual += budget.claude_cost(mdl, resp.usage)
        # 服务端工具循环：pause_turn 时回传上下文继续，最多 4 次
        for _ in range(4):
            if resp.stop_reason != "pause_turn":
                break
            messages.append({"role": "assistant", "content": resp.content})
            resp = client.messages.create(model=mdl, max_tokens=3000,
                                          thinking={"type": "adaptive"},
                                          tools=tools, messages=messages)
            actual += budget.claude_cost(mdl, resp.usage)
        return "".join(getattr(b, "text", "") for b in resp.content
                       if getattr(b, "type", None) == "text").strip() or None
    except Exception:
        return None
    finally:
        budget.settle(budget.EST_DEEP, actual)   # 按真实用量结算（失败则退款）


# ── 维基百科人物头像（免费，给没有 X 账号的人用真实照片）──────
def wiki_thumb(title: str) -> str:
    """返回维基百科该人物的头像缩略图 URL；取不到→''。"""
    requests = _req()
    if requests is None or not title:
        return ""
    try:
        import urllib.parse as _u
        t = _u.quote(title.replace(" ", "_"))
        r = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{t}",
            timeout=10, headers={"User-Agent": "VoicesRadar/1.0 (news dashboard)"})
        r.raise_for_status()
        j = r.json() or {}
        return ((j.get("thumbnail") or {}).get("source")) or ""
    except Exception:
        return ""


def anthropic_key() -> str | None:
    k = secret("ANTHROPIC_API_KEY")
    if k and isinstance(k, str) and k.startswith("sk-ant-") and "xxxx" not in k:
        return k
    return None
