"""重要人物动态雷达 —— 实时聚合重要人物的表态 / 采访概要 / X 推文。

数据：Google News + Claude 摘要(可选) + 第三方 X 接口(可选)。
刷新：手动「Get the latest」，结果本地持久化。由投资面板顶部导航进入。
"""
import html as _html
import time
import urllib.parse as _ul
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import streamlit as st

from . import budget
from . import data
from . import people as P
from . import roster
from . import store
from .theme import css


NEWS_TTL, TW_TTL, SUM_TTL, AVATAR_TTL = 900, 1800, 1800, 86400


def _attr(u):
    """转义将放入 href/src 属性的 URL，防止引号截断/注入。"""
    return _html.escape(str(u), quote=True)

import re as _re
# 个别同名者需指定维基词条，避免歧义
_WIKI_OVERRIDE = {
    "John Williams (NY Fed)": "John C. Williams (economist)",
    "Andrew Bailey (BOE)": "Andrew Bailey (banker)",
    "CZ (赵长鹏)": "Changpeng Zhao",
    "Brian Armstrong": "Brian Armstrong (businessman)",
    "Ken Griffin": "Kenneth C. Griffin",
}

# 当前追踪名单（运行时由 roster 决定，渲染/抓取/路由都用它）
TRACKED: list = []


def _latin_name(display):
    s = _re.sub(r"[^A-Za-z.\-' ]", " ", display.split("(")[0])
    return _re.sub(r"\s+", " ", s).strip()


def wiki_title(p):
    return _WIKI_OVERRIDE.get(p["name"]) or _latin_name(p["name"])


# 5 个类别各一种色调（标签页 emoji 圆点 + 卡片色条/徽章）
CAT_COLOR = {
    P.AI_LEAD: "#7aa2f7", P.FED: "#3dba6a", P.CENBANK: "#b48ead",
    P.MARKET: "#e0a458", P.CRYPTO: "#f7931a",
}
CAT_DOT = {
    P.AI_LEAD: "🔵", P.FED: "🟢", P.CENBANK: "🟣", P.MARKET: "🟡", P.CRYPTO: "🟠",
}


# ── 会话缓存（纯值，无 TTL；持久化由 store + 手动获取控制）────
def cache_get(key, ttl=None):
    return st.session_state.get("_cache", {}).get(key)


def cache_put(key, val):
    st.session_state.setdefault("_cache", {})[key] = val


def _sig(news):
    return hash(tuple(a["url"] for a in news[:5])) if news else 0


# ── 并行预热（新闻 + 推文 + 摘要）──────────────────────────
def warm(plist, show_tw, tw_key, tw_base, show_sum, anth_key):
    jobs = []
    for p in plist:
        if cache_get(f"news:{p['en']}", NEWS_TTL) is None:
            jobs.append(("news", p))
        if show_tw and tw_key and p.get("handle") and cache_get(f"tw:{p['handle']}", TW_TTL) is None:
            jobs.append(("tw", p))
    if jobs:
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {}
            for kind, p in jobs:
                if kind == "news":
                    futs[ex.submit(data.fetch_news, p["en"])] = ("news", p["en"])
                else:
                    futs[ex.submit(data.fetch_tweets, p["handle"], tw_key, 5, tw_base)] = ("tw", p["handle"])
            for f in as_completed(futs):
                k, ident = futs[f]
                try:
                    res = f.result()
                except Exception:
                    res = []
                cache_put(f"{k}:{ident}", res)

    # 维基头像（默认首选，给所有无显式 photo 的人拉，缓存一天）
    av_jobs = [p for p in plist if not p.get("photo")
               and cache_get(f"avatar:{p['en']}", AVATAR_TTL) is None]
    if av_jobs:
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(data.wiki_thumb, wiki_title(p)): p["en"] for p in av_jobs}
            for f in as_completed(futs):
                en = futs[f]
                try:
                    res = f.result()
                except Exception:
                    res = ""
                cache_put(f"avatar:{en}", res or "")

    if show_sum and anth_key:
        sjobs = []
        for p in plist:
            news = cache_get(f"news:{p['en']}", NEWS_TTL) or []
            if news and cache_get(f"sum:{p['en']}:{_sig(news)}", SUM_TTL) is None:
                sjobs.append((p, news))
        if sjobs:
            sum_model = data.secret("ANTHROPIC_MODEL") or "claude-sonnet-4-6"
            with ThreadPoolExecutor(max_workers=4) as ex:
                futs = {ex.submit(data.summarize, p["name"], news, anth_key, sum_model):
                        f"sum:{p['en']}:{_sig(news)}" for p, news in sjobs}
                for f in as_completed(futs):
                    ck = futs[f]
                    try:
                        res = f.result()
                    except Exception:
                        res = None
                    cache_put(ck, res)


# ── 手动获取最新数据：全量抓取 + 存盘 ──────────────────────
def do_fetch(show_tw, tw_key, tw_base, show_sum, anth_key):
    c = st.session_state.setdefault("_cache", {})
    for k in list(c):                       # 清时效数据(保留头像/精读)，强制重拉
        if k.split(":", 1)[0] in ("news", "tw", "sum"):
            c.pop(k, None)
    with st.spinner("正在获取最新数据…（约 10–30 秒）"):
        warm(TRACKED, show_tw, tw_key, tw_base, show_sum, anth_key)
    st.session_state["fetched_at"] = time.time()
    store.save(st.session_state["fetched_at"], c)


# ── 头像：handle→unavatar 拉真实 X 头像；否则按名搜；失败回退首字母 ──
def avatar_html(p, color="#1e2130", size=44):
    name = p["name"].split("(")[0].strip()
    initials = ("https://ui-avatars.com/api/?name=" + _ul.quote(name) +
                "&size=96&background=1e2130&color=7aa2f7&bold=true&format=png")
    wiki = cache_get(f"avatar:{p['en']}", AVATAR_TTL)       # 维基真实照片（warm 时拉取）
    if p.get("photo"):                                      # 显式指定优先级最高
        src = p["photo"]
    elif wiki:                                              # 默认首选维基百科头像
        src = wiki
    elif p.get("handle"):                                   # 退回 X 头像
        src = f"https://unavatar.io/x/{p['handle']}?fallback={_ul.quote(initials, safe='')}"
    else:                                                   # 再退回按名搜 / 首字母
        src = f"https://unavatar.io/{_ul.quote(name)}?fallback={_ul.quote(initials, safe='')}"
    return (f'<img src="{src}" referrerpolicy="no-referrer" loading="lazy" '
            f'onerror="this.onerror=null;this.src=\'{initials}\'" alt="" '
            f'style="width:{size}px;height:{size}px;border-radius:50%;object-fit:cover;'
            f'border:2px solid {color}88;flex:0 0 auto;background:#1e2130">')


# ── 🔬 精读 expander（卡片/详情页共用，scope 区分 widget key）──
def deep_expander(p, news, anth_key, scope="grid"):
    with st.expander("🔬 精读 — 抓原文提炼核心观点 / 为什么 / 如何应对"):
        if not news:
            st.caption("暂无文章可精读。")
        elif not anth_key:
            st.caption("需配置 ANTHROPIC_API_KEY 才能精读（secrets.toml）。")
        else:
            opts = list(range(len(news[:5])))
            idx = st.selectbox("选择要精读的文章", opts,
                               format_func=lambda i: news[i]["title"][:70],
                               key=f"sel_{scope}_{p['en']}")
            if st.button("📖 精读这篇", key=f"deep_{scope}_{p['en']}"):
                ck = f"deep:{news[idx]['url']}"
                res = cache_get(ck, 86400)
                if res is None:
                    with st.spinner("联网读原文并解读中（约 10–30 秒）…"):
                        res = data.deep_read(p["name"], news[idx]["title"],
                                             news[idx]["url"], anth_key,
                                             model=data.secret("ANTHROPIC_MODEL"))
                        if res and res != "__BUDGET__":      # 预算阻断不缓存
                            cache_put(ck, res)
                st.session_state[f"deepres_{p['en']}"] = (news[idx]["title"], res or "__FAIL__")
            dr = st.session_state.get(f"deepres_{p['en']}")
            if dr:
                st.markdown(f"**{_html.escape(dr[0])}**")
                if dr[1] == "__BUDGET__":
                    st.warning("今日 API 预算已用尽，精读暂停。可调高 DAILY_BUDGET_USD 或明日再试。")
                elif dr[1] == "__FAIL__":
                    st.warning("解读失败（联网或接口异常）。请点开原文阅读，或稍后重试。")
                else:
                    st.markdown(dr[1])


# ── 渲染单个人物卡 ──────────────────────────────────────────
def render_card(p, show_tw, tw_key, show_sum, anth_key, color="#7aa2f7"):
    esc = _html.escape
    news = cache_get(f"news:{p['en']}", NEWS_TTL) or []
    pid = TRACKED.index(p) if p in TRACKED else 0
    h = (f'<div class="pcard" style="border-left:3px solid {color}">'
         f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">'
         f'<a href="?p={pid}" target="_self" class="plink">{avatar_html(p, color)}</a>'
         f'<div style="flex:1;min-width:0">'
         f'<div><a href="?p={pid}" target="_self" class="plink"><span class="pname">{esc(p["name"])}</span></a>'
         f'<span class="cat-badge" style="background:{color}26;color:{color}">{esc(p["cat"])}</span></div>')
    if p.get("handle"):
        h += f'<a href="https://x.com/{p["handle"]}" target="_blank" class="meta">@{p["handle"]}</a>'
    h += '</div></div>'

    if p.get("stance"):
        h += (f'<div class="stance"><span class="stance-tag">🎯 背后立场</span>'
              f'{esc(p["stance"])}</div>')

    if show_sum:
        summ = cache_get(f"sum:{p['en']}:{_sig(news)}", SUM_TTL)
        if summ:
            h += ('<div class="sec-label">动态概要 · Claude</div>'
                  f'<div class="summary">{esc(summ).replace(chr(10), "<br>")}</div>')

    h += '<div class="sec-label">📰 最新表态 / 报道</div>'
    if news:
        for a in news[:5]:
            h += (f'<div class="news-row"><a href="{_attr(a["url"])}" target="_blank">{esc(a["title"])}</a>'
                  f'<div class="meta">{esc(a["domain"])} · {data.fmt_seendate(a["seendate"])}</div></div>')
    else:
        h += '<div class="empty">暂无近期新闻</div>'

    if show_tw:
        h += '<div class="sec-label">🐦 最新推文</div>'
        if not p.get("handle"):
            h += '<div class="empty">该人物无公开 X 账号</div>'
        elif not tw_key:
            h += '<div class="empty">未配置 X 接口（secrets: TWITTERAPI_KEY）</div>'
        else:
            tws = cache_get(f"tw:{p['handle']}", TW_TTL) or []
            if tws:
                for t in tws[:4]:
                    h += (f'<div class="tweet"><a href="{_attr(t["url"])}" target="_blank" '
                          f'style="color:inherit;text-decoration:none">{esc(t["text"])}</a>'
                          f'<div class="meta">{esc(str(t["created_at"]))}</div></div>')
            else:
                h += '<div class="empty">暂无推文 / 拉取失败</div>'
    h += '</div>'
    st.markdown(h, unsafe_allow_html=True)
    deep_expander(p, news, anth_key, scope="grid")


def _news_ts(s):
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).timestamp()
    except Exception:
        return 0.0


# ── 单人详情页（点头像/名字进入）────────────────────────────
def render_detail(p, show_tw, tw_key, show_sum, anth_key):
    esc = _html.escape
    color = CAT_COLOR.get(p["cat"], "#7aa2f7")
    if st.button("← 返回列表"):
        st.query_params.clear()
        st.rerun()
    news = cache_get(f"news:{p['en']}", NEWS_TTL) or []

    head = (f'<div style="display:flex;align-items:center;gap:16px;margin:4px 0 8px">'
            f'{avatar_html(p, color, size=88)}<div>'
            f'<div style="font-size:24px;font-weight:700;color:{color}">{esc(p["name"])}</div>'
            f'<span class="cat-badge" style="background:{color}26;color:{color}">{esc(p["cat"])}</span>')
    if p.get("handle"):
        head += f' &nbsp;<a href="https://x.com/{p["handle"]}" target="_blank" class="meta">@{p["handle"]}</a>'
    head += '</div></div>'
    st.markdown(head, unsafe_allow_html=True)

    if p.get("stance"):
        st.markdown(f'<div class="stance"><span class="stance-tag">🎯 背后立场 / 利益</span>'
                    f'{esc(p["stance"])}</div>', unsafe_allow_html=True)
        st.caption("立场为依据其身份与利益结构的推导，仅供「打折扣」参考，非其本人主张。")

    if show_sum:
        summ = cache_get(f"sum:{p['en']}:{_sig(news)}", SUM_TTL)
        if summ:
            st.markdown(f'<div class="summary">{esc(summ).replace(chr(10), "<br>")}</div>',
                        unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        nh = (f'<div class="pcard" style="border-left:3px solid {color}">'
              f'<div class="sec-label">📰 最新表态 / 报道</div>')
        if news:
            for a in news[:8]:
                nh += (f'<div class="news-row"><a href="{_attr(a["url"])}" target="_blank">{esc(a["title"])}</a>'
                       f'<div class="meta">{esc(a["domain"])} · {data.fmt_seendate(a["seendate"])}</div></div>')
        else:
            nh += '<div class="empty">暂无近期新闻</div>'
        st.markdown(nh + '</div>', unsafe_allow_html=True)
    with col2:
        th = (f'<div class="pcard" style="border-left:3px solid {color}">'
              f'<div class="sec-label">🐦 最新推文</div>')
        if not p.get("handle"):
            th += '<div class="empty">该人物无公开 X 账号</div>'
        elif not tw_key:
            th += '<div class="empty">未配置 X 接口（secrets: TWITTERAPI_KEY）</div>'
        else:
            tws = cache_get(f"tw:{p['handle']}", TW_TTL) or []
            if tws:
                for t in tws[:8]:
                    th += (f'<div class="tweet"><a href="{_attr(t["url"])}" target="_blank" '
                           f'style="color:inherit;text-decoration:none">{esc(t["text"])}</a>'
                           f'<div class="meta">{esc(str(t["created_at"]))}</div></div>')
            else:
                th += '<div class="empty">暂无推文 / 拉取失败</div>'
        st.markdown(th + '</div>', unsafe_allow_html=True)

    deep_expander(p, news, anth_key, scope="detail")


# ── 全员动态时间线（新闻 + 推文按时间倒序混排）──────────────
def render_timeline(plist, show_tw):
    esc = _html.escape
    items = []
    for p in plist:
        color = CAT_COLOR.get(p["cat"], "#7aa2f7")
        pid = TRACKED.index(p) if p in TRACKED else 0
        for a in (cache_get(f"news:{p['en']}", NEWS_TTL) or [])[:3]:
            items.append((_news_ts(a["seendate"]), p, pid, color, "📰",
                          a["title"], a["url"], a.get("domain", "")))
        if show_tw and p.get("handle"):
            for t in (cache_get(f"tw:{p['handle']}", TW_TTL) or [])[:3]:
                items.append((t.get("ts", 0) or 0, p, pid, color, "🐦",
                              t["text"], t["url"], "@" + p["handle"]))
    items.sort(key=lambda x: x[0] or 0, reverse=True)
    if not items:
        st.info("暂无动态（仍在加载，或数据源不可用）。")
        return
    rows = ""
    for ts, p, pid, color, icon, text, url, meta in items[:60]:
        when = datetime.fromtimestamp(ts).strftime("%m/%d %H:%M") if ts else ""
        nm = esc(p["name"].split("(")[0].strip())
        rows += (
            f'<div class="tl-row">'
            f'<a href="?p={pid}" target="_self" class="plink">{avatar_html(p, color, size=34)}</a>'
            f'<div style="flex:1;min-width:0">'
            f'<div style="font-size:11px"><a href="?p={pid}" target="_self" class="plink" '
            f'style="color:{color};font-weight:600">{nm}</a> '
            f'<span class="meta">{icon} {esc(meta)} · {when}</span></div>'
            f'<div class="tl-text"><a href="{_attr(url)}" target="_blank">{esc(text)}</a></div>'
            f'</div></div>')
    st.markdown(rows, unsafe_allow_html=True)


# ── 管理追踪人员（增减 / 推荐候选 / 自定义）─────────────────
def render_manage():
    st.markdown("### 👥 管理追踪人员")
    custom = st.session_state.get("roster_custom", [])
    catalog, seen = [], set()
    for p in (P.PEOPLE + P.CANDIDATES + custom):     # 全部可选项（去重）
        if p["name"] not in seen:
            seen.add(p["name"])
            catalog.append(p)
    names = [p["name"] for p in catalog]
    active = st.session_state.get("roster_active", [])

    sel = st.multiselect(
        "勾选要追踪的人物（取消勾选=移除，展开下拉添加候选）",
        names, default=[n for n in names if n in active],
        key="_roster_sel")
    a, b = st.columns([1, 4])
    if a.button("💾 保存名单", type="primary", width="stretch"):
        st.session_state["roster_active"] = list(sel)
        roster.save(sel, custom)
        st.success(f"已保存：追踪 {len(sel)} 人。新加入者的新闻/头像将在下次「Get the latest」拉取。")
    b.caption(f"当前勾选 {len(sel)} 人 · 候选库共 {len(catalog)} 人")

    with st.expander(f"🌟 推荐候选（{len(P.CANDIDATES)} 位，去上方下拉里挑）", expanded=True):
        for cat in P.CATEGORIES:
            cs = [p["name"] for p in P.CANDIDATES if p["cat"] == cat]
            if cs:
                dot = CAT_DOT.get(cat, "")
                st.markdown(f"{dot} **{cat}**：" + " · ".join(cs))

    with st.expander("➕ 自定义添加（名单/候选里都没有的人）"):
        with st.form("add_custom", clear_on_submit=True):
            nm = st.text_input("显示名（如：张三 / Jane Doe）")
            en = st.text_input("英文检索词（用于搜新闻，如：Jane Doe CEO Acme）")
            c1, c2 = st.columns(2)
            cat = c1.selectbox("类别", P.CATEGORIES)
            hd = c2.text_input("X 用户名（可空，不带 @）")
            if st.form_submit_button("添加并追踪"):
                if nm.strip() and en.strip():
                    person = {"name": nm.strip(), "en": en.strip(), "cat": cat,
                              "handle": (hd.strip() or None)}
                    cust = st.session_state.get("roster_custom", [])
                    if all(c["name"] != person["name"] for c in cust) and \
                            all(p["name"] != person["name"] for p in P.PEOPLE + P.CANDIDATES):
                        cust.append(person)
                    act = st.session_state.get("roster_active", [])
                    if person["name"] not in act:
                        act.append(person["name"])
                    st.session_state["roster_custom"] = cust
                    st.session_state["roster_active"] = act
                    st.session_state["_roster_sel"] = list(act)   # 同步多选框选中态
                    roster.save(act, cust)
                    st.success(f"已添加并追踪「{person['name']}」。")
                    st.rerun()
                else:
                    st.warning("「显示名」和「英文检索词」必填。")


# ════════════════════════════════════════════════════════════
# 渲染入口（被投资面板顶部导航调用）
# ════════════════════════════════════════════════════════════
def render():
    global TRACKED
    _THEME = "light" if st.session_state.get("vr_light", False) else "dark"
    st.markdown(css(_THEME), unsafe_allow_html=True)

    top_l, top_r = st.columns([4, 1])
    with top_l:
        st.markdown("## 📡 重要人物动态雷达")
    with top_r:
        get_latest = st.button("🔄 Get the latest", width="stretch", type="primary")

    c1, c2, c3, c4 = st.columns([2.0, 1.0, 1.0, 1.0])
    with c1:
        view = st.radio("视图", ["📇 分类", "🕒 时间线", "👥 管理"],
                        horizontal=True, label_visibility="collapsed")
    with c2:
        st.toggle("☀️ 白天", key="vr_light")          # 切换日/夜色系（顶部据此注入 CSS）
    with c3:
        show_sum = st.toggle("摘要", value=True)
    with c4:
        show_tw = st.toggle("推文", value=True)

    tw_key = data.secret("TWITTERAPI_KEY")
    tw_base = data.secret("TWITTER_API_BASE")  # 换其它服务时配置
    anth_key = data.anthropic_key()
    budget.set_cap(data.secret("DAILY_BUDGET_USD", 0.20))   # 每日花费上限(USD)

    # 开页：把本地快照载入会话缓存（仅一次）→ 默认展示本地数据
    if not st.session_state.get("_loaded"):
        _fa, _data = store.load()
        st.session_state["_cache"] = _data
        st.session_state["fetched_at"] = _fa
        st.session_state["_loaded"] = True

    # 载入追踪名单（roster）→ 构建当前追踪列表 TRACKED（渲染/抓取/路由都用它）
    if not st.session_state.get("_roster_loaded"):
        _act, _cust = roster.load([p["name"] for p in P.PEOPLE])
        st.session_state["roster_active"] = _act
        st.session_state["roster_custom"] = _cust
        st.session_state["_roster_loaded"] = True
    _active_names = st.session_state.get("roster_active", [])
    _catalog, _seen = [], set()
    for _p in (P.PEOPLE + P.CANDIDATES + st.session_state.get("roster_custom", [])):
        if _p["name"] not in _seen:
            _seen.add(_p["name"])
            _catalog.append(_p)
    TRACKED = [_p for _p in _catalog if _p["name"] in _active_names]

    fetched_at = float(st.session_state.get("fetched_at", 0) or 0)
    age_h = (time.time() - fetched_at) / 3600 if fetched_at else 1e9

    # 点「Get the latest」：<5h 弹确认，否则直接抓
    if get_latest:
        if fetched_at and age_h < 5:
            st.session_state["_dialog"] = "confirm"
        else:
            do_fetch(show_tw, tw_key, tw_base, show_sum, anth_key)
            st.rerun()

    _sel = st.query_params.get("p")
    # >24h(或无数据) 自动弹窗提示获取（仅列表页、非管理页、未确认过本会话）
    if (_sel is None and "管理" not in view and st.session_state.get("_dialog") is None
            and (not fetched_at or age_h >= 24) and not st.session_state.get("_stale_ack")):
        st.session_state["_dialog"] = "stale"

    # ── 弹窗 ────────────────────────────────────────────────────
    _dlg = st.session_state.get("_dialog")
    if _dlg == "confirm":
        @st.dialog("数据较新，确认重新获取？")
        def _confirm_dialog():
            st.write(f"当前数据距今仅 **{age_h:.1f} 小时**（不足 5 小时）。"
                     f"重新获取会消耗 API 额度，确认继续？")
            a, b = st.columns(2)
            if a.button("✅ 确认获取", width="stretch"):
                st.session_state["_dialog"] = None
                do_fetch(show_tw, tw_key, tw_base, show_sum, anth_key)
                st.rerun()
            if b.button("取消", width="stretch"):
                st.session_state["_dialog"] = None
                st.rerun()
        _confirm_dialog()
    elif _dlg == "stale":
        @st.dialog("数据需要更新")
        def _stale_dialog():
            if not fetched_at:
                st.warning("本地暂无数据。点击下方按钮获取最新动态。")
            else:
                st.warning(f"本地数据已 **{age_h:.0f} 小时**未更新（超过 24 小时），建议获取最新。")
            a, b = st.columns(2)
            if a.button("🔄 立即获取", width="stretch"):
                st.session_state["_dialog"] = None
                do_fetch(show_tw, tw_key, tw_base, show_sum, anth_key)
                st.rerun()
            if b.button("先看本地", width="stretch"):
                st.session_state["_dialog"] = None
                st.session_state["_stale_ack"] = True
                st.rerun()
        _stale_dialog()

    # ── 管理人员视图 ─────────────────────────────────────────────
    if "管理" in view:
        render_manage()
        st.stop()

    # ── 路由：单人详情页（只读本地缓存，不抓取）──────────────────
    if _sel is not None:
        try:
            _person = TRACKED[int(_sel)]
        except Exception:
            _person = None
        if _person:
            render_detail(_person, show_tw, tw_key, show_sum, anth_key)
            st.stop()
        st.query_params.clear()

    plist = TRACKED
    _spent, _cap = budget.spent_today(), budget.cap()
    if fetched_at:
        _fresh = (f"数据更新于 {datetime.fromtimestamp(fetched_at).strftime('%m/%d %H:%M')}"
                  f"（{age_h:.1f} 小时前）")
    else:
        _fresh = "本地暂无数据 —— 点右上「Get the latest」"
    st.caption(f"{_fresh} · 追踪 {len(plist)} 人 · "
               f"Claude {'✅' if anth_key else '未配置'} · X接口 {'✅' if tw_key else '未配置'} · "
               f"💰 今日 ${_spent:.3f}/${_cap:.2f}")
    if budget.remaining() <= 0 and _cap > 0:
        st.warning("⚠️ 今日 API 预算已用尽 —— 摘要/精读/推文暂停，新闻与头像不受影响，次日恢复。")

    # ── 渲染（只读本地缓存，不自动抓取）─────────────────────────
    if "时间线" in view:
        render_timeline(plist, show_tw)
    else:
        tabs = st.tabs([f"{CAT_DOT.get(c, '')} {c}" for c in P.CATEGORIES])
        for tab, cat in zip(tabs, P.CATEGORIES):
            with tab:
                grp = [p for p in plist if p["cat"] == cat]
                color = CAT_COLOR.get(cat, "#7aa2f7")
                cols = st.columns(2)
                for i, p in enumerate(grp):
                    with cols[i % 2]:
                        render_card(p, show_tw, tw_key, show_sum, anth_key, color)

    st.markdown(
        "<div style='text-align:center;font-size:10px;color:#3a3e4a;padding:8px'>"
        "新闻来自 GDELT 公开数据 · 摘要由 Claude 生成可能有误 · 推文经第三方接口 · "
        "仅供信息参考，请以官方原文为准</div>", unsafe_allow_html=True)
