"""轻量联网检索层 —— 为情报生成/人物精读提供上下文材料。

替代原 Claude 服务端 web_search：DeepSeek API 无内建联网检索，改为
「先检索、后生成」——本层负责检索，结果拼进 prompt 交给 lib/llm.py。

  - 新闻检索：Google News RSS（免费、无 key、中/英文均可，限流宽松）
  - 正文抓取：Jina Reader（r.jina.ai，免费；Google News 加密跳转链接尽力而为）

任何失败一律返回空结果，调用方在 prompt 中如实降级（"未取到检索材料"）。
无 streamlit 依赖 —— App 与 GitHub Actions 脚本共用。
"""
from __future__ import annotations


def _req():
    try:
        import requests
        return requests
    except Exception:
        return None


def news(query: str, limit: int = 8, zh: bool = True) -> list[dict]:
    """Google News RSS 检索。返回 [{title, source, date}]（date 为 MM/DD），失败→[]。"""
    requests = _req()
    if requests is None or not query.strip():
        return []
    try:
        import urllib.parse as _u
        import xml.etree.ElementTree as ET
        loc = "hl=zh-CN&gl=CN&ceid=CN:zh-Hans" if zh else "hl=en-US&gl=US&ceid=US:en"
        url = f"https://news.google.com/rss/search?q={_u.quote(query)}&{loc}"
        r = requests.get(url, timeout=12,
                         headers={"User-Agent": "Mozilla/5.0 (InvestPanel)"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        out, seen = [], set()
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            src = (item.findtext("source") or "").strip()
            pub = item.findtext("pubDate") or ""
            if not title or title in seen:
                continue
            seen.add(title)
            if src and title.endswith(f" - {src}"):     # 去掉标题尾部的来源
                title = title[: -len(src) - 3].strip()
            out.append({"title": title, "source": src, "date": _mmdd(pub)})
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


def _mmdd(rfc822: str) -> str:
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(rfc822).strftime("%m/%d")
    except Exception:
        return ""


def _lines(items: list[dict]) -> str:
    return "\n".join(f"- [{it['date']}] {it['title']}" + (f"（{it['source']}）" if it['source'] else "")
                     for it in items)


def stock_material(code: str, name: str) -> str:
    """个股检索材料：公司新闻 + 财报相关，拼成 prompt 可用的多行文本；无结果→''。"""
    items, seen = [], set()
    for q in (f"{name} {code}", f"{name} 财报 业绩"):
        for it in news(q, limit=8):
            if it["title"] not in seen:
                seen.add(it["title"])
                items.append(it)
    return _lines(items[:14])


def policy_material(industry: str) -> str:
    """行业政策检索材料；无结果→''。"""
    items, seen = [], set()
    for q in (f"{industry} 行业 政策", f"{industry} 监管 新规"):
        for it in news(q, limit=7):
            if it["title"] not in seen:
                seen.add(it["title"])
                items.append(it)
    return _lines(items[:12])


def article_text(url: str, max_chars: int = 20000) -> str:
    """经 Jina Reader 抓正文（可跟随跳转/渲染 JS）。失败→''。"""
    requests = _req()
    if requests is None or not url:
        return ""
    try:
        r = requests.get("https://r.jina.ai/" + url, timeout=30,
                         headers={"Accept": "text/plain",
                                  "User-Agent": "Mozilla/5.0 (InvestPanel)"})
        r.raise_for_status()
        txt = (r.text or "").strip()
        # Reader 对错误页也可能返回 200 短文本，太短视为失败
        return txt[:max_chars] if len(txt) > 300 else ""
    except Exception:
        return ""
