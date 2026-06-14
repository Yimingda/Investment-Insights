"""A股（沪深300 主视图）—— 通过 akshare 接入，未安装/失败时降级到示例数据。"""
from __future__ import annotations

from lib import data, indicators
from lib.model import (Snapshot, Indicator, Strategy, Related, KPI, Alert,
                       score_label, clamp_score)
from .base import AssetModule

ANCHORS = [3850, 3870, 3820, 3890, 3910, 3880, 3930, 3960, 3940, 3980, 4010,
           3990, 4020, 4050, 4030, 4060, 4090, 4070, 4100, 4080, 4110, 4090,
           4120, 4150, 4130, 4100, 4080, 4110, 4090, 4120]


class AShareModule(AssetModule):
    id = "a_share"
    name = "沪深300指数"
    icon = "🇨🇳"
    accent = "#e0533d"
    price_prefix = "¥"
    price_decimals = 2

    def build_snapshot(self, refresh: bool = False) -> Snapshot:
        res = data.ak_index_history("sh000300")
        if res and res[0]:
            closes, dates, live = res[0], res[1], True
        else:
            closes, dates = self.sim_fallback(ANCHORS, refresh)
            live = False
        price = closes[-1]

        ma60 = indicators.sma(closes, 60) if len(closes) >= 60 else indicators.sma(closes, 20)
        ma20 = indicators.sma(closes, 20)
        rsi = indicators.rsi(closes, 14) or 50
        mom20 = indicators.pct_change(closes, 20)
        north = data.ak_northbound()  # 北向资金净流入（亿元），不可用时为 None

        change = closes[-1] - closes[-2] if len(closes) > 1 else 0.0
        change_pct = (change / closes[-2] * 100) if len(closes) > 1 and closes[-2] else 0.0

        score = self._score(price, ma60, ma20, rsi, mom20)
        slabel, scolor = score_label(score)

        kpis = [
            KPI("沪深300", self.fmt_price(price),
                f"{'+' if change >= 0 else ''}{change:.2f} ({change_pct:+.2f}%)"),
            KPI("均线结构", "多头" if ma20 and ma60 and ma20 > ma60 else "空头",
                f"MA20 {'>' if ma20 and ma60 and ma20 > ma60 else '<'} MA60"),
            KPI("20日动量", f"{mom20:+.1f}%", "短中期趋势"),
            KPI("RSI(14)", f"{rsi:.0f}", self._rsi_badge(rsi)[0]),
            KPI("市场情绪", slabel, f"综合得分 {score}/100"),
        ]

        alerts = []
        if not live:
            alerts.append(Alert("alert-warn", "ℹ️ 未检测到 akshare 实时数据（库未安装或网络不可用），当前为示例数据。"))
        if price < ma60:
            alerts.append(Alert("alert-warn", f"⚠️ 沪深300 ({self.fmt_price(price)}) 跌破60日均线（¥{ma60:,.2f}），中期趋势转弱。"))
        if rsi > 70:
            alerts.append(Alert("alert-warn", f"📈 RSI {rsi:.0f} 超买，短期或有调整压力。"))
        elif rsi < 30:
            alerts.append(Alert("alert-up", f"🧊 RSI {rsi:.0f} 超卖，关注超跌反弹机会。"))
        if north is not None and abs(north) >= 50:
            cls = "alert-up" if north > 0 else "alert-dn"
            verb = "净流入" if north > 0 else "净流出"
            alerts.append(Alert(cls, f"🌊 北向资金当日{verb} {abs(north):.1f} 亿，外资动向是 A股情绪的重要风向标。"))

        indis = [
            Indicator("60日均线", f"¥{ma60:,.2f}",
                      *("下方 看空", "badge-dn") if price < ma60 else ("上方 看多", "badge-up")),
            Indicator("20日均线", f"¥{ma20:,.2f}",
                      *("多头排列", "badge-up") if ma20 and ma60 and ma20 > ma60 else ("空头排列", "badge-dn")),
            Indicator("RSI (14)", f"{rsi:.0f}", *self._rsi_badge(rsi)),
            Indicator("20日动量", f"{mom20:+.1f}%",
                      *("强势", "badge-up") if mom20 > 3 else (("弱势", "badge-dn") if mom20 < -3 else ("盘整", "badge-neu"))),
        ]
        if north is not None:
            indis.append(Indicator("北向资金(当日)", f"{north:+.1f}亿",
                         *("净流入", "badge-up") if north > 0 else ("净流出", "badge-dn")))
        m = self.macd_row(closes)
        if m:
            indis.append(m)

        strategies = [
            Strategy("🟢 长线 >12月", """
- **宽基定投：** 沪深300/中证500 ETF 长线定投，弱化择时
- **估值参考：** 低估值分位区间加大定投力度，高分位减速
- **仓位：** 按风险承受力配置权益比例，避免满仓单押
- **逻辑：** A股波动大、风格轮动快，纪律性定投平滑成本"""),
            Strategy("🟡 中线 3-6月", """
- **趋势：** 站上 MA60 且 MA20>MA60 偏多；反之防御
- **政策面：** A股对政策、流动性敏感，关注货币/财政信号
- **北向资金：** 关注外资（北向）净流入方向作为情绪参考
- **止损：** 个股止损 -10% 左右，指数可适度放宽"""),
            Strategy("🔴 短线 <1月", """
- **题材轮动：** A股短线题材切换快，追高风险大
- **若操作：** 控制仓位，严设止损，不追涨杀跌
- **观察：** 成交量、涨停家数、板块轮动、消息面
- ⚠️ T+1 交易制度下隔夜风险更高，新手谨慎"""),
            Strategy("🔵 已持仓者", """
- **再平衡：** 定期检查仓位与行业集中度，偏离则再平衡
- **止盈：** 高估值/大涨后分批止盈，落袋为安
- **分散：** 避免重仓单一题材股，控制回撤
- **现金流：** 留足备用金，避免低位被迫割肉"""),
        ]

        related = self._related()
        extra = [self._northbound_card(north), self._valuation_card()]

        return Snapshot(
            price=price, price_fmt=self.fmt_price(price),
            history=closes[-60:], dates=dates[-60:],
            change=change, change_pct=change_pct,
            score=score, score_label=slabel, score_color=scolor,
            kpis=kpis, alerts=alerts, indicators=indis,
            strategies=strategies, related=related,
            ma_ref=ma60, ma_label=f"MA60 ¥{ma60:,.0f}",
            extra_cards=extra, data_live=live,
            source_note="实时 (akshare 沪深300)" if live else "示例数据（akshare 未连）",
            ai_facts={
                "均线结构": "多头(MA20>MA60)" if ma20 and ma60 and ma20 > ma60 else "空头(MA20<MA60)",
                "20日动量": f"{mom20:+.1f}%",
                **({"北向资金(当日)": f"{north:+.1f}亿"} if north is not None else {}),
                "数据源": "akshare 实时" if live else "示例数据",
            },
        )

    def _score(self, price, ma60, ma20, rsi, mom20):
        s = 50
        s += 8 if price > ma60 else -8
        s += 5 if (ma20 and ma60 and ma20 > ma60) else -5
        s += 8 if rsi < 30 else (3 if rsi < 45 else (-8 if rsi > 70 else 0))
        s += 4 if mom20 > 3 else (-4 if mom20 < -3 else 0)
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

    def _related(self):
        # A股相关指数：尝试 akshare，失败用示例值
        specs = [
            ("上证指数", "sh000001", 3250), ("深证成指", "sz399001", 10200),
            ("创业板指", "sz399006", 2050), ("中证500", "sh000905", 5800),
            ("科创50", "sh000688", 1050), ("沪深300", "sh000300", 4120),
        ]
        out = []
        for name, sym, fb in specs:
            res = data.ak_index_history(sym)
            if res and len(res[0]) >= 2:
                p, prev = res[0][-1], res[0][-2]
                chg = (p - prev) / prev * 100 if prev else 0
            else:
                p, chg = fb, 0.0
            up = chg >= 0
            out.append(Related(name, f"¥{p:,.2f}", f"{'+' if up else ''}{chg:.2f}%", up))
        return out

    def _northbound_card(self, north):
        if north is None:
            return "北向资金", ('<div style="font-size:11px;color:#5a6070;padding:8px 0;line-height:1.6">'
                              '北向资金<b>实时净额</b>暂不可用：沪深交易所自 2024 年 8 月起'
                              '停止盘中实时披露北向资金流向，仅保留盘后持股数据。'
                              '<br>其余 A股指标（指数 / 均线 / RSI / 动量）不受影响。</div>')
        color = "#3dba6a" if north > 0 else "#e05555"
        verb = "净流入" if north > 0 else "净流出"
        width = min(100, abs(north) / 1.5)
        return "北向资金（当日）", f"""
        <div style="text-align:center;padding:6px 0">
          <div style="font-size:34px;font-weight:700;font-family:monospace;color:{color}">{north:+.1f}<span style="font-size:14px">亿</span></div>
          <div style="font-size:12px;color:{color};margin-top:2px">外资{verb}</div>
          <div style="height:6px;background:#1e2130;border-radius:3px;margin:12px 0 4px">
            <div style="height:100%;width:{width}%;background:{color};opacity:.7;border-radius:3px"></div>
          </div>
          <div style="font-size:9px;color:#5a6070">沪深港通北向合计 · akshare 实时</div>
        </div>"""

    def _valuation_card(self):
        # 估值/情绪为编辑性参考（无统一免费实时源）
        rows = [
            ("沪深300 PE分位", "中低", 40, "#3dba6a"),
            ("两市成交活跃度", "中性", 55, "#e08030"),
            ("北向资金趋势", "观望", 50, "#e08030"),
            ("融资余额", "平稳", 50, "#5a6070"),
        ]
        cells = ""
        for label, val, pct, color in rows:
            cells += f"""<div style="margin-bottom:9px">
              <div style="display:flex;justify-content:space-between;font-size:11px">
                <span style="color:#5a6070">{label}</span><span style="color:{color}">{val}</span></div>
              <div style="height:4px;background:#1e2130;border-radius:2px;margin-top:3px">
                <div style="height:100%;width:{pct}%;background:{color};opacity:.7;border-radius:2px"></div></div>
            </div>"""
        cells += '<div style="font-size:9px;color:#5a6070;margin-top:4px">估值/情绪为编辑性参考</div>'
        return "A股估值与情绪", cells


