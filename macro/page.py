"""宏观「增长×通胀」四象限页面 —— 由投资面板顶部导航进入。

数据 100% yfinance 实时拉取（带缓存），无需任何 key、无需预置文件。
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from . import quadrant as Q

QCOLOR = {
    "Reflation 再通胀": "#e8a23d",
    "Goldilocks 金发女孩": "#3dba6a",
    "Stagflation 滞胀": "#e05555",
    "Deflation 通缩衰退": "#4d8fdb",
}
QCORNER = {"Reflation 再通胀": (1, 1), "Goldilocks 金发女孩": (1, -1),
           "Stagflation 滞胀": (-1, 1), "Deflation 通缩衰退": (-1, -1)}
ANAME = {"gold": "黄金", "btc": "比特币", "ndx": "纳指"}
ACOL = {"gold": "#f1b000", "btc": "#9a7bff", "ndx": "#4d8fdb"}


# ── 数据：一次性拉全部 ticker 的复权收盘，缓存 6 小时 ────────────────────
@st.cache_data(ttl=21600, show_spinner=False)
def _fetch_closes():
    try:
        import yfinance as yf
    except Exception:
        return None
    allt = Q.TICKERS + ["BTC-USD", "^NDX"]
    try:
        df = yf.download(allt, start="2005-01-01", interval="1d",
                         auto_adjust=True, progress=False)
    except Exception:
        return None
    if df is None or len(df) == 0:
        return None
    try:
        close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df
    except Exception:
        return None
    return close


def _dark(fig, height=320, legend=True):
    fig.update_layout(
        height=height, paper_bgcolor="#111318", plot_bgcolor="#111318",
        font=dict(color="#9aa0ad", size=11), margin=dict(l=18, r=18, t=24, b=18),
        showlegend=legend,
        legend=dict(orientation="h", y=1.14, x=1, xanchor="right",
                    font=dict(color="#c9ccd6", size=11)),
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor="#1e2130", zerolinecolor="#2a2e3a", color="#5a6070")
    fig.update_yaxes(gridcolor="#1e2130", zerolinecolor="#2a2e3a", color="#5a6070")
    return fig


def _runs(mask):
    out, start, prev, inside = [], None, None, False
    for dt, v in mask.items():
        if v and not inside:
            start, inside = dt, True
        elif not v and inside:
            out.append((start, prev)); inside = False
        prev = dt
    if inside:
        out.append((start, prev))
    return out


def _card_open(title):
    st.markdown(f'<div class="card"><div class="card-title">{title}</div>',
                unsafe_allow_html=True)


def _card_close():
    st.markdown('</div>', unsafe_allow_html=True)


_PLOT_CFG = {"displayModeBar": False}


def render():
    st.markdown("## 🌦️ 宏观「增长 × 通胀」四象限")
    st.markdown(
        '<div style="font-size:12.5px;color:#c9ccd6;line-height:1.7;margin:-4px 0 6px">'
        '桥水(Bridgewater) Ray Dalio 全天候框架：资产价格由两个相对预期的<b>意外</b>驱动'
        '——<b>增长</b>与<b>通胀</b>，二者交叉成 <b>2×2 = 四种环境</b>。每种环境有不同赢家，'
        '全天候在四个环境里放入<b>大致相等的风险</b>，从而对任何环境都有准备。</div>',
        unsafe_allow_html=True)
    st.markdown(
        '<div class="alert-warn">⚠️ 本看板的增长/通胀轴是<b>市场隐含</b>（用价格比值反推），'
        '并非 CPI/PMI 等宏观实测值——<b>描述性、非预测性，不构成投资建议</b>。</div>',
        unsafe_allow_html=True)

    close = _fetch_closes()
    if close is None or any(t not in getattr(close, "columns", []) for t in Q.TICKERS):
        st.markdown('<div class="alert-dn">行情拉取失败或数据不足（需 yfinance 实时数据）。'
                    '请点右上角「⟳ 刷新数据」或稍后重试。</div>', unsafe_allow_html=True)
        return

    px = close[Q.TICKERS]
    tracked = pd.DataFrame({k: close[v] for k, v in Q.TRACKED.items()
                            if v in close.columns})

    mode_label = st.radio("归一化尺度",
                          ["expanding（自始至今，默认）", "rolling（近 3 年自适应）"],
                          horizontal=True, key="macro_mode", label_visibility="collapsed")
    mode = "rolling" if mode_label.startswith("rolling") else "expanding"

    axes, gz, iz = Q.build_axes(px, mode)
    if axes.empty:
        st.markdown('<div class="alert-dn">数据不足以构建象限（历史过短）。</div>',
                    unsafe_allow_html=True)
        return
    cur = axes.iloc[-1]
    q_now = str(cur["quadrant"])
    dist = float((cur["growth_z"] ** 2 + cur["inflation_z"] ** 2) ** 0.5)

    # ── ① 当前象限 ────────────────────────────────────────────────────
    st.markdown(f"#### ① 当前所处象限 · "
                f"<span style='color:{QCOLOR[q_now]}'>{q_now}</span>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("增长 Growth (σ)", f"{cur['growth_z']:+.2f}",
              "上行" if cur["growth_z"] >= 0 else "下行")
    c2.metric("通胀 Inflation (σ)", f"{cur['inflation_z']:+.2f}",
              "上行" if cur["inflation_z"] >= 0 else "下行")
    c3.metric("当前象限", q_now.split()[0], q_now.split()[-1])
    c4.metric("已持续", f"{int(cur['days_in_regime'])} 日", f"信念 dist={dist:.2f}")
    pb = Q.QUADRANT_PLAYBOOK[q_now]
    st.markdown(
        f'<div class="card" style="font-size:12.5px;line-height:1.7;color:#d4d7e0">'
        f'<b style="color:{QCOLOR[q_now]}">{q_now}</b> — {pb["logic"]}<br>'
        f'<span style="color:#3dba6a">✅ 受益：</span>{"、".join(pb["favor"])}<br>'
        f'<span style="color:#e05555">⛔ 回避：</span>{"、".join(pb["avoid"])}<br>'
        f'<span style="color:#f1b000">🟡 黄金：</span>{pb["gold"]}</div>',
        unsafe_allow_html=True)

    # ── ② 象限地图 + 蜗牛轨迹 ─────────────────────────────────────────
    _card_open("② 象限地图 + 蜗牛轨迹（近 1 年路径，⭐=今天）")
    R = 3.0
    fmap = go.Figure()
    for qname, (gs, isn) in QCORNER.items():
        x0, x1 = (0, R) if gs > 0 else (-R, 0)
        y0, y1 = (0, R) if isn > 0 else (-R, 0)
        fmap.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                       fillcolor=QCOLOR[qname], opacity=0.13, line_width=0, layer="below")
        fmap.add_annotation(x=x1 * 0.62, y=y1 * 0.9, text=qname, showarrow=False,
                            font=dict(size=12, color=QCOLOR[qname]))
    trail = axes.iloc[-252:]
    fmap.add_trace(go.Scatter(
        x=trail["growth_z"], y=trail["inflation_z"], mode="lines+markers",
        line=dict(color="rgba(170,170,190,0.45)", width=1),
        marker=dict(size=5, color=list(range(len(trail))), colorscale="Plasma", showscale=False),
        hovertext=[d.strftime("%Y-%m-%d") for d in trail.index], hoverinfo="text", name="近1年"))
    fmap.add_trace(go.Scatter(
        x=[cur["growth_z"]], y=[cur["inflation_z"]], mode="markers+text",
        marker=dict(size=17, color=QCOLOR[q_now], line=dict(color="#e9f0e0", width=1.5),
                    symbol="star"),
        text=["今天"], textposition="top center", textfont=dict(color="#e9f0e0"), name="今天"))
    fmap.add_hline(y=0, line_color="#3a3e4a")
    fmap.add_vline(x=0, line_color="#3a3e4a")
    fmap.update_xaxes(range=[-R, R], title_text="增长 Growth (σ) →")
    fmap.update_yaxes(range=[-R, R], title_text="通胀 Inflation (σ) →")
    _dark(fmap, height=440, legend=False)
    fmap.update_layout(hovermode="closest")
    st.plotly_chart(fmap, width="stretch", config=_PLOT_CFG)
    _card_close()

    # ── ③ 两轴历史走势 ────────────────────────────────────────────────
    _card_open("③ 两轴历史走势（背景=当时所处象限）")
    fts = go.Figure()
    fts.add_trace(go.Scatter(x=axes.index, y=axes["growth_z"], name="增长 Growth",
                             line=dict(color="#4d8fdb", width=1)))
    fts.add_trace(go.Scatter(x=axes.index, y=axes["inflation_z"], name="通胀 Inflation",
                             line=dict(color="#e8853d", width=1)))
    for qname, color in QCOLOR.items():
        for s, e in _runs(axes["quadrant"] == qname):
            fts.add_vrect(x0=s, x1=e, fillcolor=color, opacity=0.08, line_width=0, layer="below")
    fts.add_hline(y=0, line_color="#3a3e4a")
    _dark(fts, height=300)
    fts.update_yaxes(title_text="σ")
    st.plotly_chart(fts, width="stretch", config=_PLOT_CFG)
    _card_close()

    # ── ④ 今日成分贡献 ────────────────────────────────────────────────
    contrib = Q.component_contrib(gz, iz, axes.index[-1])
    cc1, cc2 = st.columns(2)
    for col, axis_name, title in ((cc1, "growth", "④ 增长轴 · 今日各腿贡献"),
                                  (cc2, "inflation", "④ 通胀轴 · 今日各腿贡献")):
        with col:
            _card_open(title)
            rows = contrib[axis_name]
            fb = go.Figure(go.Bar(
                x=[r["contrib"] for r in rows], y=[r["expr"] for r in rows], orientation="h",
                marker_color=["#3dba6a" if r["contrib"] >= 0 else "#e05555" for r in rows],
                text=[f"z={r['z']:+.2f}" for r in rows], textposition="auto"))
            fb.add_vline(x=0, line_color="#3a3e4a")
            _dark(fb, height=220, legend=False)
            fb.update_xaxes(title_text="加权贡献 (σ)")
            st.plotly_chart(fb, width="stretch", config=_PLOT_CFG)
            _card_close()

    # ── ⑤ 各象限远期收益 ──────────────────────────────────────────────
    _card_open("⑤ 各象限的远期收益（金/币/纳指，按资产分桶、绝不混合）")
    H = st.radio("远期窗口 H（交易日）", Q.HORIZONS, index=1, horizontal=True, key="macro_H")
    study = Q.forward_return_study(axes, tracked, Q.HORIZONS)
    sH = study[study["horizon"] == H].copy()
    order = list(QCOLOR.keys())
    fbar = go.Figure()
    for a in ("gold", "btc", "ndx"):
        sub = sH[sH["asset"] == a].set_index("quadrant").reindex(order)
        fbar.add_trace(go.Bar(
            x=order, y=(sub["mean"] * 100).values, name=ANAME[a], marker_color=ACOL[a],
            text=[("⚠" if bool(ln) else "") for ln in sub["low_n"].values], textposition="outside"))
    fbar.add_hline(y=0, line_color="#3a3e4a")
    _dark(fbar, height=340)
    fbar.update_layout(barmode="group")
    fbar.update_yaxes(title_text=f"未来 {H} 日平均收益 (%)")
    st.plotly_chart(fbar, width="stretch", config=_PLOT_CFG)
    st.markdown(
        '<div style="font-size:11px;color:#5a6070;margin:2px 0 8px">⚠ = 有效样本不足(eff_n&lt;5)，'
        '该格读数不可靠。<b>eff_n = 该象限天数 ÷ H</b>——每日的 H 日窗口高度重叠、并非独立观测，'
        '真实独立样本远少于天数。</div>', unsafe_allow_html=True)
    show = sH[["asset", "quadrant", "n_days", "eff_n", "mean", "hit", "low_n"]].copy()
    show["asset"] = show["asset"].map(ANAME)
    show["mean"] = (show["mean"] * 100).round(2)
    show["hit"] = (show["hit"] * 100).round(1)
    show = show.rename(columns={"asset": "资产", "quadrant": "象限", "n_days": "天数",
                                "eff_n": "有效N", "mean": "均值%", "hit": "胜率%", "low_n": "样本不足"})
    st.dataframe(show, width="stretch", hide_index=True)
    btc_first = tracked["btc"].dropna().index.min().date() if "btc" in tracked else None
    st.markdown(f'<div style="font-size:11px;color:#5a6070">📅 黄金/纳指自 2010；'
                f'<b>比特币自 {btc_first}</b>(Yahoo BTC-USD 起点)，故 2014 年前的象限里比特币无数据。</div>',
                unsafe_allow_html=True)
    _card_close()

    # ── ⑥ 「数字黄金」证伪 ────────────────────────────────────────────
    _card_open("⑥ 「数字黄金」证伪：比特币 vs 黄金")
    ff = go.Figure()
    for a, c in (("gold", "#f1b000"), ("btc", "#9a7bff")):
        sub = sH[sH["asset"] == a].set_index("quadrant").reindex(order)
        ff.add_trace(go.Bar(x=order, y=(sub["mean"] * 100).values, name=ANAME[a], marker_color=c))
    ff.add_hline(y=0, line_color="#3a3e4a")
    _dark(ff, height=300)
    ff.update_layout(barmode="group")
    ff.update_yaxes(title_text=f"未来 {H} 日平均收益 (%)")
    st.plotly_chart(ff, width="stretch", config=_PLOT_CFG)
    try:
        rc = pd.concat([tracked["btc"].pct_change().rename("b"),
                        tracked["ndx"].pct_change().rename("n"),
                        tracked["gold"].pct_change().rename("g")], axis=1).dropna().sort_index()
        cn = rc["b"].rolling(90).corr(rc["n"])
        cgld = rc["b"].rolling(90).corr(rc["g"])
        fc = go.Figure()
        fc.add_trace(go.Scatter(x=cn.index, y=cn.values, name="BTC ~ 纳指", line=dict(color="#4d8fdb", width=1)))
        fc.add_trace(go.Scatter(x=cgld.index, y=cgld.values, name="BTC ~ 黄金", line=dict(color="#f1b000", width=1)))
        fc.add_hline(y=0, line_color="#3a3e4a")
        _dark(fc, height=240)
        fc.update_yaxes(title_text="90日滚动相关")
        st.plotly_chart(fc, width="stretch", config=_PLOT_CFG)
    except Exception:
        pass
    st.markdown(
        '<div class="alert-warn">📌 经验结论：比特币在<b>滞胀</b>格里收益常为负（与高 beta 风险资产一致），'
        '黄金却抗跌；且比特币与<b>纳指</b>的相关性长期高于与<b>黄金</b>的相关性。'
        '→ 比特币行为更像「高 beta 科技股」，<b>不是「数字黄金」</b>。</div>',
        unsafe_allow_html=True)
    _card_close()

    # ── ⑦ 两轴正交性 ──────────────────────────────────────────────────
    corr_now = float(Q.axis_correlation(axes).dropna().iloc[-1])
    _card_open("⑦ 两轴正交性自检")
    st.markdown(
        f'<div style="font-size:12.5px;color:#c9ccd6;line-height:1.6">'
        f'增长轴 vs 通胀轴 的 126 日滚动相关 = <b style="font-family:monospace">{corr_now:+.2f}</b>。'
        f'接近 0 = 两轴较独立、四象限可信；若 |相关| &gt; 0.3，说明此刻 2×2 被同一驱动因素'
        f'（常是利率）扭成平行四边形，斜角象限读数需打折。</div>', unsafe_allow_html=True)
    _card_close()

    # ── ⑧ 全天候参考配置 ──────────────────────────────────────────────
    _card_open("⑧ 全天候参考配置（静态风险平价，非交易建议）")
    aw = pd.DataFrame(Q.ALLWEATHER).rename(
        columns={"sleeve": "资产", "pct": "美元权重%", "bias": "对应环境"})
    st.dataframe(aw, width="stretch", hide_index=True)
    st.markdown(
        '<div style="font-size:11px;color:#5a6070;line-height:1.6;margin-top:6px">'
        '美元权重看起来「债券很重」，是因为债券<b>每一美元的波动最低</b>——按<b>风险贡献</b>算，'
        '四种环境各占大致相等权重。那 15% 的商品+黄金，就是「通胀/滞胀」环境的风险持有者，'
        '按风险而非美元来配。这是全天候核心：不预测环境，而是对每种环境都 balanced。</div>',
        unsafe_allow_html=True)
    _card_close()

    # ── ⑨ 美林投资时钟叠加 ────────────────────────────────────────────
    _card_open("⑨ 美林投资时钟叠加(同一平面 · 每格的主角资产)")
    mc = Q.MERRILL[q_now]
    st.markdown(
        f'<div style="font-size:13px;color:#d4d7e0;line-height:1.7">'
        f'美林时钟把这**同一个 增长×通胀 平面**看成一个**顺时针转的周期**:复苏→过热→滞胀→衰退。'
        f'每一格有一个**主角资产大类**。当前 <b style="color:{QCOLOR[q_now]}">{q_now}</b> = '
        f'时钟相位 <b>{mc["phase"]}</b> → 🎯 时钟主角:<b style="color:#e8a23d">{mc["lead"]}</b>。</div>',
        unsafe_allow_html=True)
    clock = pd.DataFrame([
        {"象限(本页)": q, "时钟相位": Q.MERRILL[q]["phase"], "主角资产": Q.MERRILL[q]["lead"]}
        for q in Q.MERRILL_CYCLE])
    st.dataframe(clock, width="stretch", hide_index=True)
    st.markdown(
        '<div class="alert-warn" style="font-size:11.5px;line-height:1.6">'
        '⚠️ <b>命名冲突提醒:</b>本页的 “Reflation 再通胀”(增长↑通胀↑)= 美林的 <b>Overheat 过热</b>;'
        '而美林的 “Reflation” 指增长↓通胀↓,即本页的 <b>Deflation</b>(主角债券)。故此处只叠加主角资产、不改本页格名。'
        '</div>', unsafe_allow_html=True)

    # 实证:美林指定的"主角"真的在该格跑赢吗?(复用四大类代理 SPY/DBC/SHY/IEF)
    ms = Q.merrill_leader_study(axes, px)
    fm = go.Figure()
    proxy_names = list(Q.MERRILL_PROXIES.keys())
    pcolor = {"股票 SPY": "#4d8fdb", "商品 DBC": "#e8a23d", "现金 SHY": "#5cc2c2", "债券 IEF": "#3dba6a"}
    for name in proxy_names:
        fm.add_trace(go.Bar(x=ms["quadrant"], y=(ms[name] * 100).values, name=name,
                            marker_color=pcolor[name]))
    fm.add_hline(y=0, line_color="#3a3e4a")
    _dark(fm, height=320)
    fm.update_layout(barmode="group")
    fm.update_yaxes(title_text=f"未来 63 日平均收益 (%)")
    st.plotly_chart(fm, width="stretch", config=_PLOT_CFG)
    verdict = "; ".join(
        f"{r['quadrant'].split()[0]}→时钟押{r['designated'].split()[0]}"
        f"{'✅命中' if r['match'] else '❌实际是'+str(r['actual_winner']).split()[0]}"
        for _, r in ms.iterrows())
    st.caption(f"时钟处方 vs 实测(市场隐含象限,H=63):{verdict}。"
               "命中说明时钟成立,不命中正是'市场隐含时钟 vs 教科书处方'的看点——描述性,非择时。")
    _card_close()

    st.markdown(
        "<div style='text-align:center;font-size:10px;color:#3a3e4a;padding:10px'>"
        "增长/通胀轴为市场隐含的描述性指标 · 数据 yfinance 实时 · "
        "⚠️ 仅供研究参考，不构成投资建议。</div>", unsafe_allow_html=True)
