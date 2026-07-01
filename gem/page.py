"""双动量 GEM 页面 —— 由投资面板顶部导航进入。数据 100% yfinance 实时拉取。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from . import engine as E

_PLOT_CFG = {"displayModeBar": False}
_ALL_TK = ["SPY", "VEU", "ACWX", "EFA", "AGG", "BND", "BIL", "^IRX"]


@st.cache_data(ttl=21600, show_spinner=False)
def _fetch_closes():
    try:
        import yfinance as yf
    except Exception:
        return None
    try:
        df = yf.download(_ALL_TK, start="2001-01-01", interval="1d",
                         auto_adjust=True, progress=False)
    except Exception:
        return None
    if df is None or len(df) == 0:
        return None
    try:
        return df["Close"] if isinstance(df.columns, pd.MultiIndex) else df
    except Exception:
        return None


def _dark(fig, height=320, legend=True):
    fig.update_layout(
        height=height, paper_bgcolor="#111318", plot_bgcolor="#111318",
        font=dict(color="#9aa0ad", size=11), margin=dict(l=18, r=18, t=22, b=18),
        showlegend=legend,
        legend=dict(orientation="h", y=1.14, x=1, xanchor="right",
                    font=dict(color="#c9ccd6", size=10)), hovermode="x unified")
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


def render():
    st.markdown("## 🚦 双动量 GEM · Global Equities Momentum")
    st.markdown(
        '<div style="font-size:12.5px;color:#c9ccd6;line-height:1.7;margin:-4px 0 6px">'
        'Gary Antonacci 的**双动量**:每月看两道过滤——**相对动量**(SPY vs 海外,谁强持谁)+ '
        '**绝对动量**(SPY vs 国库券,不及现金则**转持债券**)。目标不是跑赢,而是**用债券躲开大熊市**。'
        '</div>', unsafe_allow_html=True)

    close = _fetch_closes()
    if close is None or "SPY" not in getattr(close, "columns", []):
        st.markdown('<div class="alert-dn">Yahoo 数据暂不可用,稍后重试。</div>', unsafe_allow_html=True)
        return

    # ── 控件 ─────────────────────────────────────────────────────────
    k1, k2, k3 = st.columns(3)
    L = k1.radio("回看月数", [6, 9, 12], index=2, horizontal=True)
    exus = k2.radio("海外代理", ["VEU", "ACWX", "EFA"], index=0, horizontal=True)
    cash = k3.radio("现金基准", ["BIL", "^IRX"], index=0, horizontal=True)
    bond = "AGG"
    if exus == "EFA":
        st.caption("注:EFA = 发达市场(不含新兴);VEU/ACWX 含新兴市场。")

    # 单一月度网格:始终并入 BIL + ^IRX(稳健性网格两者都需要);只有所选股/债 sleeve 决定起点
    need = list(dict.fromkeys(["SPY", exus, bond, "BIL", "^IRX"]))
    if any(t not in close.columns for t in need):
        st.markdown('<div class="alert-dn">部分标的数据缺失,稍后重试。</div>', unsafe_allow_html=True)
        return
    m = E.to_monthly(close[need]).dropna(how="any")
    sig = E.build_signals(m, exus, bond, cash, L)
    strat, bench, eq_s, eq_b = E.backtest(m, sig, exus, bond)

    start_disc = m.index.min().date()
    fv = {t: close[t].dropna().index.min().date() for t in [exus, bond, "BIL"]}
    st.markdown(
        f'<div class="alert-warn">⚠️ Yahoo 实时·总回报收盘;成本/税/滑点<b>忽略</b>;'
        f'ETF 上市日截断历史 → 回测自 <b>{start_disc}</b> 起(海外 {fv[exus]}·债 {fv[bond]}·现金BIL {fv["BIL"]});'
        f'信号<b>滞后一月</b>(无未来函数);每月再平衡;研究用途,非投资建议。</div>',
        unsafe_allow_html=True)

    # ── ① 当前建议 ───────────────────────────────────────────────────
    last_t = sig.index[-1]
    hold = sig.at[last_t, "hold"]
    r_us, r_exus, r_cash = (sig.at[last_t, c] for c in ("r_us", "r_exus", "r_cash"))
    st.markdown("#### ① 本月建议(截至上一个月末,持有至下月)")
    if isinstance(hold, str):
        col = E.SLEEVE_COLOR[hold]
        risk = "风险偏好 <b>开</b>(SPY 12月 > 国库券)" if r_us > r_cash else \
               "风险偏好 <b>关</b>(SPY 12月 ≤ 国库券)→ 转债"
        winner = "SPY(美股)" if (r_us >= r_exus) else "海外"
        trace = (f"{risk};" + (f"相对赢家:{winner} → " if r_us > r_cash else "→ ")
                 + f"<b style='color:{col}'>持 {E.SLEEVE_CN[hold]}</b>")
        cc = st.columns([1.1, 1, 1, 1])
        cc[0].markdown(
            f'<div class="card" style="text-align:center;border-color:{col}">'
            f'<div style="font-size:11px;color:#5a6070">建议持有</div>'
            f'<div style="font-size:22px;font-weight:700;color:{col}">{E.SLEEVE_CN[hold]}</div>'
            f'<div style="font-size:10px;color:#5a6070">{last_t.date()}</div></div>',
            unsafe_allow_html=True)
        cc[1].metric("SPY 12月", f"{r_us*100:+.1f}%")
        cc[2].metric("海外 12月", f"{r_exus*100:+.1f}%")
        cc[3].metric("国库券 12月", f"{r_cash*100:+.1f}%")
        st.markdown(f'<div style="font-size:12px;color:#c9ccd6;margin-top:4px">🧭 {trace}</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="alert-warn">历史不足以形成信号(预热中)。</div>', unsafe_allow_html=True)

    if len(strat) < 24:
        st.markdown('<div class="alert-warn">可用月份不足 24,以下回测面板略过。</div>', unsafe_allow_html=True)
        _disclosure(sig)
        return

    # ── ② 动量分数走势 ───────────────────────────────────────────────
    st.markdown("#### ② 三条动量分数(阴影=风险关闭,SPY<国库券)")
    f2 = go.Figure()
    f2.add_trace(go.Scatter(x=sig.index, y=sig["r_us"] * 100, name="SPY 美股",
                            line=dict(color=E.SLEEVE_COLOR["US"], width=1.2)))
    f2.add_trace(go.Scatter(x=sig.index, y=sig["r_exus"] * 100, name="海外",
                            line=dict(color=E.SLEEVE_COLOR["EXUS"], width=1.2)))
    f2.add_trace(go.Scatter(x=sig.index, y=sig["r_cash"] * 100, name="国库券",
                            line=dict(color=E.SLEEVE_COLOR["BONDS"], width=1.2, dash="dot")))
    f2.add_hline(y=0, line_color="#3a3e4a")
    for s, e in _runs((sig["r_us"] < sig["r_cash"]).fillna(False)):
        f2.add_vrect(x0=s, x1=e, fillcolor="#e05555", opacity=0.08, line_width=0, layer="below")
    _dark(f2, height=300)
    f2.update_yaxes(title_text=f"{L}月回报 (%)")
    st.plotly_chart(f2, width="stretch", config=_PLOT_CFG)

    # ── ③ 历史持仓带 ─────────────────────────────────────────────────
    st.markdown("#### ③ 历史持仓(蓝=美股 · 绿=海外 · 黄=债券)")
    held = sig["hold"].reindex(strat.index).dropna()
    codemap = {"US": 0, "EXUS": 1, "BONDS": 2}
    z = [[codemap[h] for h in held]]
    ribbon = go.Figure(go.Heatmap(
        z=z, x=[d.date() for d in held.index], y=["持仓"],
        colorscale=[[0, E.SLEEVE_COLOR["US"]], [0.33, E.SLEEVE_COLOR["US"]],
                    [0.33, E.SLEEVE_COLOR["EXUS"]], [0.66, E.SLEEVE_COLOR["EXUS"]],
                    [0.66, E.SLEEVE_COLOR["BONDS"]], [1.0, E.SLEEVE_COLOR["BONDS"]]],
        zmin=0, zmax=2, showscale=False, xgap=0, ygap=0,
        hovertext=[[E.SLEEVE_CN[h] for h in held]], hoverinfo="text"))
    _dark(ribbon, height=120, legend=False)
    st.plotly_chart(ribbon, width="stretch", config=_PLOT_CFG)

    # ── ④ 净值曲线 vs SPY ────────────────────────────────────────────
    st.markdown("#### ④ 策略净值 vs SPY 买入持有")
    logy = st.checkbox("对数坐标", value=True, key="gem_log")
    f4 = go.Figure()
    f4.add_trace(go.Scatter(x=eq_s.index, y=eq_s.values, name="GEM 双动量",
                            line=dict(color="#e9f0e0", width=1.6)))
    f4.add_trace(go.Scatter(x=eq_b.index, y=eq_b.values, name="SPY 买入持有",
                            line=dict(color="#5a6070", width=1.2)))
    _dark(f4, height=330)
    f4.update_yaxes(title_text="净值(起点=1)", type="log" if logy else "linear")
    st.plotly_chart(f4, width="stretch", config=_PLOT_CFG)
    st.caption(f"曲线日期=决策月末,该月收益在下月实现·净值自 {start_disc} 归一化为 1。")

    # ── ⑤ 回撤 ───────────────────────────────────────────────────────
    ss, sb = E.stats(eq_s, strat), E.stats(eq_b, bench)
    st.markdown("#### ⑤ 回撤(水下曲线)")
    f5 = go.Figure()
    f5.add_trace(go.Scatter(x=ss["dd"].index, y=ss["dd"].values * 100, name="GEM",
                            fill="tozeroy", line=dict(color="#e05555", width=1)))
    f5.add_trace(go.Scatter(x=sb["dd"].index, y=sb["dd"].values * 100, name="SPY",
                            line=dict(color="#5a6070", width=1)))
    _dark(f5, height=240)
    f5.update_yaxes(title_text="回撤 (%)")
    st.plotly_chart(f5, width="stretch", config=_PLOT_CFG)

    # ── ⑥ 统计对比 ───────────────────────────────────────────────────
    st.markdown("#### ⑥ 统计对比(GEM vs SPY 买入持有)")
    pct, sw, tovr = E.occupancy(sig, strat)
    g = st.columns(5)
    g[0].metric("年化 CAGR", f"{ss['cagr']*100:.1f}%", f"SPY {sb['cagr']*100:.1f}%")
    g[1].metric("年化波动", f"{ss['vol']*100:.1f}%", f"SPY {sb['vol']*100:.1f}%", delta_color="inverse")
    g[2].metric("最大回撤", f"{ss['maxdd']*100:.1f}%", f"SPY {sb['maxdd']*100:.1f}%", delta_color="inverse")
    g[3].metric("Sharpe(rf=0)", f"{ss['sharpe0']:.2f}", f"SPY {sb['sharpe0']:.2f}")
    g[4].metric("年换手/月数", f"{tovr:.1f} 次", f"{ss['months']} 月")
    st.caption("双动量的价值在**最大回撤**远小于 SPY(用债券躲熊市),代价是牛市里 CAGR 可能略低。"
               "Sharpe 用算术均值分子、CAGR 为几何——两者口径不同,勿直接相减。")
    st.markdown(f'<div style="font-size:11px;color:#5a6070">持仓占比 · '
                + " · ".join(f"{E.SLEEVE_CN[k]} {v*100:.0f}%" for k, v in pct.items())
                + f" · 共切换 {sw} 次</div>", unsafe_allow_html=True)

    # ── ⑦ 稳健性网格 ─────────────────────────────────────────────────
    with st.expander("⑦ 稳健性网格(回看 6/9/12 × 现金 BIL/^IRX)"):
        st.dataframe(E.robustness(m, exus, bond), width="stretch", hide_index=True)
        st.caption("跨回看期表现稳健=非过拟合到 L=12;剧烈波动才说明脆弱。BIL 与 ^IRX 近乎一致 "
                   "= ^IRX 累计近似贴合 BIL 总回报。")

    _disclosure(sig)


def _disclosure(sig):
    with st.expander("查看每月信号明细(近 24 月)"):
        show = sig.tail(24).copy()
        for c in ("r_us", "r_exus", "r_cash"):
            show[c] = (show[c] * 100).round(1)
        show = show.rename(columns={"r_us": "SPY%", "r_exus": "海外%", "r_cash": "现金%", "hold": "持仓"})
        show["持仓"] = show["持仓"].map(lambda h: E.SLEEVE_CN.get(h, "—") if isinstance(h, str) else "—")
        st.dataframe(show, width="stretch")
    st.markdown(
        '<div class="alert-warn" style="font-size:11.5px;line-height:1.7">'
        '<b>诚实边界:</b>① 成本/税/滑点忽略(GEM 每年仅换手 ~1-2 次,但真实摩擦仍在);'
        '② 样本自 ~2008 起,完整熊市周期少(2008/2020/2022),CAGR/MaxDD 为短样本点估计;'
        '③ ^IRX 现金为近似(用前月末收益率月度累计);④ 绝对动量以 SPY 腿为闸门(书中口径),'
        '另有以相对赢家为闸门的变体,二者仅在 US<现金<海外 时不同;⑤ 研究/教育,非投资建议。</div>',
        unsafe_allow_html=True)
    st.markdown(
        "<div style='text-align:center;font-size:10px;color:#3a3e4a;padding:10px'>"
        "数据 yfinance 实时 · 成本已忽略 · ⚠️ 研究用途,非投资建议。</div>", unsafe_allow_html=True)
