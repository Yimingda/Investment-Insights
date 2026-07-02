"""术语详解页面 —— 纯静态,无数据依赖。所有缩写/术语大白话解释 + ticker 速查。"""
from __future__ import annotations

import streamlit as st


def _table(rows: list[tuple[str, str]]) -> str:
    head = "| 术语 | 大白话解释 |\n|---|---|\n"
    body = "\n".join(f"| **{t}** | {d} |" for t, d in rows)
    return head + body


BASICS = [
    ("σ / z-score / 标准差", "把一个数和它自己近期的平均值比,看偏离了几倍「常见波动」。0=和平时一样,+2=少见地高,−2=少见地低。好处:不同资产量级天差地别,都换成 σ 就能公平比较。"),
    ("ETF", "交易所交易基金——像股票一样买卖的一篮子资产。例:SPY=标普500,GLD=黄金,AGG=美国综合债。"),
    ("对数坐标 (log scale)", "纵轴按百分比等距:100→200 和 1000→2000(都翻倍)在图上一样高。看长期涨跌不会被近年的大数字压扁。"),
    ("总回报 / auto_adjust", "价格已计入分红/派息再投资。比较债券、高股息 ETF 时必须用总回报,否则会低估它们。"),
    ("无前视 / 因果 (look-ahead-free)", "算每一天的指标时只用那天**之前**的数据,不偷看未来 → 不是「马后炮」。"),
    ("回撤 / drawdown", "从最近的高点跌下来的百分比。**最大回撤 (MaxDD)** = 历史上最惨的一次,衡量「要扛多大的亏」。"),
    ("CAGR 年化复合增长率", "把一段时间的总收益摊成「平均每年涨多少」。"),
    ("夏普比率 (Sharpe)", "每承担 1 单位波动,换来多少收益;越高越「性价比高」。本工具标注 rf=0(把无风险利率当 0)。"),
    ("波动率 (vol / volatility)", "收益的标准差(年化),衡量价格颠簸的剧烈程度。注意:华尔街口语的 Vol 有时也指成交量(Volume)。"),
    ("基点 (bps)", "0.01%。50bps = 0.5%,常用于利率,如「降息 50bps」。"),
]

MACRO = [
    ("增长 Growth / 通胀 Inflation 轴", "驱动资产价格的两个「相对预期的意外」。本工具用市场价格比值**反推**(市场隐含),不是 CPI/PMI 等宏观实测值。"),
    ("四象限", "增长×通胀交叉出的四种环境:**Reflation 再通胀**(增长↑通胀↑)、**Goldilocks 金发女孩**(增长↑通胀↓)、**Stagflation 滞胀**(增长↓通胀↑)、**Deflation 通缩衰退**(增长↓通胀↓)。"),
    ("RORO (Risk-On / Risk-Off)", "全市场「进攻 vs 避险」的总开关。>0 = 钱偏爱风险资产(股/币),<0 = 逃向避险(黄金/美债)。"),
    ("全天候 All-Weather / 风险平价 (risk parity)", "桥水 Ray Dalio 的组合思想:按**风险贡献**均等配置(不是按美元金额),让组合对四种环境都平衡、不赌单一环境。"),
    ("铜金比 (copper/gold, HG=F/GC=F)", "铜(工业需求「Dr. Copper」)÷ 黄金(避险)。上升 = 市场在给「增长加速」定价。"),
    ("盈亏平衡 breakeven (TIP/IEF)", "抗通胀债(TIP)÷ 名义国债(IEF),约等于市场隐含的**通胀预期**。"),
    ("eff_n 有效样本", "= 该象限天数 ÷ 持有期 H。每日的 H 日窗口高度重叠、并非独立观测,真实独立样本远少于天数;eff_n<5 的读数不可靠(打 ⚠)。"),
    ("美林时钟相位", "同一增长×通胀平面的周期叙事:**Recovery 复苏**(主角=股票)→ **Overheat 过热**(商品)→ **Stagflation 滞胀**(现金)→ **Reflation/Deflation**(债券)→ 循环。"),
    ("⚠️ Reflation 命名冲突", "本页「Reflation 再通胀」= 增长↑通胀↑;而美林时钟的「Reflation」指增长↓通胀↓(=本页 Deflation)。两处同名、含义相反,注意区分。"),
]

EXTREMES = [
    ("vol_z 成交量异常", "今天的成交量比近 20 日平均高/低几个 σ。冲到 +2 以上 = 放天量,常见于情绪极端(疯狂追涨或恐慌抛售)。"),
    ("px_ma_z", "价格相对 200 日均线偏离几个 σ——衡量「离均线多远」,过高/过低都是极端。"),
    ("ret_n 动量", "近 20 个交易日的涨跌幅(%)。"),
    ("regime 温度计 (gauge)", "把 px_ma_z、vol_z、RORO、动量 标准化后取均值的合成分数;±0.8 = TOP/BOTTOM 观察带。**描述性温度计,非择时信号**(回测证明这类分数对未来回撤无稳定预测力)。"),
    ("ATH 历史新高 (All-Time High)", "该资产至今的最高价。图上橙点标出新高日。"),
    ("WATCH 观察 (TOP/BOTTOM)", "温度计进入极端区(≥+0.8 顶部观察 / ≤−0.8 底部观察),投影到价格图上的红/绿底色。"),
    ("事件类型", "avers_top 避险顶 · euphoria_top 狂热顶 · growth_top 成长顶 · policy_bottom 政策底 · crisis_bottom 危机底 · capitulation_bottom 投降底 · policy_pivot 政策转向 · shock 冲击。红=顶,绿=底,灰=转向/冲击。"),
]

RRG = [
    ("RRG (Relative Rotation Graph)", "相对轮动图——把各板块相对大盘(SPY)的「强弱 × 动量」画在一张四象限图上,看谁在领涨、谁在补跌。"),
    ("RS-Ratio", "相对强弱的**趋势**(x 轴,以 100 为中心;>100=强于大盘)。本工具为**无前视开源近似**,非 StockCharts 的专有 JdK 数值。"),
    ("RS-Momentum", "RS-Ratio 的**动量/变化率**(y 轴,以 100 为中心;>100=还在加强)。"),
    ("相对强弱 RS (Relative Strength)", "板块价格 ÷ 基准(SPY)价格。上升=跑赢大盘。"),
    ("四象限(RRG)", "**Leading 领先**(强且更强)· **Weakening 转弱**(强但动量掉头)· **Lagging 落后**(弱且更弱)· **Improving 改善**(弱但动量转起)。顺时针轮动:改善→领先→转弱→落后→改善。"),
    ("基准 benchmark", "参照物,这里是 SPY(标普500);它自身相对自己恒等于 100,固定在图中心。"),
    ("尾迹 tail", "最近 N 周的移动轨迹,让你看到板块「往哪个象限转」。"),
    ("EMA 指数移动平均", "一种越近的数据权重越大的平滑均线。"),
    ("SPDR 行业 ETF", "把标普500拆成 11 个行业:XLK 科技 · XLF 金融 · XLE 能源 · XLV 医疗 · XLI 工业 · XLY 非必需消费 · XLP 必需消费 · XLU 公用事业 · XLB 原材料 · XLRE 房地产 · XLC 通信服务。"),
]

GEM = [
    ("双动量 (Dual Momentum) / GEM", "Gary Antonacci 的策略「Global Equities Momentum」:每月用两道动量过滤决定持有什么。"),
    ("相对动量", "美股 vs 海外股,谁近 12 月回报高就持谁。"),
    ("绝对动量", "赢家 vs 国库券(现金):赢家还不如现金,就转持**债券**避险。"),
    ("回看 lookback", "算动量用的历史长度,默认 12 个月(可选 6/9/12)。"),
    ("ex-US 海外(除美)", "美国以外的股票。VEU/ACWX 含新兴市场,EFA 只含发达市场。"),
    ("国库券 T-bill (BIL / ^IRX)", "短期(1-3 月)美国国债,近似「无风险现金收益」。BIL 是 ETF,^IRX 是 13 周贴现收益率。"),
    ("换手 turnover", "一年调仓几次。GEM 很低(~1-2 次/年),但真实成本仍需考虑。"),
    ("绝对/相对 谁跑赢", "GEM 的价值不在跑赢,而在**用债券躲开大熊市**——历史最大回撤远小于一直持有标普。"),
]

TICKERS = [
    ("SPY / QQQ / ^NDX", "标普500 ETF / 纳斯达克100 ETF / 纳斯达克100 指数"),
    ("GC=F / GLD", "COMEX 黄金期货 / 黄金 ETF"),
    ("BTC-USD / IBIT", "比特币现货 / 比特币现货 ETF(2024 起)"),
    ("HG=F / CL=F / DBC", "铜期货 / WTI 原油期货 / 广义大宗商品 ETF"),
    ("SHY / IEF / TLT", "美国国债 ETF:1-3 年(近现金)/ 7-10 年 / 20 年以上"),
    ("HYG / LQD / AGG / BND", "高收益债 / 投资级债 / 综合债 / 综合债 ETF"),
    ("TIP", "抗通胀国债(TIPS)ETF"),
    ("VEU / ACWX / EFA", "全球除美(含新兴)/ 全球除美 / 发达市场除美(不含新兴)"),
    ("BIL / ^IRX", "1-3 月国库券 ETF / 13 周国库券贴现收益率"),
    ("XLK…XLC", "11 个 SPDR 行业 ETF(见 RRG 那节)"),
]

SECTIONS = [
    ("🧱 最基础(先看这个)", BASICS, True),
    ("🌦️ 宏观四象限 & 美林时钟", MACRO, False),
    ("🎯 极值追踪", EXTREMES, False),
    ("🔄 RRG 板块轮动", RRG, False),
    ("🚦 GEM 双动量", GEM, False),
    ("📇 代码速查(所有 ticker)", TICKERS, False),
]


def render():
    st.markdown("## 📖 术语详解")
    st.markdown(
        '<div style="font-size:12.5px;color:#c9ccd6;line-height:1.7;margin:-4px 0 8px">'
        '这几页(宏观四象限 / 极值追踪 / RRG / GEM / 美林时钟)涉及的**所有缩写和术语**,'
        '都在这里用大白话解释了。看不懂哪个词,点开对应分组即可。</div>', unsafe_allow_html=True)
    for title, rows, expanded in SECTIONS:
        with st.expander(title, expanded=expanded):
            st.markdown(_table(rows))
    st.markdown(
        '<div class="alert-warn" style="font-size:11.5px;line-height:1.6">'
        '⚠️ 所有这些工具都是**描述性 / 研究用途**,不预测价格、不构成投资建议。'
        '很多"分数/温度计/象限"经回测对未来回撤无稳定预测力——当**当下状态的地图**看,别当买卖信号。</div>',
        unsafe_allow_html=True)
    st.markdown(
        "<div style='text-align:center;font-size:10px;color:#3a3e4a;padding:10px'>"
        "术语解释仅为帮助理解 · ⚠️ 不构成投资建议。</div>", unsafe_allow_html=True)
