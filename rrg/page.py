"""相对轮动图 RRG 页面 —— 由投资面板顶部导航进入。数据 100% yfinance 实时拉取。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from . import compute as C

_PLOT_CFG = {"displayModeBar": False}


@st.cache_data(ttl=21600, show_spinner=False)
def _fetch_closes():
    try:
        import yfinance as yf
    except Exception:
        return None
    tks = [C.BENCH] + C.SECTORS
    try:
        df = yf.download(tks, start="1998-12-01", interval="1d",
                         auto_adjust=True, progress=False)
    except Exception:
        return None
    if df is None or len(df) == 0:
        return None
    try:
        close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df
    except Exception:
        return None
    close = close.reindex(columns=tks).sort_index()
    return close


def _dark(fig, height=460, legend=True):
    fig.update_layout(
        height=height, paper_bgcolor="#111318", plot_bgcolor="#111318",
        font=dict(color="#9aa0ad", size=11), margin=dict(l=18, r=18, t=24, b=18),
        showlegend=legend,
        legend=dict(orientation="h", y=1.14, x=1, xanchor="right",
                    font=dict(color="#c9ccd6", size=10)))
    fig.update_xaxes(gridcolor="#1e2130", zerolinecolor="#2a2e3a", color="#5a6070")
    fig.update_yaxes(gridcolor="#1e2130", zerolinecolor="#2a2e3a", color="#5a6070")
    return fig


def render():
    st.markdown("## 🔄 相对轮动图 RRG · 板块轮动")
    st.markdown(
        '<div style="font-size:12.5px;color:#c9ccd6;line-height:1.7;margin:-4px 0 6px">'
        'Julius de Kempenaer 的**相对轮动图**:11 个 SPDR 行业相对 SPY,画在 '
        '<b>RS-Ratio(x,相对强弱趋势)× RS-Momentum(y,该趋势的动量)</b> 平面上,以 100 为中心。'
        '四象限**顺时针**轮动:改善 Improving → 领先 Leading → 转弱 Weakening → 落后 Lagging → 改善。'
        '</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="alert-warn">⚠️ RS-Ratio / RS-Momentum 是**无前视的开源近似**'
        '(对相对强弱**水平**做因果 z-score,映射到 100+K·z),**非** StockCharts 的专有 JdK 数值。'
        '描述性、非预测性,不构成投资建议。</div>', unsafe_allow_html=True)

    close = _fetch_closes()
    if close is None or C.BENCH not in getattr(close, "columns", []) or close[C.BENCH].dropna().empty:
        st.markdown('<div class="alert-dn">Yahoo 行情拉取失败或基准 SPY 缺失,稍后重试。</div>',
                    unsafe_allow_html=True)
        return

    wk, partial = C.to_weekly(close)
    if partial:
        wk = wk.iloc[:-1]                       # 全局剔除未完成的当周(所有面板一致)

    # ── 控件 ─────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([1.3, 1, 1])
    deep = c1.toggle("深历史模式(9 板块,去掉 XLRE/XLC,回溯 ~2000)", value=False)
    tail = int(c2.slider("尾迹长度(周)", 4, 14, C.TAIL))
    universe = C.SECTORS_CORE if deep else C.SECTORS

    frames = C.rrg_frame(wk, universe)
    if not frames:
        st.markdown('<div class="alert-dn">可用历史不足,无法计算 RRG。</div>', unsafe_allow_html=True)
        return
    all_weeks = sorted(set().union(*[f.index for f in frames.values()]))
    replay_opts = all_weeks[-260:] if len(all_weeks) > 260 else all_weeks
    asof = c3.select_slider("截至周(回放)", options=[d.date() for d in replay_opts],
                            value=replay_opts[-1].date())
    asof_ts = pd.Timestamp(asof)

    picked = st.multiselect("板块(默认全选)", universe,
                            default=universe, format_func=lambda t: f"{t} {C.NAMES[t]}")
    picked = picked or universe

    # 截至 asof 的每个板块子序列
    sub = {tk: frames[tk].loc[:asof_ts] for tk in picked if not frames[tk].loc[:asof_ts].empty}
    if not sub:
        st.markdown('<div class="alert-warn">该周尚无可绘制的板块(晚上市 + 预热)。</div>',
                    unsafe_allow_html=True)
        return
    st.caption(f"截至 {asof} · 周五锚定周线 · {'含' if not partial else '已剔除'}未完成当周")

    # ── ① RRG 散点(核心)─────────────────────────────────────────────
    R = 3.5 * C.K
    fig = go.Figure()
    for qname, (sx, sy) in {"Leading": (1, 1), "Weakening": (1, -1),
                            "Lagging": (-1, -1), "Improving": (-1, 1)}.items():
        x0, x1 = (100, 100 + R) if sx > 0 else (100 - R, 100)
        y0, y1 = (100, 100 + R) if sy > 0 else (100 - R, 100)
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                      fillcolor=C.QCOLOR[qname], opacity=0.08, line_width=0, layer="below")
        fig.add_annotation(x=(x0 + x1) / 2, y=y0 + (y1 - y0) * (0.9 if sy > 0 else 0.1),
                           text=f"{qname} {C.QUAD_CN[qname]}", showarrow=False,
                           font=dict(size=12, color=C.QCOLOR[qname]))
    fig.add_hline(y=100, line_color="#3a3e4a", line_dash="dot")
    fig.add_vline(x=100, line_color="#3a3e4a", line_dash="dot")
    fig.add_annotation(x=100, y=100, text="◆ SPY", showarrow=False,
                       font=dict(size=10, color="#9aa0ad"), yshift=-10)
    for tk in sub:
        t = sub[tk].iloc[-tail:]
        last = t.iloc[-1]
        col = C.COLORS[tk]
        n = len(t)
        fig.add_trace(go.Scatter(
            x=t["ratio"], y=t["mom"], mode="lines+markers",
            line=dict(color=col, width=1),
            marker=dict(size=[3 + 4 * i / max(1, n - 1) for i in range(n)], color=col,
                        opacity=[0.25 + 0.6 * i / max(1, n - 1) for i in range(n)]),
            name=f"{tk} {C.NAMES[tk]}", hoverinfo="skip", showlegend=False))
        cq = C.quadrant(last["ratio"], last["mom"])
        fig.add_trace(go.Scatter(
            x=[last["ratio"]], y=[last["mom"]], mode="markers+text",
            marker=dict(size=13, color=C.QCOLOR[cq], line=dict(color=col, width=2),
                        symbol="circle"),
            text=[tk], textposition="top center", textfont=dict(color=col, size=10),
            name=tk,
            hovertext=[f"{tk} {C.NAMES[tk]}<br>{cq} {C.QUAD_CN[cq]}<br>"
                       f"RS-Ratio {last['ratio']:.1f} · RS-Mom {last['mom']:.1f}"],
            hoverinfo="text", showlegend=False))
    fig.update_xaxes(range=[100 - R, 100 + R], title_text="RS-Ratio(相对强弱趋势)→")
    fig.update_yaxes(range=[100 - R, 100 + R], title_text="RS-Momentum(动量)→")
    _dark(fig, height=520, legend=False)
    fig.update_layout(hovermode="closest")
    st.plotly_chart(fig, width="stretch", config=_PLOT_CFG)
    st.caption("点由暗到亮 = 由远及近(尾迹),大圆点=最新,颜色=当前象限,描边=板块固定色。")

    # ── ② 当前排位表 ─────────────────────────────────────────────────
    rows = []
    for tk in sub:
        s = sub[tk]
        last = s.iloc[-1]
        qs = C.quad_series(s)
        cq = C.quadrant(last["ratio"], last["mom"])
        prev_mom = s["mom"].iloc[-2] if len(s) > 1 else last["mom"]
        rows.append({"板块": f"{tk} {C.NAMES[tk]}", "象限": f"{cq} {C.QUAD_CN[cq]}",
                     "RS-Ratio": round(last["ratio"], 1), "RS-Mom": round(last["mom"], 1),
                     "动量": "↗" if last["mom"] >= prev_mom else "↘",
                     "已持续(周)": C.weeks_in_current(qs)})
    tbl = pd.DataFrame(rows)
    qrank = {q: i for i, q in enumerate(C.QUAD_ORDER)}
    tbl = tbl.sort_values(by=["象限", "RS-Ratio"],
                          key=lambda s: s.map(lambda v: qrank.get(v.split()[0], 9)) if s.name == "象限" else s,
                          ascending=[True, False]).reset_index(drop=True)
    st.markdown("#### ② 当前排位(按象限顺时针 → RS-Ratio)")
    st.dataframe(tbl, width="stretch", hide_index=True)

    # ── ③ 象限历史时间线(热力图)─────────────────────────────────────
    st.markdown("#### ③ 象限历史(近 ~3 年,一眼看轮动)")
    span = [d for d in all_weeks if d <= asof_ts][-156:]
    code = {"Improving": 0, "Leading": 1, "Weakening": 2, "Lagging": 3}
    z, order_tk = [], universe
    for tk in order_tk:
        if tk not in frames:
            z.append([np.nan] * len(span)); continue
        qs = C.quad_series(frames[tk])
        row = [code.get(qs.get(d), np.nan) if d in qs.index else np.nan for d in span]
        z.append(row)
    colorscale = [[0.0, C.QCOLOR["Improving"]], [0.25, C.QCOLOR["Improving"]],
                  [0.25, C.QCOLOR["Leading"]], [0.5, C.QCOLOR["Leading"]],
                  [0.5, C.QCOLOR["Weakening"]], [0.75, C.QCOLOR["Weakening"]],
                  [0.75, C.QCOLOR["Lagging"]], [1.0, C.QCOLOR["Lagging"]]]
    hm = go.Figure(go.Heatmap(
        z=z, x=[d.date() for d in span], y=[f"{t} {C.NAMES[t]}" for t in order_tk],
        colorscale=colorscale, zmin=0, zmax=3, showscale=False, xgap=0, ygap=1,
        hovertemplate="%{y}<br>%{x}<extra></extra>"))
    _dark(hm, height=max(240, 26 * len(order_tk) + 60), legend=False)
    st.plotly_chart(hm, width="stretch", config=_PLOT_CFG)
    st.caption("蓝=改善 · 绿=领先 · 黄=转弱 · 红=落后 · 空白=尚未上市/预热。")

    # ── ④ 远期收益研究(展开)────────────────────────────────────────
    with st.expander("④ 各象限的下一周收益(滞后、非重叠、无前视)"):
        study = C.forward_return_study(wk, {tk: frames[tk] for tk in universe if tk in frames})
        agg = (study.groupby("quadrant")
               .apply(lambda g: pd.Series({
                   "n_weeks": int(g["n"].sum()),
                   "mean_%": (np.average(g.loc[g["mean"].notna(), "mean"],
                                         weights=g.loc[g["mean"].notna(), "n"]) * 100)
                             if g["mean"].notna().any() else np.nan}))
               .reindex(C.QUAD_ORDER))
        fbar = go.Figure(go.Bar(
            x=[f"{q} {C.QUAD_CN[q]}" for q in C.QUAD_ORDER],
            y=agg["mean_%"].values,
            marker_color=[C.QCOLOR[q] for q in C.QUAD_ORDER]))
        fbar.add_hline(y=0, line_color="#3a3e4a")
        _dark(fbar, height=280, legend=False)
        fbar.update_yaxes(title_text="下一周平均收益 (%)")
        st.plotly_chart(fbar, width="stretch", config=_PLOT_CFG)
        st.caption("⚠️ 这里的 n 是**跨板块汇总**,而板块间高度相关——真实独立样本远少于 n,"
                   "置信区间比看上去宽。RRG 更适合当**当下轮动地图**,而非择时信号。")

    # ── ⑤ 诚实声明 ───────────────────────────────────────────────────
    fv = C.first_valid_dates(frames)
    late = ", ".join(f"{tk}→{fv[tk].date()}" for tk in ("XLRE", "XLC") if tk in fv)
    st.markdown(
        f'<div class="alert-warn" style="font-size:11.5px;line-height:1.7">'
        f'<b>诚实边界:</b> ① RS 指标是开源近似,非专有 JdK 公式;② 晚上市板块首个可绘制周(含 ~1.7 年预热):'
        f'{late or "—"},早期读数样本短;③ 无前视:因果 EMA(adjust=False)+ 截止前一周的 .shift(1) 归一化 + '
        f'周五锚定 + 收益滞后一周;④ 研究/教育用途,非投资建议。</div>',
        unsafe_allow_html=True)
    st.markdown(
        "<div style='text-align:center;font-size:10px;color:#3a3e4a;padding:10px'>"
        "RS 指标为无前视开源近似 · 数据 yfinance 实时 · ⚠️ 仅供研究参考,不构成投资建议。</div>",
        unsafe_allow_html=True)
