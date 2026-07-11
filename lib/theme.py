"""暗色主题 CSS + Plotly 图表构建器（仪表盘、价格走势图）。"""
from __future__ import annotations

from datetime import datetime, timedelta

import plotly.graph_objects as go

# 默认强调色（黄金金色）；各品种可覆盖
DEFAULT_ACCENT = "#d4a520"

CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  .main { background: #0a0c10; }
  .block-container { padding: 1.2rem 2rem; }

  .kpi-box { background: #111318; border: 1px solid #1e2130; border-radius: 10px;
    padding: 14px 16px; text-align: left; }
  .kpi-label { font-size: 10px; color: #5a6070; text-transform: uppercase;
    letter-spacing: 0.08em; margin-bottom: 4px; }
  .kpi-val { font-size: 22px; font-weight: 700; font-family: monospace; }
  .kpi-sub { font-size: 11px; margin-top: 2px; }

  .card { background: #111318; border: 1px solid #1e2130; border-radius: 10px;
    padding: 16px; margin-bottom: 4px; }
  .card-title { font-size: 11px; color: #5a6070; text-transform: uppercase;
    letter-spacing: 0.08em; margin-bottom: 12px; font-weight: 600; }
  .ind-row { display: flex; justify-content: space-between; align-items: center;
    padding: 7px 0; border-bottom: 1px solid #1e2130; font-size: 12px; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 10px; font-weight: 600; text-transform: uppercase; }
  .badge-up   { background: rgba(61,186,106,.15); color: #3dba6a; }
  .badge-dn   { background: rgba(224,85,85,.15);  color: #e05555; }
  .badge-warn { background: rgba(224,128,48,.15); color: #e08030; }
  .badge-neu  { background: rgba(90,96,112,.2);   color: #5a6070; }

  .alert-up   { background: rgba(61,186,106,.08); border: 1px solid rgba(61,186,106,.3);
    border-radius: 7px; padding: 9px 13px; font-size: 12px; margin-bottom: 8px; }
  .alert-warn { background: rgba(224,128,48,.08); border: 1px solid rgba(224,128,48,.3);
    border-radius: 7px; padding: 9px 13px; font-size: 12px; margin-bottom: 8px; }
  .alert-dn   { background: rgba(224,85,85,.08);  border: 1px solid rgba(224,85,85,.3);
    border-radius: 7px; padding: 9px 13px; font-size: 12px; margin-bottom: 8px; }

  .inst-bar-bg { height: 5px; background: #1e2130; border-radius: 3px; margin-top: 3px; }
  .heat-cell   { border-radius: 7px; padding: 10px 12px; }

  .live-dot  { display:inline-block;width:7px;height:7px;border-radius:50%;
    background:#3dba6a;margin-right:5px;box-shadow:0 0 6px #3dba6a; }
  .sim-dot   { display:inline-block;width:7px;height:7px;border-radius:50%;
    background:#e08030;margin-right:5px; }

  .stButton > button { background: #181b22; border: 1px solid #1e2130; color: #c9ccd6;
    border-radius: 6px; font-size: 12px; }
  .stButton > button:hover { background: #232733; border-color: #3a3e4a; }

  div[data-testid="stMetric"] { background: #111318; border: 1px solid #1e2130;
    border-radius: 10px; padding: 12px 16px; }
  div[data-testid="stMetricLabel"] p { font-size: 10px !important; color: #5a6070 !important;
    text-transform: uppercase; }
  div[data-testid="stMetricValue"] { font-family: monospace; }

  footer { visibility: hidden; }
  #MainMenu { visibility: hidden; }
</style>
"""


def make_gauge(score: int, label: str, color: str) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={"font": {"size": 28, "color": "#e4e6ee", "family": "monospace"}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 0, "tickcolor": "#1e2130",
                     "tickvals": [0, 25, 50, 75, 100],
                     "ticktext": ["极空", "偏空", "中性", "看多", "极多"]},
            "bar": {"color": "#f0c040", "thickness": 0.25},
            "bgcolor": "#111318",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 20],   "color": "#7f1d1d"},
                {"range": [20, 40],  "color": "#991b1b"},
                {"range": [40, 60],  "color": "#5c3d00"},
                {"range": [60, 80],  "color": "#14532d"},
                {"range": [80, 100], "color": "#052e16"},
            ],
            "threshold": {"line": {"color": "#f0c040", "width": 3},
                          "thickness": 0.8, "value": score},
        },
        title={"text": f"<b style='color:{color}'>{label}</b>"
                       f"<br><span style='color:#5a6070;font-size:11px'>综合信号得分</span>",
               "font": {"size": 13}},
    ))
    fig.update_layout(height=220, margin=dict(l=20, r=20, t=40, b=10),
                      paper_bgcolor="#111318", font_color="#e4e6ee")
    return fig


def make_price_chart(history: list[float], dates: list[str], price: float,
                     accent: str = DEFAULT_ACCENT,
                     ma_ref: float | None = None, ma_label: str = "",
                     price_prefix: str = "$",
                     overlays: list[tuple[str, list, str]] | None = None) -> go.Figure:
    """overlays: [(名称, 序列(与 history 等长), 颜色)] —— 如 EMA30/50/200 叠加线。"""
    n = len(history)
    if not dates or len(dates) != n:
        dates = [(datetime.now() - timedelta(days=n - i)).strftime("%m/%d") for i in range(n)]

    fill = _hex_to_rgba(accent, 0.08)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=history, fill="tozeroy", fillcolor=fill,
        line=dict(color=accent, width=2), mode="lines", name="价格",
        hovertemplate="<b>%{x}</b><br>" + price_prefix + "%{y:,.2f}<extra></extra>",
    ))
    _has_overlay = False
    if overlays:
        for nm, series, col in overlays:
            if series and len(series) == n:
                _has_overlay = True
                fig.add_trace(go.Scatter(
                    x=dates, y=series, mode="lines", name=nm,
                    line=dict(color=col, width=1.1),
                    hovertemplate=nm + ": " + price_prefix + "%{y:,.2f}<extra></extra>",
                ))
    if ma_ref:
        fig.add_hline(y=ma_ref, line=dict(color="#e08030", dash="dash", width=1.5),
                      annotation_text=ma_label or f"MA {ma_ref:,.0f}",
                      annotation_position="top right",
                      annotation_font=dict(color="#e08030", size=10))
    fig.add_trace(go.Scatter(
        x=[dates[-1]], y=[price], mode="markers",
        marker=dict(color="#f0c040", size=10, line=dict(color="#0a0c10", width=2)),
        name="当前", hovertemplate=f"当前: {price_prefix}{price:,.2f}<extra></extra>",
    ))
    step = max(1, n // 6)
    fig.update_layout(
        height=220, margin=dict(l=10, r=10, t=10, b=30),
        paper_bgcolor="#111318", plot_bgcolor="#111318",
        font=dict(color="#5a6070", size=10), showlegend=False,
        xaxis=dict(showgrid=False, color="#5a6070", tickangle=0,
                   tickvals=dates[::step], ticktext=dates[::step]),
        yaxis=dict(showgrid=True, gridcolor="#1e2130", color="#5a6070",
                   tickprefix=price_prefix, tickformat=","),
        hovermode="x unified",
    )
    if _has_overlay:   # 有 EMA 等叠加线时显示横向小图例，便于辨认各线
        fig.update_layout(showlegend=True,
                          legend=dict(orientation="h", x=0, y=1.12,
                                      font=dict(size=9, color="#9aa0b0"),
                                      bgcolor="rgba(0,0,0,0)"))
    return fig


def make_bar(x: list, y: list, accent: str = DEFAULT_ACCENT, prefix: str = "$") -> go.Figure:
    """竖向柱状图（花费趋势）。"""
    fig = go.Figure(go.Bar(
        x=x, y=y, marker_color=accent,
        hovertemplate="%{x}<br>" + prefix + "%{y:,.2f}<extra></extra>"))
    fig.update_layout(
        height=240, margin=dict(l=10, r=10, t=10, b=30),
        paper_bgcolor="#111318", plot_bgcolor="#111318",
        font=dict(color="#5a6070", size=10), showlegend=False,
        xaxis=dict(showgrid=False, color="#5a6070"),
        yaxis=dict(showgrid=True, gridcolor="#1e2130", color="#5a6070",
                   tickprefix=prefix, tickformat=","))
    return fig


def make_hbar(labels: list, values: list, accent: str = DEFAULT_ACCENT,
              prefix: str = "$") -> go.Figure:
    """横向柱状图（按维度看消耗占比），按值升序使最大项在顶部。"""
    pairs = sorted(zip(values, labels))
    vals = [v for v, _ in pairs]
    labs = [l for _, l in pairs]
    fig = go.Figure(go.Bar(
        x=vals, y=labs, orientation="h", marker_color=accent,
        hovertemplate="%{y}<br>" + prefix + "%{x:,.2f}<extra></extra>"))
    fig.update_layout(
        height=max(220, 30 * len(labs) + 50), margin=dict(l=10, r=10, t=10, b=20),
        paper_bgcolor="#111318", plot_bgcolor="#111318",
        font=dict(color="#5a6070", size=10), showlegend=False,
        xaxis=dict(showgrid=True, gridcolor="#1e2130", color="#5a6070",
                   tickprefix=prefix, tickformat=","),
        yaxis=dict(color="#c9ccd6"))
    return fig


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"
