"""美股（标普500 / SPY 主视图）—— 含实时 VIX、板块ETF 表现。"""
from __future__ import annotations

from lib import data, indicators
from lib.model import (Snapshot, Indicator, Strategy, Related, KPI, Alert,
                       score_label, clamp_score)
from .base import AssetModule

ANCHORS = [505, 508, 502, 510, 515, 512, 518, 521, 519, 524, 528, 531, 529,
           533, 537, 535, 540, 544, 542, 546, 550, 548, 552, 556, 554, 558,
           562, 560, 564, 568]


class USEquityModule(AssetModule):
    id = "us_equity"
    name = "标普500 (SPY)"
    icon = "🇺🇸"
    accent = "#4c8bf5"
    price_prefix = "$"
    price_decimals = 2

    def build_snapshot(self, refresh: bool = False) -> Snapshot:
        closes, dates, live = self.series_or_sim("SPY", ANCHORS, period="1y", refresh=refresh)
        price = closes[-1]

        ma200 = indicators.sma(closes, 200) if live and len(closes) >= 60 else indicators.sma(closes, 30)
        ma50 = indicators.sma(closes, 50) if live and len(closes) >= 50 else indicators.sma(closes, 20)
        rsi = indicators.rsi(closes, 14) or 50
        mom30 = indicators.pct_change(closes, 30)
        vix = data.yf_last("^VIX") or 16.0

        change = closes[-1] - closes[-2] if len(closes) > 1 else 0.0
        change_pct = (change / closes[-2] * 100) if len(closes) > 1 and closes[-2] else 0.0

        score = self._score(price, ma200, ma50, rsi, vix, mom30)
        slabel, scolor = score_label(score)

        kpis = [
            KPI("SPY 现价", self.fmt_price(price),
                f"{'+' if change >= 0 else ''}{change:.2f} ({change_pct:+.2f}%)"),
            KPI("均线结构", "多头" if ma50 and ma200 and ma50 > ma200 else "空头",
                f"MA50 {'>' if ma50 and ma200 and ma50 > ma200 else '<'} MA200"),
            KPI("30日动量", f"{mom30:+.1f}%", "短中期趋势"),
            KPI("VIX 恐慌指数", f"{vix:.1f}", self._vix_desc(vix)),
            KPI("市场情绪", slabel, f"综合得分 {score}/100"),
        ]

        alerts = []
        if vix >= 25:
            alerts.append(Alert("alert-dn", f"😱 VIX {vix:.1f}（高位恐慌），市场波动加剧，注意控制仓位。"))
        elif vix < 13:
            alerts.append(Alert("alert-warn", f"😴 VIX {vix:.1f}（极低），市场或过度乐观，警惕黑天鹅。"))
        if price < ma200:
            alerts.append(Alert("alert-warn", f"⚠️ SPY ({self.fmt_price(price)}) 跌破200日均线（${ma200:,.2f}），长期趋势转弱。"))
        if rsi > 70:
            alerts.append(Alert("alert-warn", f"📈 RSI {rsi:.0f} 进入超买，短期或有回调压力。"))

        indis = [
            Indicator("200日均线", f"${ma200:,.2f}",
                      *("下方 看空", "badge-dn") if price < ma200 else ("上方 看多", "badge-up")),
            Indicator("RSI (14)", f"{rsi:.0f}", *self._rsi_badge(rsi)),
            Indicator("VIX 恐慌指数", f"{vix:.1f}", *self._vix_badge(vix)),
            Indicator("30日动量", f"{mom30:+.1f}%",
                      *("强势", "badge-up") if mom30 > 3 else (("弱势", "badge-dn") if mom30 < -3 else ("盘整", "badge-neu"))),
        ]
        m = self.macd_row(closes)
        if m:
            indis.append(m)

        strategies = [
            Strategy("🟢 长线 >12月", """
- **指数定投：** 宽基指数（SPY/VOO）长线定投是多数人最优解，不择时
- **仓位：** 按风险承受力配置股票比例，年龄越大比例越低
- **再投资：** 分红再投入，享受复利
- **逻辑：** 美股长期向上由盈利增长驱动，回调是定投良机"""),
            Strategy("🟡 中线 3-6月", """
- **趋势：** 站上 MA200 且 MA50>MA200（金叉）偏多；反之防御
- **节奏：** 关注财报季、CPI、FOMC 等关键节点
- **分批：** 回调至均线支撑分批加仓，避免追高
- **止损：** 个股止损 -8%~-10%，指数可放宽"""),
            Strategy("🔴 短线 <1月", """
- **波动交易：** VIX 高位时机会与风险并存，需经验
- **若操作：** 控制仓位，严设止损，不与趋势对抗
- **观察：** VIX、成交量、龙头股动向、消息面
- ⚠️ 短线胜率取决于纪律，新手以学习为主"""),
            Strategy("🔵 已持仓者", """
- **再平衡：** 定期检查股债比例，偏离目标时再平衡
- **止盈：** 个股涨幅过大、估值过高可分批减持
- **分散：** 避免单一个股/板块集中度过高
- **现金流：** 留足应急资金，避免被迫在低点割肉"""),
        ]

        related = self._related()
        extra = [self._sector_card()]

        return Snapshot(
            price=price, price_fmt=self.fmt_price(price),
            history=closes[-60:], dates=dates[-60:],
            change=change, change_pct=change_pct,
            score=score, score_label=slabel, score_color=scolor,
            kpis=kpis, alerts=alerts, indicators=indis,
            strategies=strategies, related=related,
            ma_ref=ma200, ma_label=f"MA200 ${ma200:,.2f}",
            extra_cards=extra, data_live=live,
            source_note="实时 (SPY)" if live else "示例数据（未连实时源）",
            ai_facts={
                "VIX恐慌指数": f"{vix:.1f}",
                "均线结构": "金叉(多头)" if ma50 and ma200 and ma50 > ma200 else "死叉(空头)",
                "30日动量": f"{mom30:+.1f}%",
            },
        )

    def _score(self, price, ma200, ma50, rsi, vix, mom30):
        s = 50
        s += 8 if price > ma200 else -8
        s += 5 if (ma50 and ma200 and ma50 > ma200) else -5
        s += 6 if rsi < 35 else (-8 if rsi > 70 else 0)
        s += 6 if vix < 15 else (-8 if vix > 25 else 0)
        s += 4 if mom30 > 5 else (-4 if mom30 < -5 else 0)
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
    def _vix_badge(vix):
        if vix >= 25:
            return "高位恐慌", "badge-dn"
        if vix < 13:
            return "过度乐观", "badge-warn"
        if vix < 20:
            return "平静", "badge-up"
        return "中性", "badge-neu"

    @staticmethod
    def _vix_desc(vix):
        if vix >= 25:
            return "高位恐慌"
        if vix < 13:
            return "极度平静"
        return "正常区间"

    def _related(self):
        specs = [
            ("纳指100 QQQ", "QQQ", 480), ("道指 DIA", "DIA", 420),
            ("罗素2000 IWM", "IWM", 210), ("苹果 AAPL", "AAPL", 230),
            ("英伟达 NVDA", "NVDA", 135), ("微软 MSFT", "MSFT", 420),
        ]
        out = []
        for name, tkr, fb in specs:
            res = data.yf_history(tkr, period="5d")
            if res and len(res[0]) >= 2:
                p, prev = res[0][-1], res[0][-2]
                chg = (p - prev) / prev * 100 if prev else 0
            else:
                p, chg = fb, 0.0
            up = chg >= 0
            out.append(Related(name, f"${p:,.2f}", f"{'+' if up else ''}{chg:.2f}%", up))
        return out

    def _sector_card(self):
        sectors = [
            ("科技 XLK", "XLK"), ("金融 XLF", "XLF"), ("能源 XLE", "XLE"),
            ("医疗 XLV", "XLV"), ("可选消费 XLY", "XLY"), ("公用 XLU", "XLU"),
        ]
        rows = ""
        for name, tkr in sectors:
            res = data.yf_history(tkr, period="5d")
            chg = 0.0
            if res and len(res[0]) >= 2 and res[0][-2]:
                chg = (res[0][-1] - res[0][-2]) / res[0][-2] * 100
            color = "#3dba6a" if chg >= 0 else "#e05555"
            rows += f"""<div style="display:flex;justify-content:space-between;font-size:11px;padding:5px 0;border-bottom:1px solid #1e2130">
              <span style="color:#5a6070">{name}</span>
              <span style="font-family:monospace;color:{color}">{'+' if chg >= 0 else ''}{chg:.2f}%</span>
            </div>"""
        return "板块表现（当日）", rows
