"""黄金（XAU/USD）—— 由原 app.py 迁移而来，接入实时数据 + 统一 Snapshot 接口。"""
from __future__ import annotations

from lib import data, indicators
from lib.model import (Snapshot, Indicator, Strategy, Related, KPI, Alert,
                       score_label, clamp_score)
from .base import AssetModule

# 编辑性/低频宏观输入（无免费实时源，作为可调上下文）
MACRO = {
    "ath": 5595, "year_ago": 3192, "ma200_fallback": 4480,
    "tips_fallback": 1.85, "dxy_fallback": 102.8, "rsi_fallback": 38,
    "etf_flow": -0.38, "hike_prob": 70, "cb_q1": 244, "inst_median": 5400,
}
ANCHORS = [4530, 4503, 4462, 4410, 4380, 4320, 4360, 4344, 4310, 4290,
           4265, 4083, 4120, 4150, 4180, 4219, 4210, 4195, 4220, 4205,
           4190, 4215, 4230, 4219, 4205, 4190, 4218, 4210, 4195, 4219]
INSTITUTIONS = [
    ("JPMorgan", 6000, "年末目标，下修自 $5,708"),
    ("富国银行", 6200, "最激进 $6,100–6,300"),
    ("高盛", 5400, "维持不变，最具韧性"),
    ("UBS 瑞银", 5500, "下修自 $5,900"),
    ("Morgan Stanley", 5200, "下修，仍看多结构"),
    ("LBMA 共识均价", 4742, "28位分析师全年均价"),
]


class GoldModule(AssetModule):
    id = "gold"
    name = "黄金 XAU/USD"
    icon = "🥇"
    accent = "#d4a520"
    price_prefix = "$"
    price_decimals = 0

    def build_snapshot(self, refresh: bool = False) -> Snapshot:
        closes, dates, live = self.series_or_sim("GC=F", ANCHORS, period="1y", refresh=refresh)
        price = closes[-1]

        ma200 = indicators.sma(closes, 200) if live and len(closes) >= 60 else MACRO["ma200_fallback"]
        rsi = indicators.rsi(closes, 14) if live and len(closes) >= 15 else MACRO["rsi_fallback"]
        dxy = data.yf_last("DX-Y.NYB") or MACRO["dxy_fallback"]
        tips = data.fred_latest("DFII10", data.secret("FRED_API_KEY")) or MACRO["tips_fallback"]
        etf, hike = MACRO["etf_flow"], MACRO["hike_prob"]

        change = closes[-1] - closes[-2] if len(closes) > 1 else 0.0
        change_pct = (change / closes[-2] * 100) if len(closes) > 1 and closes[-2] else 0.0
        from_ath = (price - MACRO["ath"]) / MACRO["ath"] * 100
        yoy = price - MACRO["year_ago"]
        upside = (MACRO["inst_median"] - price) / price * 100

        score = self._score(price, ma200, rsi, etf, tips, dxy, hike)
        slabel, scolor = score_label(score)

        # 图表只展示近 60 日
        chart_closes, chart_dates = closes[-60:], dates[-60:]

        kpis = [
            KPI("现货价格 XAU/USD", self.fmt_price(price),
                f"{'+' if change >= 0 else ''}{change:.0f} ({change_pct:+.2f}%)"),
            KPI("距年初高点 ATH", f"{from_ath:.1f}%", "ATH $5,595（1月28日）"),
            KPI("年同比涨幅", f"+${yoy:,.0f}", f"同比 +{yoy / MACRO['year_ago'] * 100:.1f}%"),
            KPI("机构目标价中位", "$5,400", f"↑ 上行空间 +{upside:.0f}%"),
            KPI("市场情绪", slabel, f"综合得分 {score}/100"),
        ]

        alerts = []
        if price < ma200:
            alerts.append(Alert("alert-warn", f"⚠️ 金价 ({self.fmt_price(price)}) 跌破均线参考（${ma200:,.0f}），技术面偏空。"))
        if etf < -0.3:
            alerts.append(Alert("alert-dn", f"📉 黄金ETF本周净流出 {abs(etf)} MOz，机构资金持续撤离。"))
        if hike > 60:
            alerts.append(Alert("alert-warn", f"🏦 CME定价12月再度加息概率 {hike}%，FOMC 是本月最大催化剂。"))
        if MACRO["cb_q1"] >= 200:
            alerts.append(Alert("alert-up", f"✅ Q1全球央行净购金 {MACRO['cb_q1']} 吨（高于五年均值），结构性需求稳固。"))

        indis = [
            Indicator("均线参考 (MA200)", f"${ma200:,.0f}",
                      *("下方 看空", "badge-dn") if price < ma200 else ("上方 看多", "badge-up")),
            Indicator("RSI (14)", f"{rsi:.0f}",
                      *self._rsi_badge(rsi)),
            Indicator("美元指数 DXY", f"{dxy:.1f}",
                      *("强势 压制", "badge-dn") if dxy > 105 else (("弱势 利好", "badge-up") if dxy < 99 else ("中性", "badge-warn"))),
            Indicator("10Y TIPS", f"{tips:.2f}%",
                      *self._tips_badge(tips)),
            Indicator("ETF资金(本周)", f"{etf:+.2f} MOz",
                      *("小幅流出", "badge-warn") if etf > -0.2 else ("明显流出", "badge-dn")),
        ]
        m = self.macd_row(closes)
        if m:
            indis.append(m)

        stop_l, entry2 = round(price * 0.92), round(price * 0.95)
        entry_rating = "⭐⭐⭐ 可以分批建仓" if price >= ma200 else "⭐⭐ 等待或小仓试探"
        strategies = [
            Strategy("🟢 长线 >12月", f"""
- **当前入场评级：** {entry_rating}
- **建仓策略：** 资金分4份，每隔4-6周买入一份
- **仓位上限：** 黄金占组合不超过 **15%**
- **机构目标价中位 $5,400**，较当前上行约 **+{upside:.0f}%**
- **止损参考：** 月度收盘跌破 **$3,500** 需重新评估
- **加仓点：** 下探至 **${entry2:,}**（-5%）可加大第二批"""),
            Strategy("🟡 中线 3-6月", f"""
- **关键节点：** 等待 **FOMC** 结果，不提前押注
- **看多触发：** 暗示暂停加息 → 反弹至 **$4,500+** 右侧入场
- **看空触发：** 确认加息 → 等待 **$3,800–3,900** 再建仓
- **目标价位：** $4,700–$5,000；LBMA全年均价共识 $4,742
- **止损：** 入场后跌破 **${stop_l:,}**（-8%）"""),
            Strategy("🔴 短线 <1月", f"""
- ⛔ **谨慎做多：** 跌破均线 + ETF净流出 + 方向未明
- **若操作：** 严格小仓（≤2%），硬止损 **${stop_l:,}**
- **观察指标：** 实时跟踪 DXY 和 10Y TIPS（与金价反向）
- ⚠️ 短线需专业知识和严格风险管理，新手谨慎"""),
            Strategy("🔵 已持仓者", f"""
- **持仓评估：** 成本低于 $4,000 仍在浮盈，无需恐慌
- **持有逻辑：** 央行需求稳固，LBMA共识 $4,742 高于当前价
- **减仓时机：** 反弹至 **$4,700–5,000** 可减持30%锁利
- **止损纪律：** 成本 $4,200+ 且浮亏，跌破 **$3,800** 必须止损"""),
        ]

        related = self._related()
        extra = [self._inst_card(price), self._heatmap_card()]

        return Snapshot(
            price=price, price_fmt=self.fmt_price(price),
            history=chart_closes, dates=chart_dates,
            change=change, change_pct=change_pct,
            score=score, score_label=slabel, score_color=scolor,
            kpis=kpis, alerts=alerts, indicators=indis,
            strategies=strategies, related=related,
            ma_ref=ma200, ma_label=f"MA200 ${ma200:,.0f}",
            extra_cards=extra, data_live=live,
            source_note="实时金价 (GC=F)" if live else "示例数据（未连实时源）",
            ai_facts={
                "距历史高点": f"{from_ath:.1f}%（ATH $5,595）",
                "机构目标价中位": "$5,400",
                "央行Q1净购金": f"{MACRO['cb_q1']} 吨",
                "ETF资金流": f"{etf:+.2f} MOz",
                "12月加息概率": f"{hike}%",
            },
        )

    # ── 评分（迁移自原 calc_score）──
    def _score(self, price, ma200, rsi, etf, tips, dxy, hike):
        s = 50
        s += -10 if price < ma200 else 5
        s += 8 if rsi < 30 else (3 if rsi < 40 else (-8 if rsi > 70 else 0))
        s += 6 if etf > 0 else -4
        s += 8 if tips < 0 else (3 if tips < 1 else (-6 if tips > 2 else 0))
        s += -5 if dxy > 105 else (5 if dxy < 100 else 0)
        s += -6 if hike > 60 else (6 if hike < 30 else 0)
        s += 5
        if (MACRO["ath"] - price) / MACRO["ath"] > 0.2:
            s += 5
        return clamp_score(s)

    @staticmethod
    def _rsi_badge(rsi):
        if rsi < 30:
            return "超卖", "badge-up"
        if rsi < 45:
            return "偏弱", "badge-warn"
        if rsi > 70:
            return "超买", "badge-dn"
        return "中性", "badge-neu"

    @staticmethod
    def _tips_badge(tips):
        if tips < 0:
            return "负利率 极佳", "badge-up"
        if tips < 1:
            return "低利率 利好", "badge-up"
        if tips > 2:
            return "高利率 压制", "badge-dn"
        return "中性偏空", "badge-warn"

    def _related(self):
        specs = [
            ("白银 XAG/USD", "SI=F", 32.45, "$", False),
            ("黄金ETF GLD", "GLD", 391.2, "$", False),
            ("黄金矿业 GDX", "GDX", 38.9, "$", False),
            ("美元指数 DXY", "DX-Y.NYB", 102.8, "", False),
            ("美国10Y国债", "^TNX", 4.38, "", True),
            ("原油 WTI", "CL=F", 99.8, "$", False),
        ]
        out = []
        for name, tkr, fallback, pre, is_rate in specs:
            res = data.yf_history(tkr, period="5d")
            if res and len(res[0]) >= 2:
                p, prev = res[0][-1], res[0][-2]
                chg = (p - prev) / prev * 100 if prev else 0
            else:
                p, chg = fallback, 0.0
            up = chg >= 0
            val = f"{p:.2f}%" if is_rate else f"{pre}{p:.2f}"
            cstr = f"{'+' if up else ''}{chg:.2f}%"
            out.append(Related(name, val, cstr, up))
        return out

    def _inst_card(self, price):
        rows = ""
        for name, target, note in INSTITUTIONS:
            pct = round((target - price) / price * 100)
            bar_w = round(target / 6300 * 100)
            color = "#4ade80" if pct > 20 else ("#fbbf24" if pct > 10 else "#f87171")
            rows += f"""<div style="margin-bottom:10px">
              <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px">
                <span style="color:#5a6070">{name}</span>
                <span style="font-family:monospace;color:#f0c040">${target:,} <span style="color:{color};font-size:10px">(+{pct}%)</span></span>
              </div>
              <div class="inst-bar-bg"><div style="height:5px;width:{bar_w}%;background:linear-gradient(90deg,#8b6914,#f0c040);border-radius:3px"></div></div>
              <div style="font-size:9px;color:#5a6070;margin-top:2px">{note}</div>
            </div>"""
        return "机构目标价", rows

    def _heatmap_card(self):
        factors = [
            ("美联储鹰派风险", "高", 80, "#e05555"), ("通胀粘性支撑", "强", 75, "#3dba6a"),
            ("央行结构需求", "强", 85, "#3dba6a"), ("ETF资金流入", "弱", 25, "#e05555"),
            ("美元走强压力", "高", 70, "#e05555"), ("地缘风险溢价", "中", 60, "#e08030"),
        ]
        cells = ""
        for label, val, pct, color in factors:
            cells += f"""<div class="heat-cell" style="background:{color}18;margin-bottom:8px">
              <div style="font-size:10px;color:rgba(255,255,255,.5)">{label}</div>
              <div style="font-size:14px;font-weight:700;color:{color}">{val}</div>
              <div style="height:3px;background:rgba(255,255,255,.1);border-radius:2px;margin-top:4px">
                <div style="height:100%;width:{pct}%;background:{color};opacity:.7;border-radius:2px"></div></div>
            </div>"""
        return "风险因子热力图", f'<div style="columns:2;column-gap:8px">{cells}</div>'
