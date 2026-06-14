"""加密货币（BTC 主视图，ETH/SOL/BNB 为相关资产）——含实时恐惧贪婪指数。"""
from __future__ import annotations

from lib import data, indicators
from lib.model import (Snapshot, Indicator, Strategy, Related, KPI, Alert,
                       score_label, clamp_score)
from .base import AssetModule

ANCHORS = [42000, 43500, 41800, 44000, 45200, 43900, 46000, 47500, 46800,
           48000, 49500, 51000, 50200, 52000, 53500, 52800, 54000, 55500,
           54800, 56000, 57500, 56800, 58000, 59500, 58800, 60000, 61500,
           60800, 62000, 63500]


class CryptoModule(AssetModule):
    id = "crypto"
    name = "比特币 BTC/USD"
    icon = "₿"
    accent = "#f7931a"
    price_prefix = "$"
    price_decimals = 0
    scan_ticker = "BTC-USD"

    def build_snapshot(self, refresh: bool = False) -> Snapshot:
        closes, dates, live = self.series_or_sim("BTC-USD", ANCHORS, period="1y", refresh=refresh)
        price = closes[-1]

        ma200 = indicators.sma(closes, 200) if live and len(closes) >= 60 else indicators.sma(closes, 30)
        rsi = indicators.rsi(closes, 14) or 50
        mom30 = indicators.pct_change(closes, 30)
        dd = indicators.drawdown_from_high(closes)

        fg = data.crypto_fear_greed()
        fg_val, fg_label = fg if fg else (50, "Neutral")
        fg_live = fg is not None
        glob = data.crypto_global()       # 市占率 / 总市值（CoinGecko）
        net = data.btc_network_stats()    # 算力 / 链上交易（blockchain.info）

        change = closes[-1] - closes[-2] if len(closes) > 1 else 0.0
        change_pct = (change / closes[-2] * 100) if len(closes) > 1 and closes[-2] else 0.0

        mcap_chg = glob["mcap_change_24h"] if glob else 0.0
        score = self._score(price, ma200, rsi, fg_val, mom30, mcap_chg)
        slabel, scolor = score_label(score)

        kpis = [
            KPI("BTC 现价", self.fmt_price(price),
                f"{'+' if change >= 0 else ''}{change:,.0f} ({change_pct:+.2f}%)"),
            KPI("距区间高点", f"{dd:.1f}%", "近一年最高点回撤"),
            KPI("30日动量", f"{mom30:+.1f}%", "短中期趋势"),
            KPI("恐惧贪婪指数", f"{fg_val}", f"{fg_label}{'（实时）' if fg_live else ''}"),
            KPI("市场情绪", slabel, f"综合得分 {score}/100"),
        ]

        alerts = []
        if price < ma200:
            alerts.append(Alert("alert-warn", f"⚠️ BTC ({self.fmt_price(price)}) 跌破长期均线（${ma200:,.0f}），中期趋势转弱。"))
        if fg_val <= 25:
            alerts.append(Alert("alert-up", f"🧊 恐惧贪婪指数 {fg_val}（极度恐惧），历史上常对应中长线左侧机会，但需控制仓位。"))
        elif fg_val >= 75:
            alerts.append(Alert("alert-dn", f"🔥 恐惧贪婪指数 {fg_val}（极度贪婪），市场过热，警惕回调。"))
        if abs(mom30) > 25:
            alerts.append(Alert("alert-warn", f"📈 30日波动剧烈（{mom30:+.0f}%），加密资产高波动，注意杠杆与仓位风险。"))

        indis = [
            Indicator("长期均线 (MA200)", f"${ma200:,.0f}",
                      *("下方 熊市", "badge-dn") if price < ma200 else ("上方 牛市", "badge-up")),
            Indicator("RSI (14)", f"{rsi:.0f}", *self._rsi_badge(rsi)),
            Indicator("30日动量", f"{mom30:+.1f}%",
                      *("强势", "badge-up") if mom30 > 5 else (("弱势", "badge-dn") if mom30 < -5 else ("盘整", "badge-neu"))),
            Indicator("恐惧贪婪", f"{fg_val} {fg_label}", *self._fg_badge(fg_val)),
        ]
        if glob:
            dom = glob["btc_dominance"]
            indis.append(Indicator("BTC 市占率", f"{dom:.1f}%",
                         *("资金集中BTC", "badge-up") if dom > 55 else (("山寨活跃", "badge-warn") if dom < 45 else ("均衡", "badge-neu"))))
        if net:
            indis.append(Indicator("全网算力", f"{net['hash_rate_eh']:,.0f} EH/s",
                                   "网络安全", "badge-up"))
        m = self.macd_row(closes)
        if m:
            indis.append(m)

        strategies = [
            Strategy("🟢 长线 >12月", """
- **定投优先：** 加密波动极大，长线建议固定金额定投（DCA），不择时
- **仓位上限：** 加密资产占总资产建议 **≤5-10%**，风险承受低者更少
- **冷钱包：** 长期持有考虑自托管，降低交易所风险
- **逻辑检验：** 关注减半周期、ETF资金流、监管动向"""),
            Strategy("🟡 中线 3-6月", """
- **趋势跟随：** 价格站上 MA200 视为中期偏多，跌破则转防御
- **分批：** 极度恐惧区间分批左侧，极度贪婪区间分批减仓
- **目标/止损：** 明确盈亏比，单笔止损建议 -15% 以内
- **远离杠杆：** 中线不建议合约/杠杆，现货为主"""),
            Strategy("🔴 短线 <1月", """
- ⛔ **高风险：** 加密短线波动巨大，新手极易爆仓
- **若操作：** 极小仓（≤2%），严设硬止损，绝不补仓扛单
- **观察：** 资金费率、恐惧贪婪极值、链上大额转账
- ⚠️ 不要用杠杆做短线赌方向"""),
            Strategy("🔵 已持仓者", """
- **再平衡：** 涨幅过大致占比超目标，逢高减仓回到目标比例
- **分批止盈：** 极度贪婪 + 大涨后，分批锁定部分利润
- **风险隔离：** 留足生活备用金，只用闲钱投资加密
- **税务/合规：** 注意所在地对加密资产的合规与税务要求"""),
        ]

        related = self._related()
        extra = [self._fg_card(fg_val, fg_label, fg_live),
                 self._onchain_card(glob, net)]

        return Snapshot(
            price=price, price_fmt=self.fmt_price(price),
            history=closes[-60:], dates=dates[-60:],
            change=change, change_pct=change_pct,
            score=score, score_label=slabel, score_color=scolor,
            kpis=kpis, alerts=alerts, indicators=indis,
            strategies=strategies, related=related,
            ma_ref=ma200, ma_label=f"MA200 ${ma200:,.0f}",
            extra_cards=extra, data_live=live,
            source_note="实时 (BTC-USD)" if live else "示例数据（未连实时源）",
            ai_facts={
                "恐惧贪婪指数": f"{fg_val}（{fg_label}）",
                "30日动量": f"{mom30:+.1f}%",
                "距区间高点回撤": f"{dd:.1f}%",
                **({"BTC市占率": f"{glob['btc_dominance']:.1f}%",
                    "全市场24h市值变化": f"{glob['mcap_change_24h']:+.2f}%"} if glob else {}),
                **({"全网算力": f"{net['hash_rate_eh']:,.0f} EH/s"} if net else {}),
            },
        )

    def _score(self, price, ma200, rsi, fg, mom30, mcap_chg=0.0):
        s = 50
        s += 8 if price > ma200 else -8
        s += 8 if rsi < 30 else (3 if rsi < 45 else (-8 if rsi > 70 else 0))
        # 恐惧贪婪：极度恐惧偏多（逆向），极度贪婪偏空
        s += 8 if fg <= 25 else (4 if fg < 45 else (-8 if fg >= 75 else (-3 if fg > 55 else 0)))
        s += 5 if mom30 > 10 else (-5 if mom30 < -10 else 0)
        # 全市场24h市值变化：作为短期资金动能的辅助信号
        s += 3 if mcap_chg > 2 else (-3 if mcap_chg < -2 else 0)
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
    def _fg_badge(fg):
        if fg <= 25:
            return "极度恐惧", "badge-up"
        if fg < 45:
            return "恐惧", "badge-warn"
        if fg >= 75:
            return "极度贪婪", "badge-dn"
        if fg > 55:
            return "贪婪", "badge-warn"
        return "中性", "badge-neu"

    def _related(self):
        specs = [
            ("以太坊 ETH", "ETH-USD", 3200), ("Solana SOL", "SOL-USD", 145),
            ("币安币 BNB", "BNB-USD", 580), ("瑞波 XRP", "XRP-USD", 0.62),
            ("狗狗币 DOGE", "DOGE-USD", 0.16), ("黄金 XAU", "GC=F", 4219),
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
            val = f"${p:,.2f}" if p < 10 else f"${p:,.0f}"
            out.append(Related(name, val, f"{'+' if up else ''}{chg:.2f}%", up))
        return out

    def _fg_card(self, val, label, live):
        color = "#e05555" if val >= 75 else ("#e08030" if val >= 55 else ("#3dba6a" if val <= 45 else "#5a6070"))
        return "恐惧贪婪指数", f"""
        <div style="text-align:center;padding:8px 0">
          <div style="font-size:42px;font-weight:700;font-family:monospace;color:{color}">{val}</div>
          <div style="font-size:13px;color:{color};margin-top:2px">{label}</div>
          <div style="height:6px;background:#1e2130;border-radius:3px;margin:12px 0 4px">
            <div style="height:100%;width:{val}%;background:linear-gradient(90deg,#3dba6a,#e08030,#e05555);border-radius:3px"></div>
          </div>
          <div style="font-size:9px;color:#5a6070">0 极度恐惧 ←→ 100 极度贪婪 · {'实时 alternative.me' if live else '示例值'}</div>
        </div>"""

    def _onchain_card(self, glob, net):
        def row(label, val, color="#e4e6ee"):
            return f"""<div style="display:flex;justify-content:space-between;font-size:11px;padding:6px 0;border-bottom:1px solid #1e2130">
              <span style="color:#5a6070">{label}</span>
              <span style="font-family:monospace;color:{color}">{val}</span></div>"""
        rows = ""
        if glob:
            mc = glob["mcap_change_24h"]
            rows += row("BTC 市占率", f"{glob['btc_dominance']:.1f}%")
            rows += row("全市场总市值", f"${glob['total_mcap_usd'] / 1e12:.2f}T")
            rows += row("24h 市值变化", f"{mc:+.2f}%", "#3dba6a" if mc >= 0 else "#e05555")
        if net:
            rows += row("全网算力", f"{net['hash_rate_eh']:,.0f} EH/s", "#3dba6a")
            rows += row("24h 链上交易", f"{net['n_tx_24h']:,}")
        if not rows:
            rows = '<div style="font-size:11px;color:#5a6070;padding:8px 0">链上/市值数据暂不可用（网络或接口限制），其余指标不受影响。</div>'
        return "链上 / 市值数据", rows
