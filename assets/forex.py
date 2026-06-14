"""外汇（USD/CNY 在岸人民币主视图）—— 面向换汇/对冲场景。"""
from __future__ import annotations

from lib import data, indicators
from lib.model import (Snapshot, Indicator, Strategy, Related, KPI, Alert,
                       score_label, clamp_score)
from .base import AssetModule

ANCHORS = [7.18, 7.19, 7.17, 7.20, 7.21, 7.19, 7.22, 7.23, 7.21, 7.20, 7.18,
           7.17, 7.19, 7.20, 7.22, 7.21, 7.23, 7.24, 7.22, 7.21, 7.20, 7.19,
           7.18, 7.20, 7.21, 7.22, 7.20, 7.19, 7.21, 7.20]


class ForexModule(AssetModule):
    id = "forex"
    name = "美元/人民币 USD/CNY"
    icon = "💱"
    accent = "#10b981"
    price_prefix = ""
    price_decimals = 4

    def build_snapshot(self, refresh: bool = False) -> Snapshot:
        closes, dates, live = self.series_or_sim("CNY=X", ANCHORS, period="1y", refresh=refresh)
        price = closes[-1]

        ma60 = indicators.sma(closes, 60) if live and len(closes) >= 60 else indicators.sma(closes, 20)
        ma20 = indicators.sma(closes, 20)
        rsi = indicators.rsi(closes, 14) or 50
        mom20 = indicators.pct_change(closes, 20)
        dxy = data.yf_last("DX-Y.NYB") or 102.8

        change = closes[-1] - closes[-2] if len(closes) > 1 else 0.0
        change_pct = (change / closes[-2] * 100) if len(closes) > 1 and closes[-2] else 0.0

        # 评分：衡量美元兑人民币走势强弱（高分=美元走强/人民币走弱）
        score = self._score(price, ma60, ma20, rsi, dxy, mom20)
        slabel, scolor = score_label(score)

        kpis = [
            KPI("USD/CNY 在岸", self.fmt_price(price),
                f"{'+' if change >= 0 else ''}{change:.4f} ({change_pct:+.2f}%)"),
            KPI("趋势", "美元走强" if price > ma60 else "人民币走强",
                f"价格{'>' if price > ma60 else '<'}MA60"),
            KPI("20日波动", f"{mom20:+.2f}%", "短中期方向"),
            KPI("美元指数 DXY", f"{dxy:.1f}", self._dxy_desc(dxy)),
            KPI("信号强度", slabel, f"综合得分 {score}/100"),
        ]

        alerts = []
        if price >= 7.30:
            alerts.append(Alert("alert-warn", f"⚠️ USD/CNY 升至 {price:.4f}，人民币贬值压力较大，关注央行中间价与逆周期因子。"))
        elif price <= 7.05:
            alerts.append(Alert("alert-up", f"✅ USD/CNY 降至 {price:.4f}，人民币走强，持有美元/换汇成本相对偏高。"))
        if dxy > 105:
            alerts.append(Alert("alert-warn", f"💵 美元指数 DXY {dxy:.1f} 强势，对人民币等非美货币形成压制。"))
        if abs(mom20) > 1.5:
            alerts.append(Alert("alert-warn", f"📈 近20日波动 {mom20:+.2f}%，汇率波动加大，换汇/对冲注意节奏。"))

        indis = [
            Indicator("60日均线", f"{ma60:.4f}",
                      *("美元偏强", "badge-warn") if price > ma60 else ("人民币偏强", "badge-up")),
            Indicator("20日均线", f"{ma20:.4f}",
                      *("上行趋势", "badge-warn") if ma20 and ma60 and ma20 > ma60 else ("下行趋势", "badge-up")),
            Indicator("RSI (14)", f"{rsi:.0f}", *self._rsi_badge(rsi)),
            Indicator("美元指数 DXY", f"{dxy:.1f}",
                      *("强势 压人民币", "badge-warn") if dxy > 104 else (("弱势 利人民币", "badge-up") if dxy < 100 else ("中性", "badge-neu"))),
        ]
        m = self.macd_row(closes)
        if m:
            indis.append(m)

        strategies = [
            Strategy("🟢 长线/资产配置", """
- **看基本面：** 长期汇率由购买力平价、经常账户、相对增长决定
- **利差(Carry)：** 关注中美利差，利差走阔通常压人民币
- **分散：** 适度配置多币种资产可对冲单一货币风险
- **不预测点位：** 长期不押单边，按需求（留学/海外配置）规划"""),
            Strategy("🟡 中线 3-6月", """
- **趋势跟随：** 站上 MA60 且 MA20>MA60 视为美元中期偏强
- **政策面：** 关注美联储与央行政策、中间价、逆周期因子信号
- **区间思维：** 人民币常呈区间波动，极值附近逆向布局换汇更优
- **风控：** 杠杆外汇风险极高，资产配置层面不建议用杠杆"""),
            Strategy("🔴 短线 <1月", """
- ⛔ **高杠杆陷阱：** 外汇保证金杠杆极高，新手极易爆仓
- **若操作：** 极小仓、严止损，绝不扛单
- **观察：** DXY、美债收益率、中间价、风险情绪
- ⚠️ 短线汇率交易专业性强，普通投资者以了解为主"""),
            Strategy("🔵 换汇时机（个人/企业）", """
- **分批换汇：** 大额换汇分批进行，平滑汇率成本，避免单点择时
- **逢回调换入：** 需用美元时，逢 USD/CNY 回调分批换入更划算
- **锁汇/对冲：** 企业可用远期结售汇等工具锁定成本对冲风险
- **看需求不赌方向：** 以实际用汇需求为锚，不为博汇差而过度持仓"""),
        ]

        related = self._related()
        extra = [self._rate_board()]

        return Snapshot(
            price=price, price_fmt=self.fmt_price(price),
            history=closes[-60:], dates=dates[-60:],
            change=change, change_pct=change_pct,
            score=score, score_label=slabel, score_color=scolor,
            kpis=kpis, alerts=alerts, indicators=indis,
            strategies=strategies, related=related,
            ma_ref=ma60, ma_label=f"MA60 {ma60:.3f}",
            extra_cards=extra, data_live=live,
            source_note="实时 (USD/CNY)" if live else "示例数据（未连实时源）",
            ai_facts={
                "美元指数DXY": f"{dxy:.1f}",
                "趋势": "美元走强" if price > ma60 else "人民币走强",
                "20日波动": f"{mom20:+.2f}%",
                "说明": "高分=美元走强/人民币走弱方向",
            },
        )

    def _score(self, price, ma60, ma20, rsi, dxy, mom20):
        s = 50
        s += 8 if price > ma60 else -8
        s += 5 if (ma20 and ma60 and ma20 > ma60) else -5
        s += 5 if rsi > 55 else (-5 if rsi < 45 else 0)
        s += 6 if dxy > 104 else (-6 if dxy < 100 else 0)
        s += 4 if mom20 > 0.5 else (-4 if mom20 < -0.5 else 0)
        return clamp_score(s)

    @staticmethod
    def _rsi_badge(rsi):
        if rsi > 70:
            return "美元超买", "badge-warn"
        if rsi < 30:
            return "美元超卖", "badge-up"
        return "中性", "badge-neu"

    @staticmethod
    def _dxy_desc(dxy):
        if dxy > 105:
            return "强势"
        if dxy < 100:
            return "弱势"
        return "中性区间"

    def _related(self):
        specs = [
            ("欧元 EUR/USD", "EURUSD=X", 1.08, 4), ("日元 USD/JPY", "JPY=X", 150.0, 2),
            ("英镑 GBP/USD", "GBPUSD=X", 1.27, 4), ("离岸 USD/CNH", "CNH=X", 7.21, 4),
            ("澳元 AUD/USD", "AUDUSD=X", 0.66, 4), ("美元指数 DXY", "DX-Y.NYB", 102.8, 1),
        ]
        out = []
        for name, tkr, fb, dec in specs:
            res = data.yf_history(tkr, period="5d")
            if res and len(res[0]) >= 2:
                p, prev = res[0][-1], res[0][-2]
                chg = (p - prev) / prev * 100 if prev else 0
            else:
                p, chg = fb, 0.0
            up = chg >= 0
            out.append(Related(name, f"{p:,.{dec}f}", f"{'+' if up else ''}{chg:.2f}%", up))
        return out

    def _rate_board(self):
        rows = [
            ("中美利差影响", "关注", 50, "#e08030"),
            ("美联储政策路径", "中性", 50, "#5a6070"),
            ("央行中间价信号", "稳汇率", 60, "#3dba6a"),
            ("跨境资金流向", "观望", 50, "#e08030"),
        ]
        cells = ""
        for label, val, pct, color in rows:
            cells += f"""<div style="margin-bottom:9px">
              <div style="display:flex;justify-content:space-between;font-size:11px">
                <span style="color:#5a6070">{label}</span><span style="color:{color}">{val}</span></div>
              <div style="height:4px;background:#1e2130;border-radius:2px;margin-top:3px">
                <div style="height:100%;width:{pct}%;background:{color};opacity:.7;border-radius:2px"></div></div>
            </div>"""
        cells += '<div style="font-size:9px;color:#5a6070;margin-top:4px">宏观因子为编辑性参考</div>'
        return "汇率宏观因子", cells
