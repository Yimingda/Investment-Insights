"""多品种投资建议面板 —— 统一入口。

一套 UI 渲染多个品种（黄金 / 加密 / 美股 / A股），每个品种是一个 assets 模块。
数据：yfinance / FRED / akshare（缺失则降级示例数据）。
分析：有 ANTHROPIC_API_KEY 用 Claude，否则用规则引擎。
"""
import streamlit as st
from datetime import datetime

from lib import data, ai
from lib.theme import CSS, make_gauge, make_price_chart
from assets import REGISTRY, get_module

# ── Page config ─────────────────────────────────────────────
st.set_page_config(
    page_title="多品种投资建议面板",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(CSS, unsafe_allow_html=True)


# ── 工具 ─────────────────────────────────────────────────────
def anthropic_key() -> str | None:
    k = data.secret("ANTHROPIC_API_KEY")
    if k and isinstance(k, str) and k.startswith("sk-ant-") and "xxxx" not in k:
        return k
    return None


# ── 顶部：品种切换 + 状态 ────────────────────────────────────
ids = [m.id for m in REGISTRY]
labels = {m.id: f"{m.icon} {m.name}" for m in REGISTRY}

top_l, top_r = st.columns([4, 1])
with top_l:
    st.markdown("## 📊 多品种投资建议面板")
with top_r:
    refresh = st.button("⟳ 刷新数据", width="stretch")

asset_id = st.radio(
    "选择品种", ids, format_func=lambda i: labels[i],
    horizontal=True, label_visibility="collapsed",
)
module = get_module(asset_id)

if refresh:
    st.cache_data.clear()
    st.session_state["_do_refresh"] = True

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

# ── KPI Strip ───────────────────────────────────────────────
cols = st.columns(len(snap.kpis))
for c, kpi in zip(cols, snap.kpis):
    c.metric(kpi.label, kpi.value, kpi.sub)

# ── Alerts ──────────────────────────────────────────────────
for al in snap.alerts:
    st.markdown(f'<div class="{al.cls}">{al.text}</div>', unsafe_allow_html=True)

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
                module.name, snap, api_key=key, model=data.secret("ANTHROPIC_MODEL"))
    elif cache_key not in st.session_state:
        # 默认即时显示（无 key 用规则引擎；不主动消耗 Claude 额度）
        st.session_state[cache_key] = ai.analyze(module.name, snap)

    situation, risks, advice, by_claude = st.session_state[cache_key]
    badge = ("<span class='badge badge-up'>Claude AI</span>" if by_claude
             else "<span class='badge badge-neu'>规则引擎</span>")
    st.markdown(f"分析来源：{badge}", unsafe_allow_html=True)
    st.markdown("**当前形势**"); st.markdown(situation)
    st.markdown("**主要风险**"); st.markdown(risks)
    st.markdown("**投资者建议**"); st.info(advice)
    st.markdown('</div>', unsafe_allow_html=True)

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
