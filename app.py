"""多品种投资建议面板 —— 统一入口。

一套 UI 渲染多个品种（黄金 / 加密 / 美股 / A股），每个品种是一个 assets 模块。
数据：yfinance / FRED / akshare（缺失则降级示例数据）。
分析：有 ANTHROPIC_API_KEY 用 Claude，否则用规则引擎。
"""
import html as _html
import streamlit as st
from datetime import datetime, date

esc = _html.escape   # HTML 转义（持仓监控等富文本卡片用）

from lib import data, ai, events, news, alerts, usage, stocks
from lib.theme import CSS, make_gauge, make_price_chart, make_bar, make_hbar
from lib.model import score_label
from assets import REGISTRY, get_module
from radar import page as radar_page
from macro import page as macro_page
from rrg import page as rrg_page
from gem import page as gem_page
from extremes import page as extremes_page
from glossary import page as glossary_page

# ── Page config ─────────────────────────────────────────────
st.set_page_config(
    page_title="多品种投资建议面板",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(CSS, unsafe_allow_html=True)


# ── 访问密码门（仅当 secrets 里设了 APP_PASSWORD 才启用）────────
def _check_auth():
    import hmac
    pw = data.secret("APP_PASSWORD")
    if not pw or not str(pw).strip():      # 未配置 → 不设门（本地/忘配时不锁死）
        return
    if st.session_state.get("_authed"):
        return
    st.markdown("## 🔒 访问验证")
    st.caption("本站需要密码访问。")
    with st.form("_auth_form", clear_on_submit=False):
        entered = st.text_input("密码", type="password", label_visibility="collapsed",
                                placeholder="请输入访问密码")
        ok = st.form_submit_button("进入", type="primary")
    if ok:
        if hmac.compare_digest(str(entered), str(pw)):
            st.session_state["_authed"] = True
            st.rerun()
        else:
            st.error("密码不正确，请重试。")
    st.stop()


_check_auth()


# ── 工具 ─────────────────────────────────────────────────────
def anthropic_key() -> str | None:
    k = data.secret("ANTHROPIC_API_KEY")
    if k and isinstance(k, str) and k.startswith("sk-ant-") and "xxxx" not in k:
        return k
    return None


def render_cost_page():
    """💰 API 花费监控页：Anthropic Cost Admin API 的趋势 + 消耗结构。"""
    st.markdown("## 💰 API 花费监控")
    admin = data.secret("ANTHROPIC_ADMIN_KEY")
    valid = usage.is_admin_key(admin)
    days = st.radio("时间范围", [7, 30, 90], index=1, horizontal=True,
                    format_func=lambda d: f"近 {d} 天", label_visibility="collapsed")

    rep = usage.cost_report(admin, days) if valid else None
    is_sample = rep is None
    if rep is None:
        rep = usage.sample_report(days)

    if is_sample:
        st.markdown('<div class="alert-warn">⚠️ 当前为<b>示例数据</b>（未配置有效 ANTHROPIC_ADMIN_KEY）。'
                    '配置后将显示你账户的真实花费。</div>', unsafe_allow_html=True)

    daily = rep["daily"]
    by = rep["by_label"]
    total = rep["total"]
    avg = total / max(1, len(daily))
    mx = max((v for _, v in daily), default=0.0)
    top = max(by.items(), key=lambda kv: kv[1]) if by else ("-", 0.0)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(f"近{days}天总花费", f"${total:,.2f}")
    k2.metric("日均花费", f"${avg:,.2f}")
    k3.metric("最大单日", f"${mx:,.2f}")
    k4.metric("最大消耗项", top[0], f"${top[1]:,.2f}")

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown('<div class="card"><div class="card-title">每日花费趋势 (USD)</div>',
                    unsafe_allow_html=True)
        if daily:
            st.plotly_chart(make_bar([d[5:] for d, _ in daily], [v for _, v in daily]),
                            width="stretch", config={"displayModeBar": False})
        else:
            st.markdown('<div style="color:#5a6070;font-size:12px;padding:12px 0">该时间段暂无花费数据。</div>',
                        unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="card"><div class="card-title">消耗结构 · 哪里花得多</div>',
                    unsafe_allow_html=True)
        if by:
            items = sorted(by.items(), key=lambda kv: -kv[1])[:8]
            st.plotly_chart(make_hbar([k for k, _ in items], [v for _, v in items]),
                            width="stretch", config={"displayModeBar": False})
            for label, val in items:
                pct = val / total * 100 if total else 0
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;font-size:11px;'
                    f'padding:3px 0;border-bottom:1px solid #1e2130">'
                    f'<span style="color:#c9ccd6">{label}</span>'
                    f'<span style="font-family:monospace">${val:,.2f} '
                    f'<span style="color:#5a6070">({pct:.0f}%)</span></span></div>',
                    unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    if is_sample:
        st.markdown(
            '<div class="card"><div class="card-title">如何接入真实花费</div>'
            '<div style="font-size:12px;line-height:1.8;color:#c9ccd6">'
            '1. 打开 <b>Claude Console → Settings → Admin keys</b>（需组织 admin 角色），创建 Admin API key（<code>sk-ant-admin...</code>）。<br>'
            '2. 填入 <code>.streamlit/secrets.toml</code>：<code>ANTHROPIC_ADMIN_KEY = "sk-ant-admin..."</code>（已 .gitignore，不会提交）。<br>'
            '3. 刷新本页即可看到真实花费趋势与消耗结构。<br>'
            '<span style="color:#e08030">⚠️ Admin key 权限较大，请妥善保管、切勿提交到代码库。个人账户需先在 Console 建立组织。</span>'
            '</div></div>', unsafe_allow_html=True)
    st.markdown("""<div style='text-align:center;font-size:10px;color:#3a3e4a;padding:8px'>
    数据来自 Anthropic Cost Admin API（约 5 分钟延迟）· 金额为美元</div>""", unsafe_allow_html=True)


def render_stock_watchlist():
    """A股自选股：输入代码 → 实时评分 + 建议（仅 A股页面显示）。"""
    st.markdown("### 🔎 A股自选股")
    raw = st.text_input(
        "输入 A股代码（空格/逗号分隔，可带名称）",
        key="ashare_watch", placeholder="例：600519 贵州茅台, 300750 宁德时代, 000858",
        label_visibility="collapsed")
    if not raw.strip():
        st.caption("输入代码后回车，逐只显示实时评分与建议。沪市 6 开头→.SS，深市 0/3 开头→.SZ，自动识别。")
        return
    entries = stocks.parse_entries(raw)[:9]
    cols = st.columns(min(3, len(entries)) or 1)
    for i, (code, name) in enumerate(entries):
        r = stocks.analyze(code, name)
        with cols[i % len(cols)]:
            if not r["ok"]:
                st.markdown(f'<div class="card"><b>{r["name"]}</b> '
                            f'<span style="color:#5a6070;font-size:11px">{r["ticker"]}</span><br>'
                            f'<span style="color:#e05555;font-size:12px">未取到数据，请核对代码</span></div>',
                            unsafe_allow_html=True)
                continue
            lab, col = score_label(r["score"])
            up = r["chg"] >= 0
            cc = "#3dba6a" if up else "#e05555"
            macd_txt = ("金叉" if (r["macd_hist"] or 0) > 0 else "死叉") if r["macd_hist"] is not None else "—"
            st.markdown(
                f'<div class="card">'
                f'<div style="display:flex;justify-content:space-between;align-items:baseline">'
                f'<b style="font-size:14px">{r["name"]}</b>'
                f'<span style="color:#5a6070;font-size:11px">{r["ticker"]}</span></div>'
                f'<div style="font-family:monospace;font-size:20px;margin:4px 0">¥{r["price"]:,.2f} '
                f'<span style="font-size:12px;color:{cc}">{"+" if up else ""}{r["chg_pct"]:.2f}%</span></div>'
                f'<div style="font-size:12px;color:{col};font-weight:600">综合评分 {r["score"]}/100 · {lab}</div>'
                f'<div style="font-size:11px;color:#5a6070;margin:6px 0">'
                f'MA20/60 {"多头" if r["bullish_ma"] else "空头"} · RSI {r["rsi"]:.0f} · '
                f'20日 {r["mom20"]:+.1f}% · MACD {macd_txt}</div>'
                f'<div style="font-size:12px;color:#e4e6ee;line-height:1.55">💡 {r["advice"]}</div>'
                f'</div>', unsafe_allow_html=True)
    st.caption("评分基于实时技术面（趋势 / RSI / 动量 / MACD）。⚠️ 个股波动大，仅供参考，不构成投资建议。")


@st.cache_data(ttl=1800, show_spinner=False)
def _stock_news(name: str) -> list[dict]:
    """个股新闻（复用雷达的免费 Google News RSS，按中文名检索）。"""
    try:
        from radar import data as rd
        return rd.fetch_news(name)[:3]
    except Exception:
        return []


def _holding_panel(r: dict):
    """单只持仓监控面板。返回 (市值, 成本额, 盈亏额) 供组合汇总；取数失败返回 None。"""
    from lib import portfolio as pf
    a = stocks.analyze(r["code"], r["name"])
    if not a["ok"]:
        st.markdown(f'<div class="card"><b>{r["name"]}</b> '
                    f'<span style="color:#5a6070;font-size:11px">{r["code"]}</span><br>'
                    f'<span style="color:#e05555;font-size:12px">未取到数据，请核对代码</span></div>',
                    unsafe_allow_html=True)
        return None
    price, cost, shares = a["price"], r.get("cost", 0), r.get("shares", 0)
    up = a["chg"] >= 0
    cc = "#3dba6a" if up else "#e05555"
    pl = pf.pnl(price, cost, shares)
    lab, lcol, ltext = pf.verdict(a, cost)

    # 顶部：名称 / 代码 / 现价 / 涨跌
    st.markdown(
        f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-top:2px">'
        f'<span style="font-size:16px;font-weight:700">{a["name"]} '
        f'<span style="color:#5a6070;font-size:11px">{a["ticker"]}</span></span>'
        f'<span style="font-family:monospace;font-size:19px">¥{price:,.2f} '
        f'<span style="font-size:12px;color:{cc}">{"+" if up else ""}{a["chg_pct"]:.2f}%</span></span>'
        f'</div>', unsafe_allow_html=True)

    # 盈亏 / 回本
    if pl["has_cost"]:
        pc = "#3dba6a" if pl["pnl_amt"] >= 0 else "#e05555"
        be = (f'已回本' if pl["to_breakeven"] <= 0 else f'回本还需 <b>+{pl["to_breakeven"]:.1f}%</b>')
        sh = f'{pl["shares"]:.0f}股' if pl["shares"] else '未填股数'
        st.markdown(
            f'<div style="font-size:12.5px;margin:2px 0 4px">'
            f'成本 ¥{cost:,.2f} · {sh} · '
            f'盈亏 <b style="color:{pc}">{pl["pnl_amt"]:+,.0f}（{pl["pnl_pct"]:+.2f}%）</b> · {be}</div>',
            unsafe_allow_html=True)
    else:
        st.caption("未填成本 —— 顶部「编辑持仓」填成本价/股数即可显示盈亏与回本价。")

    # 走势图（叠加成本线）
    try:
        fig = theme.make_price_chart(
            a["closes"], a["dates"], price, accent=lcol,
            ma_ref=(cost if cost and cost > 0 else a["ma60"]),
            ma_label=("成本" if cost and cost > 0 else "MA60"), price_prefix="¥")
        st.plotly_chart(fig, width="stretch", key=f"hchart_{r['code']}")
    except Exception:
        pass

    # 技术反转信号
    macd_txt = ("金叉↑" if (a["macd_hist"] or 0) > 0 else "死叉↓") if a["macd_hist"] is not None else "—"
    rsi_txt = ("超卖<30" if a["rsi"] < 30 else ("超买>70" if a["rsi"] > 70 else "中性"))
    st.markdown(
        f'<div style="font-size:11.5px;color:#9aa0b0;margin:2px 0 4px">'
        f'📐 技术：均线 {"多头" if a["bullish_ma"] else "空头"}排列 · 价{"上" if price>=a["ma60"] else "下"}穿60日线 · '
        f'RSI {a["rsi"]:.0f}({rsi_txt}) · MACD {macd_txt} · 距高点 {a["drawdown"]:.0f}% · '
        f'评分 {a["score"]}/100</div>', unsafe_allow_html=True)

    # 关键上涨影响因子
    cat = pf.CATALYSTS.get(r["code"])
    if cat:
        st.markdown(
            f'<div style="background:#3dba6a10;border-left:3px solid #3dba6a99;border-radius:6px;'
            f'padding:7px 10px;font-size:11.5px;line-height:1.55;margin:2px 0 4px">'
            f'<b style="color:#4ec27a">🚀 关键上涨因子</b><br>{esc(cat)}</div>',
            unsafe_allow_html=True)

    # 我的建议
    st.markdown(
        f'<div style="background:{lcol}14;border-left:3px solid {lcol};border-radius:6px;'
        f'padding:7px 10px;font-size:12px;line-height:1.55;margin:2px 0 4px">'
        f'<b style="color:{lcol}">💡 建议 · {lab}</b><br>{esc(ltext)}</div>',
        unsafe_allow_html=True)

    # 个股新闻
    news = _stock_news(a["name"])
    if news:
        rows_html = "".join(
            f'<div style="font-size:11px;padding:3px 0;border-top:1px solid #1e2130">'
            f'<a href="{esc(n["url"])}" target="_blank" style="color:#c8ccd8;text-decoration:none">'
            f'{esc(n["title"])}</a></div>' for n in news)
        st.markdown(f'<div style="margin:2px 0 6px"><span style="font-size:10px;color:#5a6070;'
                    f'text-transform:uppercase">📰 个股新闻</span>{rows_html}</div>',
                    unsafe_allow_html=True)
    st.divider()
    return (pl.get("market_value", 0.0), pl.get("cost_value", 0.0), pl.get("pnl_amt", 0.0))


def render_holdings_monitor():
    """📉 持仓监控盘：一股一盘（盈亏/回本 + 技术信号 + 关键因子 + 新闻 + 建议）。"""
    import json as _json
    import pandas as pd
    from lib import portfolio as pf

    st.markdown("## 📉 持仓监控盘")
    st.caption("每只单独一盘：实时价 · 盈亏/回本 · 技术反转信号 · 关键上涨因子 · 个股新闻 · 我的建议。"
               "⚠️ 仅供参考，不构成投资建议。")

    # 持仓以本次会话(st.session_state)为准 —— 云端各访客互不可见、不写共享磁盘；本地额外落盘持久化
    if "holdings" not in st.session_state:
        st.session_state["holdings"] = pf.load_holdings()
    rows = st.session_state["holdings"]

    if pf.IS_CLOUD:
        st.info("☁️ 云端模式：你填的成本价仅保存在**本次浏览器会话**（他人看不到、刷新/休眠后清空）。"
                "想长期保留，用下方「导出」存成文件，下次「导入」即可。")

    need_cost = any((r.get("cost", 0) or 0) <= 0 for r in rows)
    with st.expander("✏️ 编辑持仓（成本价 / 股数）", expanded=need_cost):
        edited = st.data_editor(
            pd.DataFrame(rows, columns=["code", "name", "cost", "shares"]),
            column_config={
                "code": st.column_config.TextColumn("代码", width="small"),
                "name": st.column_config.TextColumn("名称", width="small"),
                "cost": st.column_config.NumberColumn("成本价(¥)", min_value=0.0, step=0.01, format="%.2f"),
                "shares": st.column_config.NumberColumn("股数", min_value=0.0, step=100.0, format="%.0f"),
            },
            num_rows="dynamic", hide_index=True, width="stretch", key="holdings_editor")
        a, b = st.columns([1, 4])
        if a.button("💾 保存持仓", type="primary", width="stretch"):
            recs = edited.to_dict("records")
            st.session_state["holdings"] = recs
            pf.save_holdings(recs)            # 本地写文件；云端为空操作
            st.success("已保存。")
            st.rerun()
        b.caption("改成本价/股数；也可加行(填代码+名称)或删行。保存后按新持仓刷新。")

        # 导出 / 导入（云端持久化备份，也可跨设备迁移）
        e, f = st.columns(2)
        e.download_button("⬇️ 导出持仓 JSON", data=_json.dumps(rows, ensure_ascii=False),
                          file_name="holdings.json", mime="application/json", width="stretch")
        up = f.file_uploader("⬆️ 导入持仓 JSON", type="json", key="hold_up", label_visibility="collapsed")
        if up is not None:
            sig = f"{up.name}:{up.size}"
            if st.session_state.get("_hold_up_sig") != sig:
                try:
                    data = _json.loads(up.getvalue().decode("utf-8"))
                    assert isinstance(data, list)
                    st.session_state["holdings"] = data
                    st.session_state["_hold_up_sig"] = sig
                    pf.save_holdings(data)
                    st.success("已导入。")
                    st.rerun()
                except Exception:
                    st.error("导入失败：请用本页导出的 JSON 格式。")

    if st.button("⟳ 刷新行情", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    rows = st.session_state["holdings"]
    with st.spinner("加载持仓行情中…（首次约 10–20 秒）"):
        tot = [0.0, 0.0, 0.0]   # 市值 / 成本额 / 盈亏额
        cols = st.columns(2)
        for i, r in enumerate(rows):
            with cols[i % 2]:
                res = _holding_panel(r)
                if res:
                    for k in range(3):
                        tot[k] += res[k]

    if tot[1] > 0:   # 有填成本的组合汇总
        pnl_pct = (tot[2] / tot[1] * 100) if tot[1] else 0.0
        pc = "#3dba6a" if tot[2] >= 0 else "#e05555"
        st.markdown(
            f'<div class="card" style="text-align:center">'
            f'<span style="font-size:12px;color:#5a6070">组合合计（已填成本部分）</span><br>'
            f'市值 ¥{tot[0]:,.0f} · 成本 ¥{tot[1]:,.0f} · '
            f'<b style="color:{pc};font-size:15px">盈亏 {tot[2]:+,.0f}（{pnl_pct:+.2f}%）</b></div>',
            unsafe_allow_html=True)


# ── 顶部：品种切换 + 状态 ────────────────────────────────────
ids = [m.id for m in REGISTRY] + ["__holdings__", "__macro__", "__extremes__", "__rrg__", "__gem__", "__glossary__", "__radar__", "__cost__"]
labels = {m.id: f"{m.icon} {m.name}" for m in REGISTRY}
labels["__holdings__"] = "📉 持仓监控"
labels["__macro__"] = "🌦️ 宏观四象限"
labels["__extremes__"] = "🎯 极值追踪"
labels["__rrg__"] = "🔄 板块轮动 RRG"
labels["__gem__"] = "🚦 双动量 GEM"
labels["__glossary__"] = "📖 术语详解"
labels["__radar__"] = "📡 人物雷达"
labels["__cost__"] = "💰 API花费"

top_l, top_r = st.columns([4, 1])
with top_l:
    st.markdown("## 📊 多品种投资建议面板")
with top_r:
    refresh = st.button("⟳ 刷新数据", width="stretch")

asset_id = st.radio(
    "选择视图", ids, format_func=lambda i: labels[i],
    horizontal=True, label_visibility="collapsed",
)

if refresh:
    st.cache_data.clear()
    st.session_state["_do_refresh"] = True

# 持仓监控 / 宏观四象限 / 人物雷达 / 花费监控是独立视图（非品种），单独渲染后结束
if asset_id == "__holdings__":
    render_holdings_monitor()
    st.stop()
if asset_id == "__macro__":
    macro_page.render()
    st.stop()
if asset_id == "__extremes__":
    extremes_page.render()
    st.stop()
if asset_id == "__rrg__":
    rrg_page.render()
    st.stop()
if asset_id == "__gem__":
    gem_page.render()
    st.stop()
if asset_id == "__glossary__":
    glossary_page.render()
    st.stop()
if asset_id == "__radar__":
    radar_page.render()
    st.stop()
if asset_id == "__cost__":
    render_cost_page()
    st.stop()

module = get_module(asset_id)
do_refresh = st.session_state.pop("_do_refresh", False)
snap = module.build_snapshot(refresh=do_refresh)

# 数据源状态条
libs = data.libs_status()
dot = "live-dot" if snap.data_live else "sim-dot"
lib_tags = " · ".join(f"{n}{'✅' if ok else '❌'}" for n, ok in libs.items())
key_ok = "Claude✅" if anthropic_key() else "Claude（未配置key，用规则引擎）"
st.markdown(
    f"<div style='font-size:11px;color:#5a6070;margin:2px 0 6px'>"
    f"<span class='{dot}'></span>{snap.source_note} · 数据库：{lib_tags} · {key_ok} · "
    f"更新于 {datetime.now().strftime('%H:%M:%S')}</div>",
    unsafe_allow_html=True,
)
st.divider()

# ── 跨品种实时预警 + 当前品种实时新闻（均基于实时数据）──────
_finnhub = data.secret("FINNHUB_API_KEY")
market_alerts = alerts.scan(REGISTRY)
if market_alerts:
    _ac = {"alert-dn": "#e05555", "alert-warn": "#e08030", "alert-up": "#3dba6a"}
    chips = ""
    for _m, cls, text in market_alerts[:8]:
        col = _ac.get(cls, "#5a6070")
        chips += (f'<span style="display:inline-block;margin:2px 6px 2px 0;padding:3px 9px;'
                  f'border-radius:5px;font-size:11px;background:{col}1a;color:{col};'
                  f'border:1px solid {col}55">{text}</span>')
    st.markdown(f"<div style='margin:0 0 8px'><span style='font-size:11px;color:#5a6070'>"
                f"🔔 全市场实时预警（基于实时行情阈值）</span><br>{chips}</div>",
                unsafe_allow_html=True)

# 当前品种实时新闻：喂给 AI 分析 + 页面展示
news_items = news.headlines(asset_id, api_key=_finnhub)
news_titles = [h.title for h in news_items]

# ── KPI Strip ───────────────────────────────────────────────
cols = st.columns(len(snap.kpis))
for c, kpi in zip(cols, snap.kpis):
    c.metric(kpi.label, kpi.value, kpi.sub)

# ── Alerts ──────────────────────────────────────────────────
for al in snap.alerts:
    st.markdown(f'<div class="{al.cls}">{al.text}</div>', unsafe_allow_html=True)

# ── A股自选股（仅 A股页面）──────────────────────────────────
if asset_id == "a_share":
    render_stock_watchlist()
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ── Row 1: Chart + Gauge ────────────────────────────────────
ch_col, ga_col = st.columns([3, 2])
with ch_col:
    st.markdown('<div class="card"><div class="card-title">价格走势（近60日）</div>', unsafe_allow_html=True)
    st.plotly_chart(
        make_price_chart(snap.history, snap.dates, snap.price, accent=module.accent,
                         ma_ref=snap.ma_ref, ma_label=snap.ma_label,
                         price_prefix=module.price_prefix),
        width="stretch", config={"displayModeBar": False},
    )
    st.markdown('</div>', unsafe_allow_html=True)

with ga_col:
    st.markdown('<div class="card"><div class="card-title">综合信号仪表盘</div>', unsafe_allow_html=True)
    st.plotly_chart(make_gauge(snap.score, snap.score_label, snap.score_color),
                    width="stretch", config={"displayModeBar": False})
    rows_html = ""
    for ind in snap.indicators:
        rows_html += f"""<div class="ind-row">
            <span style="color:#5a6070">{ind.name}</span>
            <span style="font-family:monospace;font-size:12px">{ind.value}</span>
            <span class="badge {ind.badge_cls}">{ind.badge_text}</span>
        </div>"""
    st.markdown(rows_html, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ── Row 2: Strategy + AI ────────────────────────────────────
strat_col, ai_col = st.columns(2)
with strat_col:
    st.markdown('<div class="card"><div class="card-title">投资策略推荐</div>', unsafe_allow_html=True)
    tabs = st.tabs([s.title for s in snap.strategies])
    for tab, strat in zip(tabs, snap.strategies):
        with tab:
            st.markdown(strat.body_md)
    st.markdown('</div>', unsafe_allow_html=True)

with ai_col:
    st.markdown('<div class="card"><div class="card-title">🤖 智能行情分析</div>', unsafe_allow_html=True)
    key = anthropic_key()
    cache_key = f"_ai_{asset_id}"

    b1, b2 = st.columns(2)
    with b1:
        if st.button("🔄 重新分析", width="stretch", key=f"re_{asset_id}"):
            st.session_state.pop(cache_key, None)
    with b2:
        force_claude = st.button("🤖 用 Claude 深度分析", width="stretch",
                                 key=f"cl_{asset_id}", disabled=key is None)

    if force_claude and key:
        with st.spinner("Claude 分析中…"):
            st.session_state[cache_key] = ai.analyze(
                module.name, snap, api_key=key,
                model=data.secret("ANTHROPIC_MODEL"), news=news_titles)
    elif cache_key not in st.session_state:
        # 默认即时显示（无 key 用规则引擎；不主动消耗 Claude 额度）
        st.session_state[cache_key] = ai.analyze(module.name, snap, news=news_titles)

    situation, risks, advice, by_claude = st.session_state[cache_key]
    badge = ("<span class='badge badge-up'>Claude AI</span>" if by_claude
             else "<span class='badge badge-neu'>规则引擎</span>")
    st.markdown(f"分析来源：{badge}", unsafe_allow_html=True)
    st.markdown("**当前形势**"); st.markdown(situation)
    st.markdown("**主要风险**"); st.markdown(risks)
    st.markdown("**投资者建议**"); st.info(advice)
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ── 实时新闻 + 投资日历（2列，每页都有，均基于实时数据）──────
news_col, cal_col = st.columns(2)

with news_col:
    nsrc = ("<span class='badge badge-up'>实时</span>" if news_items
            else "<span class='badge badge-neu'>未配置/暂无</span>")
    if news_items:
        inner = ""
        for h in news_items:
            meta = " · ".join(x for x in [h.source, h.when] if x)
            title = (f'<a href="{h.url}" target="_blank" style="color:#e4e6ee;text-decoration:none">{h.title}</a>'
                     if h.url else f'<span style="color:#e4e6ee">{h.title}</span>')
            inner += (f'<div style="padding:7px 4px;border-bottom:1px solid #1e2130">'
                      f'<div style="font-size:12px;line-height:1.4">{title}</div>'
                      f'<div style="font-size:9px;color:#5a6070;margin-top:2px">{meta}</div></div>')
    else:
        inner = ('<div style="font-size:11px;color:#5a6070;padding:8px 0;line-height:1.6">'
                 '暂无实时新闻：A股需 akshare，其余品种需配置 FINNHUB_API_KEY。'
                 '<br>分析仍基于实时行情数据，不受影响。</div>')
    st.markdown(
        f'<div class="card"><div class="card-title">📰 实时新闻 {nsrc}</div>{inner}'
        f'<div style="font-size:9px;color:#5a6070;margin-top:8px">'
        f'已随当前行情一并提供给 AI 分析作消息面参考</div></div>',
        unsafe_allow_html=True,
    )

with cal_col:
    cal = events.upcoming_for(asset_id, api_key=_finnhub)
    _today = date.today()
    _imp_color = {3: "#e05555", 2: "#e08030", 1: "#5a6070"}
    cal_live = any(e.live for e in cal)
    src_tag = ("<span class='badge badge-up'>实时日历</span>" if cal_live
               else "<span class='badge badge-neu'>规则推算</span>")
    rows_html = ""
    for e in cal:
        dd = (e.day - _today).days
        when = "今天" if dd == 0 else ("明天" if dd == 1 else f"{dd}天后")
        c = _imp_color.get(e.importance, "#5a6070")
        bg = "background:rgba(224,128,48,.06);" if dd <= 7 else ""
        note = f" · {e.note}" if e.note else ""
        rows_html += (
            f'<div style="display:flex;align-items:center;gap:10px;padding:7px 4px;'
            f'border-bottom:1px solid #1e2130;{bg}">'
            f'<div style="min-width:92px;font-family:monospace;font-size:11px;color:#c9ccd6">'
            f'{e.day.strftime("%m/%d")} <span style="color:#5a6070">{when}</span></div>'
            f'<div style="flex:1;font-size:12px;color:#e4e6ee">{e.title}'
            f'<span style="color:#5a6070;font-size:11px">{note}</span></div>'
            f'<div style="color:{c};font-size:11px;min-width:34px;text-align:right">{"★" * e.importance}</div>'
            f'</div>')
    if not rows_html:
        rows_html = '<div style="font-size:11px;color:#5a6070;padding:8px 0">近期暂无相关日程。</div>'
    st.markdown(
        f'<div class="card"><div class="card-title">📅 投资日历 · 近45天 {src_tag}</div>{rows_html}'
        f'<div style="font-size:9px;color:#5a6070;margin-top:8px">'
        f'★越多越重磅 · 橙色底=7天内 · 仅当前品种相关 · 配 FINNHUB_API_KEY 走实时日历</div></div>',
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ── Row 3: 相关资产 + 品种专属卡片 ──────────────────────────
cards: list = [("__related__", snap.related)] + list(snap.extra_cards)
row = st.columns(min(3, len(cards)) or 1)
for i, card in enumerate(cards):
    with row[i % len(row)]:
        if card[0] == "__related__":
            st.markdown('<div class="card"><div class="card-title">相关资产监控</div>', unsafe_allow_html=True)
            html = ""
            for r in snap.related:
                color = "#3dba6a" if r.up else "#e05555"
                html += f"""<div style="display:flex;justify-content:space-between;align-items:center;
                            padding:8px 0;border-bottom:1px solid #1e2130">
                  <span style="font-size:12px">{r.name}</span>
                  <div style="text-align:right">
                    <div style="font-family:monospace;font-size:12px">{r.value}</div>
                    <div style="font-size:10px;color:{color}">{r.change}</div></div>
                </div>"""
            st.markdown(html + '</div>', unsafe_allow_html=True)
        else:
            title, inner = card
            st.markdown(f'<div class="card"><div class="card-title">{title}</div>{inner}</div>',
                        unsafe_allow_html=True)

# ── Footer ──────────────────────────────────────────────────
st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
st.markdown("""<div style='text-align:center;font-size:10px;color:#3a3e4a;padding:8px'>
⚠️ 本工具仅供参考，不构成投资建议。投资有风险，入市需谨慎，请结合自身风险承受能力审慎决策。
</div>""", unsafe_allow_html=True)
