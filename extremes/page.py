"""极值追踪页面 —— 由投资面板顶部导航进入。数据 100% yfinance 实时拉取。"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from . import compute as C

_PLOT_CFG = {"displayModeBar": False}


@st.cache_data(ttl=86400, show_spinner="拉取行情中…(首次约 10 秒,之后走缓存)")
def _fetch():
    try:
        import yfinance as yf
    except Exception:
        return None, None
    try:
        df = yf.download(C.FETCH_TK, start="2010-01-01", interval="1d",
                         auto_adjust=True, progress=False)
    except Exception:
        return None, None
    if df is None or len(df) == 0:
        return None, None
    if not isinstance(df.columns, pd.MultiIndex):
        return None, None
    return df["Close"], df["Volume"]


def render():
    st.markdown("## 🎯 宏观流动性与资产历史极值追踪")
    st.markdown(
        '<div style="font-size:12.5px;color:#c9ccd6;line-height:1.7;margin:-4px 0 6px">'
        '把黄金 / 比特币 / 纳指的**历史大顶大底**,和当时的**成交量异常、风险偏好(RORO)、'
        '策展宏观事件**对照起来——看大资金在极值点如何进退。</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="alert-warn">⚠️ regime 温度计为**运行时因果合成**(价格离均线 + 成交量异常 + '
        '动量 + 风险偏好 的标准化均值);本地研究工具里的 walk-forward 事件研究回测证明该类分数'
        '**对未来回撤无稳定预测力**——当**描述性 regime 温度计**看,非择时信号,不构成投资建议。</div>',
        unsafe_allow_html=True)

    closes, vols = _fetch()
    if closes is None or any(t not in closes.columns for t in C.ASSETS.values()):
        st.markdown('<div class="alert-dn">Yahoo 行情拉取失败或数据不足,稍后重试。</div>',
                    unsafe_allow_html=True)
        return

    closes_all = {k: closes[v] for k, v in C.ASSETS.items()}
    asset = st.radio("资产", list(C.ASSETS.keys()),
                     format_func=lambda k: f"{C.ASSET_CN[k]} ({C.ASSETS[k]})", horizontal=True)
    close = closes[C.ASSETS[asset]]
    vol = vols[C.VOL_PROXY[asset]] if C.VOL_PROXY[asset] in vols.columns else close * 0
    f = C.build(asset, close, vol, closes_all).dropna(subset=["close"])
    if f.empty:
        st.markdown('<div class="alert-dn">该资产历史不足。</div>', unsafe_allow_html=True)
        return
    cur = f.iloc[-1]

    # 当前快照
    m = st.columns(5)
    m[0].metric("现价", f"{cur['close']:,.0f}")
    m[1].metric("距历史高", f"{cur['dd']*100:+.1f}%")
    m[2].metric("温度计 (σ)", f"{cur['gauge']:+.2f}",
                "TOP 观察" if cur["gauge"] >= C.HI else ("BOTTOM 观察" if cur["gauge"] <= C.LO else "中性"))
    m[3].metric("成交量异常 vol_z", f"{cur['vol_z']:+.2f}")
    m[4].metric("风险偏好 RORO", f"{cur['roro']:+.2f}")

    ev = C.events_df(asset)
    ev = ev[(ev["date"] >= f.index.min()) & (ev["date"] <= f.index.max())]

    # ── 三联图(共享 x)────────────────────────────────────────────────
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                        row_heights=[0.46, 0.30, 0.24],
                        subplot_titles=[f"{C.ASSET_CN[asset]} 价格(对数)+ TOP/BOTTOM 观察投影",
                                        "regime 温度计(合成,±0.8 观察带)",
                                        "成交量异常 vol_z + 风险偏好 RORO(σ)"])
    # traces FIRST(plotly:子图无 trace 时先加的 shape 会被丢弃)
    fig.add_trace(go.Scatter(x=f.index, y=f["close"], name="价格",
                             line=dict(width=1, color="#4d8fdb"), showlegend=False), row=1, col=1)
    ath_hits = f.index[f["close"] >= f["ath"] * 0.999]
    fig.add_trace(go.Scatter(x=ath_hits, y=f.loc[ath_hits, "close"], mode="markers",
                             marker=dict(size=3, color="#e8a23d"), name="历史新高",
                             hoverinfo="skip", showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=f.index, y=f["gauge"], name="温度计",
                             line=dict(width=1, color="#4d8fdb"), showlegend=False), row=2, col=1)
    fig.add_trace(go.Bar(x=f.index, y=f["vol_z"], name="vol_z",
                         marker_color="#74c0fc", opacity=0.5), row=3, col=1)
    fig.add_trace(go.Scatter(x=f.index, y=f["roro"], name="RORO",
                             line=dict(width=1.2, color="#e8853d")), row=3, col=1)

    # decorations AFTER traces（WATCH 底色:合并+去噪,避免上百个碎片矩形拖慢渲染）
    for s, e in C.watch_spans(f["gauge"], C.HI, above=True):
        fig.add_vrect(x0=s, x1=e, fillcolor="#e05555", opacity=0.07, line_width=0, layer="below", row=1, col=1)
    for s, e in C.watch_spans(f["gauge"], C.LO, above=False):
        fig.add_vrect(x0=s, x1=e, fillcolor="#3dba6a", opacity=0.07, line_width=0, layer="below", row=1, col=1)
    fig.update_yaxes(type="log", title_text="价格(对数)", row=1, col=1)
    fig.add_hrect(y0=C.HI, y1=2.6, fillcolor="#e05555", opacity=0.08, line_width=0, layer="below", row=2, col=1)
    fig.add_hrect(y0=-2.6, y1=C.LO, fillcolor="#3dba6a", opacity=0.08, line_width=0, layer="below", row=2, col=1)
    fig.add_hline(y=C.HI, line_dash="dot", line_color="#e05555", row=2, col=1)
    fig.add_hline(y=C.LO, line_dash="dot", line_color="#3dba6a", row=2, col=1)
    fig.add_hline(y=0, line_color="#3a3e4a", row=2, col=1)
    fig.update_yaxes(title_text="σ", range=[-2.4, 2.4], row=2, col=1)
    fig.add_hline(y=2, line_dash="dot", line_color="#5a6070", row=3, col=1)
    fig.add_hline(y=0, line_color="#3a3e4a", row=3, col=1)
    fig.update_yaxes(title_text="σ", range=[-3.5, 6], row=3, col=1)
    for _, e in ev.iterrows():
        color = C.ev_color(e["type"])
        for r in range(1, 4):
            kw = dict(annotation_text=e["id"], annotation_position="top",
                      annotation_font_size=8, annotation_textangle=-90) if r == 1 else {}
            fig.add_vline(x=e["date"], line_dash="dash", line_color=color,
                          opacity=0.5, row=r, col=1, **kw)

    fig.update_layout(height=760, paper_bgcolor="#111318", plot_bgcolor="#111318",
                      font=dict(color="#9aa0ad", size=11), margin=dict(l=18, r=18, t=40, b=18),
                      hovermode="x unified", barmode="overlay", showlegend=False)
    fig.update_xaxes(gridcolor="#1e2130", color="#5a6070")
    fig.update_yaxes(gridcolor="#1e2130", color="#5a6070")
    st.plotly_chart(fig, width="stretch", config=_PLOT_CFG)
    st.caption("红虚线=历史顶部事件 · 绿虚线=历史底部事件 · 灰=政策转向/冲击 · "
               "价格图红/绿底=温度计处于 TOP/BOTTOM 观察 · 橙点=历史新高。")

    # ── 策展事件表 ───────────────────────────────────────────────────
    st.markdown(f"#### 📅 {C.ASSET_CN[asset]} 策展事件")
    show = ev.copy()
    show["date"] = show["date"].dt.date
    show = show.rename(columns={"date": "日期", "type": "类型", "trigger": "宏观触发", "rotation": "资金轮动"})
    st.dataframe(show[["日期", "类型", "宏观触发", "资金轮动"]], width="stretch", hide_index=True)

    st.markdown(
        '<div class="alert-warn" style="font-size:11.5px;line-height:1.7">'
        '<b>诚实边界:</b>① 温度计是运行时因果合成的**描述性温度计**,非本地那套事件研究回测分数;'
        '② 回测结论:该类价格特征对未来回撤**无稳定样本外预测力**,勿当择时信号;'
        '③ ^NDX 无量 → 借用 QQQ 成交量,黄金借 GLD;④ 2025+ 事件为待核验;⑤ 研究/教育,非投资建议。</div>',
        unsafe_allow_html=True)
    st.markdown(
        "<div style='text-align:center;font-size:10px;color:#3a3e4a;padding:10px'>"
        "数据 yfinance 实时 · 温度计为描述性合成 · ⚠️ 研究用途,不构成投资建议。</div>",
        unsafe_allow_html=True)
