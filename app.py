import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import random
import time


# ── Page config ────────────────────────────────────────────
st.set_page_config(
    page_title="Au Watch · 黄金行情监控",
    page_icon="🥇",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  .main { background: #0a0c10; }
  .block-container { padding: 1.2rem 2rem; }

  .kpi-box {
    background: #111318; border: 1px solid #1e2130; border-radius: 10px;
    padding: 14px 16px; text-align: left;
  }
  .kpi-label { font-size: 10px; color: #5a6070; text-transform: uppercase;
    letter-spacing: 0.08em; margin-bottom: 4px; }
  .kpi-val   { font-size: 22px; font-weight: 700; font-family: monospace; }
  .kpi-sub   { font-size: 11px; margin-top: 2px; }

  .card {
    background: #111318; border: 1px solid #1e2130;
    border-radius: 10px; padding: 16px; margin-bottom: 4px;
  }
  .card-title {
    font-size: 11px; color: #5a6070; text-transform: uppercase;
    letter-spacing: 0.08em; margin-bottom: 12px; font-weight: 600;
  }
  .ind-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 7px 0; border-bottom: 1px solid #1e2130; font-size: 12px;
  }
  .badge {
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 10px; font-weight: 600; text-transform: uppercase;
  }
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

  .stButton > button {
    background: #181b22; border: 1px solid #1e2130; color: #f0c040;
    border-radius: 6px; font-size: 12px;
  }
  .stButton > button:hover { background: #8b6914; border-color: #d4a520; }

  div[data-testid="stMetric"] {
    background: #111318; border: 1px solid #1e2130;
    border-radius: 10px; padding: 12px 16px;
  }
  div[data-testid="stMetricLabel"] p { font-size: 10px !important; color: #5a6070 !important; text-transform: uppercase; }
  div[data-testid="stMetricValue"] { font-family: monospace; }

  footer { visibility: hidden; }
  #MainMenu { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Constants ───────────────────────────────────────────────
MACRO = {
    "cpi": 4.2, "ath": 5595, "year_ago": 3192, "ma200": 4480,
    "tips": 1.85, "dxy": 102.8, "rsi": 38, "etf_flow": -0.38,
    "hike_prob": 70, "cb_q1": 244,
}
INSTITUTIONS = [
    ("JPMorgan",       6000, "年末目标，下修自 $5,708"),
    ("富国银行",        6200, "最激进 $6,100–6,300"),
    ("高盛",            5400, "维持不变，最具韧性"),
    ("UBS 瑞银",        5500, "下修自 $5,900"),
    ("Morgan Stanley", 5200, "下修，仍看多结构"),
    ("LBMA 共识均价",  4742, "28位分析师全年均价"),
]
WATCHLIST = [
    ("白银 XAG/USD", 32.45, -0.82, False),
    ("黄金ETF GLD",  391.2, -0.35, False),
    ("黄金矿业 GDX",  38.9, -1.20, False),
    ("美元指数 DXY", 102.8,  0.18, False),
    ("美国10Y国债",   4.38,  0.03, True),
    ("原油 WTI",      99.8,  1.45, False),
]

# ── Session state ───────────────────────────────────────────
if "base_price" not in st.session_state:
    st.session_state.base_price = 4219.0
if "price_history" not in st.session_state:
    anchors = [
        4530,4503,4462,4410,4380,4320,4360,4344,4310,4290,
        4265,4083,4120,4150,4180,4219,4210,4195,4220,4205,
        4190,4215,4230,4219,4205,4190,4218,4210,4195,4219,
    ]
    st.session_state.price_history = [p + random.uniform(-15, 15) for p in anchors]
if "ai_analysis" not in st.session_state:
    st.session_state.ai_analysis = None
if "last_update" not in st.session_state:
    st.session_state.last_update = datetime.now()

# ── Helper functions ────────────────────────────────────────
def simulate_price(cur):
    drift = (random.random() - 0.48) * 12
    noise = (random.random() - 0.5) * 6
    return round(max(3800, min(4700, cur + drift + noise)), 2)

def calc_score(price):
    s = 50
    s += -10 if price < MACRO["ma200"] else 5
    rsi = MACRO["rsi"]
    s += 8 if rsi < 30 else (3 if rsi < 40 else (-8 if rsi > 70 else 0))
    s += 6 if MACRO["etf_flow"] > 0 else -4
    tips = MACRO["tips"]
    s += 8 if tips < 0 else (3 if tips < 1 else (-6 if tips > 2 else 0))
    s += -5 if MACRO["dxy"] > 105 else (5 if MACRO["dxy"] < 100 else 0)
    s += -6 if MACRO["hike_prob"] > 60 else (6 if MACRO["hike_prob"] < 30 else 0)
    s += 5
    if (MACRO["ath"] - price) / MACRO["ath"] > 0.2:
        s += 5
    return max(5, min(95, round(s)))

def score_label(score):
    if score >= 65: return "积极看多", "#3dba6a"
    if score >= 50: return "温和看多", "#3dba6a"
    if score >= 40: return "中性观望", "#e08030"
    if score >= 30: return "偏空谨慎", "#e08030"
    return "明显看空", "#e05555"

def fmt(n): return f"${n:,.0f}"

# ── Gauge chart ─────────────────────────────────────────────
def make_gauge(score):
    slabel, scolor = score_label(score)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={"font": {"size": 28, "color": "#e4e6ee", "family": "monospace"}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 0, "tickcolor": "#1e2130",
                     "tickvals": [0, 25, 50, 75, 100],
                     "ticktext": ["极空", "偏空", "中性", "看多", "极多"]},
            "bar":  {"color": "#f0c040", "thickness": 0.25},
            "bgcolor": "#111318",
            "borderwidth": 0,
            "steps": [
                {"range": [0,  20], "color": "#7f1d1d"},
                {"range": [20, 40], "color": "#991b1b"},
                {"range": [40, 60], "color": "#5c3d00"},
                {"range": [60, 80], "color": "#14532d"},
                {"range": [80,100], "color": "#052e16"},
            ],
            "threshold": {"line": {"color": "#f0c040", "width": 3},
                          "thickness": 0.8, "value": score},
        },
        title={"text": f"<b style='color:{scolor}'>{slabel}</b><br><span style='color:#5a6070;font-size:11px'>综合信号得分</span>",
               "font": {"size": 13}},
    ))
    fig.update_layout(
        height=220, margin=dict(l=20, r=20, t=40, b=10),
        paper_bgcolor="#111318", font_color="#e4e6ee",
    )
    return fig

# ── Price chart ─────────────────────────────────────────────
def make_price_chart(history, price, ma200):
    dates = [(datetime.now() - timedelta(days=len(history)-i)).strftime("%m/%d")
             for i in range(len(history))]
    prices = history[:]

    fig = go.Figure()
    # Fill
    fig.add_trace(go.Scatter(
        x=dates, y=prices, fill="tozeroy",
        fillcolor="rgba(212,165,32,0.08)", line=dict(color="#d4a520", width=2),
        mode="lines", name="金价",
        hovertemplate="<b>%{x}</b><br>$%{y:,.0f}<extra></extra>",
    ))
    # MA200 line
    fig.add_hline(y=ma200, line=dict(color="#e08030", dash="dash", width=1.5),
                  annotation_text=f"MA200 ${ma200:,}", annotation_position="top right",
                  annotation_font=dict(color="#e08030", size=10))
    # Current dot
    fig.add_trace(go.Scatter(
        x=[dates[-1]], y=[price], mode="markers",
        marker=dict(color="#f0c040", size=10, line=dict(color="#0a0c10", width=2)),
        name="当前", hovertemplate=f"当前: ${price:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        height=220, margin=dict(l=10, r=10, t=10, b=30),
        paper_bgcolor="#111318", plot_bgcolor="#111318",
        font=dict(color="#5a6070", size=10),
        showlegend=False,
        xaxis=dict(showgrid=False, color="#5a6070", tickangle=0,
                   tickvals=dates[::5], ticktext=dates[::5]),
        yaxis=dict(showgrid=True, gridcolor="#1e2130", color="#5a6070",
                   tickprefix="$", tickformat=","),
        hovermode="x unified",
    )
    return fig

# ── 规则引擎分析（无需任何 API，完全免费）──────────────────
def rule_based_analysis(price, score):
    ma200    = MACRO["ma200"]
    rsi      = MACRO["rsi"]
    etf      = MACRO["etf_flow"]
    tips     = MACRO["tips"]
    dxy      = MACRO["dxy"]
    hike     = MACRO["hike_prob"]
    from_ath = (price - MACRO["ath"]) / MACRO["ath"] * 100
    upside   = (5400 - price) / price * 100

    # ── 第一段：当前形势判断 ──────────────────────────────────
    if score >= 60:
        trend = "积极"
        trend_desc = f"黄金当前综合信号偏多（得分 {score}/100）"
    elif score >= 45:
        trend = "中性"
        trend_desc = f"黄金当前信号中性偏弱（得分 {score}/100）"
    else:
        trend = "偏空"
        trend_desc = f"黄金当前综合信号偏空（得分 {score}/100）"

    ma_status = f"价格{'高于' if price > ma200 else '低于'}200日均线（${ma200:,}）" + \
                ("，技术面维持多头结构。" if price > ma200 else "，技术面已转为偏空，需警惕进一步下行。")

    ath_text = f"金价较年初历史高点 $5,595 已回调 {abs(from_ath):.1f}%，" + \
               ("具备一定安全边际，机构目标价中位 $5,400 较当前仍有 {:.0f}% 上行空间。".format(upside)
                if upside > 0 else "已超越机构目标价中位 $5,400。")

    para1 = f"{trend_desc}。{ma_status}{ath_text}"

    # ── 第二段：核心风险 ─────────────────────────────────────
    risks = []
    if hike > 60:
        risks.append(f"美联储12月再度加息概率达 {hike}%，持有不生息黄金的机会成本上升")
    if etf < -0.2:
        risks.append(f"黄金ETF本周净流出 {abs(etf):.2f} MOz，西方机构资金持续撤离，短期动量不足")
    if dxy > 103:
        risks.append(f"美元指数 DXY 维持在 {dxy} 高位，对金价形成持续压制")
    if tips > 1.5:
        risks.append(f"10年期TIPS实际利率 {tips}% 处于高位，持金机会成本较大")
    if price < ma200:
        risks.append("金价跌破200日均线，可能触发更多技术性抛压")
    if not risks:
        risks.append("当前主要宏观风险已相对充分定价，需警惕地缘局势超预期缓和")

    para2 = "当前最值得关注的风险：" + "；".join(risks[:3]) + "。"

    # ── 第三段：一句话建议 ───────────────────────────────────
    if score >= 60 and price < ma200 * 0.98:
        advice = "结构性多头逻辑完整，当前回调区间适合长线投资者分批左侧建仓，控制仓位在总资产15%以内，切勿一次性满仓。"
    elif score >= 60 and price >= ma200:
        advice = "技术面与基本面共振向好，可维持多头仓位，但需在 FOMC 等关键节点前适度控制仓位敞口。"
    elif score >= 45:
        advice = f"当前信号中性，FOMC（6/16-17）结果将是近期最大方向性催化剂，建议等待结果明朗后再做仓位决策，不宜追涨或追空。"
    elif rsi < 32:
        advice = "RSI 已进入超卖区间，短线存在技术性反弹机会，但趋势未明前不建议重仓，可小仓试探并严设止损。"
    else:
        advice = "当前多项指标偏空，建议以观望为主，等待金价企稳、ETF资金重新净流入后，再考虑逢低布局。"

    return para1, para2, advice

# ════════════════════════════════════════════════════════════
# ── MAIN UI ─────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════

# Header
col_logo, col_time, col_btn = st.columns([3, 2, 1])
with col_logo:
    st.markdown("## 🥇 Au Watch · 黄金行情监控")
with col_time:
    st.markdown(f"<div style='color:#5a6070;font-size:12px;padding-top:18px'>更新于 {st.session_state.last_update.strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)
with col_btn:
    if st.button("⟳ 刷新行情", use_container_width=True):
        st.session_state.base_price = simulate_price(st.session_state.base_price)
        st.session_state.price_history.append(st.session_state.base_price)
        if len(st.session_state.price_history) > 60:
            st.session_state.price_history.pop(0)
        st.session_state.last_update = datetime.now()
        st.rerun()

st.divider()

price  = st.session_state.base_price
score  = calc_score(price)
slabel, scolor = score_label(score)
change = price - st.session_state.price_history[-2] if len(st.session_state.price_history) > 1 else 0
change_pct = (change / (price - change) * 100) if (price - change) else 0
from_ath = (price - MACRO["ath"]) / MACRO["ath"] * 100
yoy = price - MACRO["year_ago"]
yoy_pct = yoy / MACRO["year_ago"] * 100
upside = (5400 - price) / price * 100

# ── KPI Strip ───────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.metric("现货价格 XAU/USD", fmt(price),
              f"{'+' if change>=0 else ''}{change:.0f} ({change_pct:+.2f}%)")
with k2:
    st.metric("距年初高点 ATH", f"{from_ath:.1f}%", "ATH $5,595（1月28日）")
with k3:
    st.metric("年同比涨幅", f"+${yoy:,.0f}", f"同比 +{yoy_pct:.1f}%")
with k4:
    st.metric("机构目标价中位", "$5,400", f"↑ 上行空间 +{upside:.0f}%")
with k5:
    st.metric("市场情绪", slabel, f"综合得分 {score}/100")

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

# ── Alerts ──────────────────────────────────────────────────
if price < MACRO["ma200"]:
    st.markdown(f'<div class="alert-warn">⚠️ 金价 ({fmt(price)}) 跌破200日均线（${MACRO["ma200"]:,}），技术面偏空，需警惕趋势确认。</div>', unsafe_allow_html=True)
if MACRO["etf_flow"] < -0.3:
    st.markdown(f'<div class="alert-dn">📉 黄金ETF本周净流出 {abs(MACRO["etf_flow"])} MOz，机构资金持续撤离，短期动量不佳。</div>', unsafe_allow_html=True)
if MACRO["hike_prob"] > 60:
    st.markdown(f'<div class="alert-warn">🏦 CME定价12月再度加息概率 {MACRO["hike_prob"]}%，FOMC（6/16-17）是本月最大催化剂。</div>', unsafe_allow_html=True)
if MACRO["cb_q1"] >= 200:
    st.markdown(f'<div class="alert-up">✅ Q1全球央行净购金 {MACRO["cb_q1"]} 吨（高于五年均值），结构性需求底盘稳固。</div>', unsafe_allow_html=True)

# ── Row 1: Chart + Gauge ────────────────────────────────────
ch_col, ga_col = st.columns([3, 2])
with ch_col:
    st.markdown('<div class="card"><div class="card-title">价格走势（近30日）· 橙色虚线 = MA200</div>', unsafe_allow_html=True)
    st.plotly_chart(make_price_chart(st.session_state.price_history, price, MACRO["ma200"]),
                    use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

with ga_col:
    st.markdown('<div class="card"><div class="card-title">综合信号仪表盘</div>', unsafe_allow_html=True)
    st.plotly_chart(make_gauge(score), use_container_width=True, config={"displayModeBar": False})

    # Indicators table
    indicators = [
        ("200日均线", fmt(MACRO["ma200"]),
         ("下方 看空","badge-dn") if price < MACRO["ma200"] else ("上方 看多","badge-up")),
        ("RSI (14)", str(MACRO["rsi"]),
         ("超卖","badge-up") if MACRO["rsi"]<30 else (("偏弱","badge-warn") if MACRO["rsi"]<45 else (("超买","badge-dn") if MACRO["rsi"]>70 else ("中性","badge-neu")))),
        ("美元指数 DXY", str(MACRO["dxy"]),
         ("强势 压制","badge-dn") if MACRO["dxy"]>105 else (("弱势 利好","badge-up") if MACRO["dxy"]<99 else ("中性","badge-warn"))),
        ("10Y TIPS", f"{MACRO['tips']}%",
         ("负利率 极佳","badge-up") if MACRO["tips"]<0 else (("低利率 利好","badge-up") if MACRO["tips"]<1 else (("高利率 压制","badge-dn") if MACRO["tips"]>2 else ("中性偏空","badge-warn")))),
        ("ETF资金(本周)", f"{MACRO['etf_flow']:+.2f} MOz",
         ("强净流入","badge-up") if MACRO["etf_flow"]>0.3 else (("小幅流入","badge-up") if MACRO["etf_flow"]>0 else (("小幅流出","badge-warn") if MACRO["etf_flow"]>-0.2 else ("明显流出","badge-dn")))),
    ]
    rows_html = ""
    for name, val, (badge_text, badge_cls) in indicators:
        rows_html += f"""<div class="ind-row">
            <span style="color:#5a6070">{name}</span>
            <span style="font-family:monospace;font-size:12px">{val}</span>
            <span class="badge {badge_cls}">{badge_text}</span>
        </div>"""
    st.markdown(rows_html, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ── Row 2: Strategy + AI ────────────────────────────────────
strat_col, ai_col = st.columns(2)

with strat_col:
    st.markdown('<div class="card"><div class="card-title">投资策略推荐</div>', unsafe_allow_html=True)
    tab_long, tab_mid, tab_short, tab_hold = st.tabs(["🟢 长线 >12月", "🟡 中线 3-6月", "🔴 短线 <1月", "🔵 已持仓者"])
    stop_l  = round(price * 0.92)
    entry2  = round(price * 0.95)

    with tab_long:
        entry_rating = "⭐⭐⭐ 可以分批建仓" if price >= MACRO["ma200"] else "⭐⭐ 等待或小仓试探"
        st.markdown(f"""
- **当前入场评级：** {entry_rating}
- **建仓策略：** 将资金分4份，每隔4-6周买入一份，首批本周起始
- **仓位上限：** 黄金占总投资组合不超过 **15%**
- **机构目标价中位 $5,400**，较当前上行约 **+{upside:.0f}%**（12个月维度）
- **止损参考：** 若月度收盘跌破 **$3,500**，需重新评估整体逻辑
- **低成本加仓点：** 若下探至 **${entry2:,}**（-5%），可加大第二批力度
        """)
    with tab_mid:
        st.markdown(f"""
- **关键节点：** 等待 **6月16-17日 FOMC** 结果落地，不提前押注方向
- **看多触发：** 若Warsh暗示暂停加息 → 金价有望快速反弹至 **$4,500+**，届时右侧入场
- **看空触发：** 若确认12月加息 → 等待下探至 **$3,800–$3,900** 再建仓
- **目标价位：** $4,700–$5,000（3-6个月）；LBMA全年均价共识 $4,742
- **止损：** 入场后跌破 **${stop_l:,}**（入场价-8%）触发止损
        """)
    with tab_short:
        st.markdown(f"""
- ⛔ **当前不建议短线做多：** 跌破200均线 + ETF净流出 + FOMC方向未明
- **若必须操作：** 严格小仓（≤2%资金），设硬止损 **${stop_l:,}**
- **观察指标：** 实时跟踪 DXY 和 10Y TIPS 实际利率（与金价反向）
- **可做空机会：** 若FOMC后DXY突破106，金价可能短线下探 $3,900
- ⚠️ 短线做空需专业知识和严格风险管理，新手请谨慎
        """)
    with tab_hold:
        st.markdown(f"""
- **持仓评估：** 若入场成本低于 $4,000，目前仍在浮盈区间，无需恐慌
- **持有逻辑检验：** 央行需求稳固，LBMA全年均价共识 $4,742 仍高于当前价
- **减仓时机：** 若价格快速反弹至 **$4,700–$5,000**，可考虑减持30%锁定利润
- **止损纪律：** 若成本在 $4,200+ 且当前浮亏，跌破 **$3,800** 必须执行止损
- **组合再平衡：** 黄金占比超过总资产15%，建议逢高逐步减至目标仓位
        """)
    st.markdown('</div>', unsafe_allow_html=True)

with ai_col:
    st.markdown('<div class="card"><div class="card-title">📊 智能行情分析（规则引擎）</div>', unsafe_allow_html=True)

    if st.button("🔄 重新分析", use_container_width=True):
        st.session_state.ai_analysis = None

    if st.session_state.ai_analysis is None:
        st.session_state.ai_analysis = rule_based_analysis(price, score)

    para1, para2, advice = st.session_state.ai_analysis

    st.markdown("**当前形势**")
    st.markdown(para1)
    st.markdown("---")
    st.markdown("**主要风险**")
    st.markdown(para2)
    st.markdown("---")
    st.markdown("**投资者建议**")
    st.info(advice)

    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ── Row 3: Institutions + Heatmap + Watchlist ───────────────
inst_col, heat_col, watch_col = st.columns(3)

with inst_col:
    st.markdown('<div class="card"><div class="card-title">机构目标价</div>', unsafe_allow_html=True)
    for name, target, note in INSTITUTIONS:
        pct = round((target - price) / price * 100)
        bar_w = round(target / 6300 * 100)
        color = "#4ade80" if pct > 20 else ("#fbbf24" if pct > 10 else "#f87171")
        st.markdown(f"""
        <div style="margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px">
            <span style="color:#5a6070">{name}</span>
            <span style="font-family:monospace;color:#f0c040">${target:,} <span style="color:{color};font-size:10px">(+{pct}%)</span></span>
          </div>
          <div class="inst-bar-bg"><div style="height:5px;width:{bar_w}%;background:linear-gradient(90deg,#8b6914,#f0c040);border-radius:3px"></div></div>
          <div style="font-size:9px;color:#5a6070;margin-top:2px">{note}</div>
        </div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with heat_col:
    st.markdown('<div class="card"><div class="card-title">风险因子热力图</div>', unsafe_allow_html=True)
    factors = [
        ("美联储鹰派风险", "高", 80, "#e05555"),
        ("通胀粘性支撑",   "强", 75, "#3dba6a"),
        ("央行结构需求",   "强", 85, "#3dba6a"),
        ("ETF资金流入",    "弱", 25, "#e05555"),
        ("美元走强压力",   "高", 70, "#e05555"),
        ("地缘风险溢价",   "中", 60, "#e08030"),
    ]
    cols = st.columns(2)
    for i, (label, val, pct, color) in enumerate(factors):
        with cols[i % 2]:
            st.markdown(f"""
            <div class="heat-cell" style="background:{color}18;margin-bottom:8px">
              <div style="font-size:10px;color:rgba(255,255,255,.5)">{label}</div>
              <div style="font-size:14px;font-weight:700;color:{color}">{val}</div>
              <div style="height:3px;background:rgba(255,255,255,.1);border-radius:2px;margin-top:4px">
                <div style="height:100%;width:{pct}%;background:{color};opacity:.7;border-radius:2px"></div>
              </div>
            </div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with watch_col:
    st.markdown('<div class="card"><div class="card-title">相关资产监控</div>', unsafe_allow_html=True)
    for name, wprice, chg, is_rate in WATCHLIST:
        up = chg >= 0
        val_str = f"{wprice:.2f}%" if is_rate else f"${wprice:.2f}"
        chg_str = f"{'+'if up else ''}{chg:.2f}{'bp' if is_rate else '%'}"
        chg_color = "#3dba6a" if up else "#e05555"
        st.markdown(f"""
        <div style="display:flex;justify-content:space-between;align-items:center;
                    padding:8px 0;border-bottom:1px solid #1e2130">
          <span style="font-size:12px">{name}</span>
          <div style="text-align:right">
            <div style="font-family:monospace;font-size:12px">{val_str}</div>
            <div style="font-size:10px;color:{chg_color}">{chg_str}</div>
          </div>
        </div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ── Footer ──────────────────────────────────────────────────
st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
st.markdown("""<div style='text-align:center;font-size:10px;color:#3a3e4a;padding:8px'>
⚠️ 本工具仅供参考，不构成投资建议。黄金投资存在本金损失风险，请结合自身风险承受能力审慎决策。
</div>""", unsafe_allow_html=True)
