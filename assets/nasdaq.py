"""纳斯达克100（^NDX 主视图）—— 含 VXN 波动率、七巨头 Mag7、QQQ/SPY 相对强弱。"""
from __future__ import annotations

from lib import data, indicators
from lib.model import (Snapshot, Indicator, Strategy, Related, KPI, Alert,
                       score_label, clamp_score)
from .base import AssetModule

ANCHORS = [23800, 23950, 23700, 24100, 24350, 24200, 24500, 24700, 24550,
           24850, 25100, 24950, 25200, 25400, 25250, 25500, 25350, 25150,
           25300, 25500, 25650, 25450, 25600, 25800, 25650, 25500, 25700,
           25850, 25700, 25900]

# 七巨头 Mag7（纳指权重核心，合计占比过半）
MAG7 = [("苹果", "AAPL"), ("微软", "MSFT"), ("英伟达", "NVDA"), ("亚马逊", "AMZN"),
        ("谷歌", "GOOGL"), ("Meta", "META"), ("特斯拉", "TSLA")]


class NasdaqModule(AssetModule):
    id = "nasdaq"
    name = "纳斯达克100 (NDX)"
    icon = "🚀"
    accent = "#9a7bff"
    price_prefix = ""
    price_decimals = 0
    scan_ticker = "^NDX"

    def build_snapshot(self, refresh: bool = False) -> Snapshot:
        closes, dates, live = self.series_or_sim("^NDX", ANCHORS, period="1y", refresh=refresh)
        price = closes[-1]

        ma200 = indicators.sma(closes, 200) if live and len(closes) >= 60 else indicators.sma(closes, 30)
        ma50 = indicators.sma(closes, 50) if live and len(closes) >= 50 else indicators.sma(closes, 20)
        rsi = indicators.rsi(closes, 14) or 50
        mom30 = indicators.pct_change(closes, 30)
        dd = indicators.drawdown_from_high(closes)
        vxn = data.yf_last("^VXN") or data.yf_last("^VIX") or 20.0
        rel_qqq_spy = self._ratio_mom20("QQQ", "SPY")   # 成长 vs 大盘 相对强弱（20日，%）

        change = closes[-1] - closes[-2] if len(closes) > 1 else 0.0
        change_pct = (change / closes[-2] * 100) if len(closes) > 1 and closes[-2] else 0.0

        score = self._score(price, ma200, ma50, rsi, vxn, mom30, rel_qqq_spy)
        slabel, scolor = score_label(score)

        kpis = [
            KPI("纳指100 NDX", self.fmt_price(price),
                f"{'+' if change >= 0 else ''}{change:,.0f} ({change_pct:+.2f}%)"),
            KPI("距一年高点", f"{dd:.1f}%", "近一年最高点回撤"),
            KPI("30日动量", f"{mom30:+.1f}%", "短中期趋势"),
            KPI("纳指波动率 VXN", f"{vxn:.1f}", self._vxn_desc(vxn)),
            KPI("市场情绪", slabel, f"综合得分 {score}/100"),
        ]

        alerts = []
        if vxn >= 28:
            alerts.append(Alert("alert-dn", f"😱 VXN {vxn:.1f}（高位恐慌），科技股波动加剧，注意控制仓位与杠杆。"))
        elif vxn < 14:
            alerts.append(Alert("alert-warn", f"😴 VXN {vxn:.1f}（极低），市场或过度乐观，警惕拥挤交易反转。"))
        if price < ma200:
            alerts.append(Alert("alert-warn", f"⚠️ 纳指100 ({self.fmt_price(price)}) 跌破200日均线（{ma200:,.0f}），长期趋势转弱。"))
        if rsi > 70:
            alerts.append(Alert("alert-warn", f"📈 RSI {rsi:.0f} 进入超买，短期或有回调压力（成长股弹性大、回调也猛）。"))
        if rel_qqq_spy is not None and rel_qqq_spy <= -3:
            alerts.append(Alert("alert-warn", f"🔄 QQQ 近20日跑输 SPY {abs(rel_qqq_spy):.1f}%，资金从成长向价值/防御轮动。"))

        indis = [
            Indicator("200日均线", f"{ma200:,.0f}",
                      *("下方 看空", "badge-dn") if price < ma200 else ("上方 看多", "badge-up")),
            Indicator("均线排列", "MA50 " + (">" if ma50 and ma200 and ma50 > ma200 else "<") + " MA200",
                      *("金叉 多头", "badge-up") if ma50 and ma200 and ma50 > ma200 else ("死叉 空头", "badge-dn")),
            Indicator("RSI (14)", f"{rsi:.0f}", *self._rsi_badge(rsi)),
            Indicator("VXN 波动率", f"{vxn:.1f}", *self._vxn_badge(vxn)),
            Indicator("30日动量", f"{mom30:+.1f}%",
                      *("强势", "badge-up") if mom30 > 3 else (("弱势", "badge-dn") if mom30 < -3 else ("盘整", "badge-neu"))),
        ]
        if rel_qqq_spy is not None:
            indis.append(Indicator("QQQ/SPY 20日", f"{rel_qqq_spy:+.1f}%",
                         *("成长领跑", "badge-up") if rel_qqq_spy > 1 else (("成长跑输", "badge-dn") if rel_qqq_spy < -1 else ("同步", "badge-neu"))))
        m = self.macd_row(closes)
        if m:
            indis.append(m)

        strategies = [
            Strategy("🟢 长线 >12月", """
- **指数定投：** QQQ/纳指100 长线定投分享科技盈利增长，不择时
- **波动预期：** 纳指回撤显著大于标普（-30% 级别历史上多次），仓位要能扛
- **集中度风险：** 七巨头占比过半——纳指≠分散，宜与宽基/债券搭配
- **逻辑检验：** 关注 AI 资本开支周期、利率环境、盈利兑现度"""),
            Strategy("🟡 中线 3-6月", """
- **趋势：** 站上 MA200 且 MA50>MA200（金叉）偏多；跌破转防御
- **利率敏感：** 成长股是长久期资产，紧盯 10Y 利率与 FOMC 路径
- **节奏：** 财报季权重股（苹果/微软/英伟达）业绩定方向，回调至均线分批
- **止损：** 指数仓 -10%~-12% 重新评估，杠杆 ETF 不建议隔季持有"""),
            Strategy("🔴 短线 <1月", """
- **高波动：** 纳指日内波动常为标普 1.5 倍上下，VXN 高位时更甚
- **若操作：** 小仓位、严设硬止损，不与趋势对抗、不抄权重股财报博弈
- **观察：** VXN、QQQ/SPY 相对强弱、半导体（SOX）风向、龙头股动向
- ⚠️ 三倍杠杆（TQQQ 等）损耗大，短线工具而非持仓标的"""),
            Strategy("🔵 已持仓者", """
- **再平衡：** 科技涨幅过大致组合集中度超标时，逢高再平衡回目标比例
- **分批止盈：** RSI 超买 + VXN 极低 + 大涨后，可分批锁定部分利润
- **对冲：** 大仓位可用少量对冲（如减仓换现金），避免裸扛财报季
- **纪律：** 跌破 MA200 是长期趋势警报，机械执行预案好过临场纠结"""),
        ]

        related = self._related()
        extra = [self._mag7_card(), self._breadth_card(rel_qqq_spy)]

        return Snapshot(
            price=price, price_fmt=self.fmt_price(price),
            history=closes[-60:], dates=dates[-60:],
            change=change, change_pct=change_pct,
            score=score, score_label=slabel, score_color=scolor,
            kpis=kpis, alerts=alerts, indicators=indis,
            strategies=strategies, related=related,
            ma_ref=ma200, ma_label=f"MA200 {ma200:,.0f}",
            extra_cards=extra, data_live=live,
            source_note="实时 (^NDX)" if live else "示例数据（未连实时源）",
            ai_facts={
                "VXN纳指波动率": f"{vxn:.1f}",
                "均线结构": "金叉(多头)" if ma50 and ma200 and ma50 > ma200 else "死叉(空头)",
                "30日动量": f"{mom30:+.1f}%",
                "距一年高点回撤": f"{dd:.1f}%",
                **({"QQQ/SPY 20日相对强弱": f"{rel_qqq_spy:+.1f}%"} if rel_qqq_spy is not None else {}),
            },
        )

    def _score(self, price, ma200, ma50, rsi, vxn, mom30, rel=None):
        s = 50
        s += 8 if price > ma200 else -8
        s += 5 if (ma50 and ma200 and ma50 > ma200) else -5
        s += 6 if rsi < 35 else (-8 if rsi > 70 else 0)
        s += 5 if vxn < 16 else (-8 if vxn > 28 else 0)
        s += 4 if mom30 > 5 else (-4 if mom30 < -5 else 0)
        if rel is not None:
            s += 3 if rel > 1 else (-3 if rel < -1 else 0)
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
    def _vxn_badge(vxn):
        if vxn >= 28:
            return "高位恐慌", "badge-dn"
        if vxn < 14:
            return "过度乐观", "badge-warn"
        if vxn < 22:
            return "平静", "badge-up"
        return "中性", "badge-neu"

    @staticmethod
    def _vxn_desc(vxn):
        if vxn >= 28:
            return "高位恐慌"
        if vxn < 14:
            return "极度平静"
        return "正常区间"

    @staticmethod
    def _ratio_mom20(a: str, b: str) -> float | None:
        """A/B 比价的近20日变化（%）——衡量相对强弱；任一腿缺数据返回 None。"""
        ra, rb = data.yf_history(a, period="3mo"), data.yf_history(b, period="3mo")
        if not ra or not rb:
            return None
        n = min(len(ra[0]), len(rb[0]))
        if n < 21:
            return None
        ratio = [x / y for x, y in zip(ra[0][-n:], rb[0][-n:]) if y]
        return indicators.pct_change(ratio, 20) if len(ratio) >= 21 else None

    def _related(self):
        specs = [
            ("QQQ ETF", "QQQ", 480, "$", False), ("标普500 SPY", "SPY", 560, "$", False),
            ("费城半导体 SOX", "^SOX", 5200, "", False), ("英伟达 NVDA", "NVDA", 135, "$", False),
            ("罗素2000 IWM", "IWM", 210, "$", False), ("美国10Y国债", "^TNX", 4.38, "", True),
        ]
        out = []
        for name, tkr, fb, pre, is_rate in specs:
            res = data.yf_history(tkr, period="5d")
            if res and len(res[0]) >= 2:
                p, prev = res[0][-1], res[0][-2]
                chg = (p - prev) / prev * 100 if prev else 0
            else:
                p, chg = fb, 0.0
            up = chg >= 0
            val = f"{p:.2f}%" if is_rate else f"{pre}{p:,.2f}"
            out.append(Related(name, val, f"{'+' if up else ''}{chg:.2f}%", up))
        return out

    def _mag7_card(self):
        rows = ""
        for name, tkr in MAG7:
            res = data.yf_history(tkr, period="5d")
            if res and len(res[0]) >= 2 and res[0][-2]:
                p, chg = res[0][-1], (res[0][-1] - res[0][-2]) / res[0][-2] * 100
                color = "#3dba6a" if chg >= 0 else "#e05555"
                rows += f"""<div style="display:flex;justify-content:space-between;font-size:11px;padding:5px 0;border-bottom:1px solid #1e2130">
                  <span style="color:#5a6070">{name} {tkr}</span>
                  <span style="font-family:monospace">${p:,.2f}
                    <span style="color:{color}">{'+' if chg >= 0 else ''}{chg:.2f}%</span></span>
                </div>"""
        if not rows:
            rows = '<div style="font-size:11px;color:#5a6070;padding:8px 0">行情暂不可用（网络或接口限制），其余指标不受影响。</div>'
        return "七巨头 Mag7（当日）", rows

    def _breadth_card(self, rel_qqq_spy):
        """相对强弱/集中度：QQQ/SPY、QQQ/RSP（等权）、半导体 SOX。"""
        def row(label, val, note):
            if val is None:
                return ""
            color = "#3dba6a" if val >= 0 else "#e05555"
            return f"""<div style="display:flex;justify-content:space-between;font-size:11px;padding:5px 0;border-bottom:1px solid #1e2130">
              <span style="color:#5a6070">{label}</span>
              <div style="text-align:right"><span style="font-family:monospace;color:{color}">{'+' if val >= 0 else ''}{val:.1f}%</span>
                <div style="font-size:9px;color:#5a6070">{note}</div></div>
            </div>"""
        rows = row("QQQ / SPY（20日）", rel_qqq_spy, "成长 vs 大盘")
        rows += row("QQQ / RSP（20日）", self._ratio_mom20("QQQ", "RSP"), "巨头 vs 等权 = 集中度")
        sox = data.yf_history("^SOX", period="3mo")
        rows += row("半导体 SOX（20日）", indicators.pct_change(sox[0], 20) if sox and len(sox[0]) >= 21 else None,
                    "AI/科技风向标")
        if not rows:
            rows = '<div style="font-size:11px;color:#5a6070;padding:8px 0">相对强弱数据暂不可用（网络或接口限制）。</div>'
        return "相对强弱 · 集中度", rows
