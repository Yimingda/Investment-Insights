# 📊 多品种投资建议面板

基于 Streamlit + Claude AI 的多品种投资监控 Dashboard。一套 UI 渲染多个品种，
数据接入免费实时行情，缺失时自动降级到示例数据，可一键部署到 Streamlit Cloud。

## 支持品种

| 品种 | 主标的 | 实时数据源 |
|------|--------|-----------|
| 🥇 黄金 | XAU/USD（GC=F） | yfinance + FRED(可选) |
| ₿ 加密货币 | BTC/USD | yfinance + 恐惧贪婪(alternative.me) + 链上/市值(CoinGecko、blockchain.info) |
| 🇺🇸 美股 | 标普500 (SPY) | yfinance + 实时 VIX、板块ETF |
| 🇨🇳 A股 | 沪深300 | akshare（指数 + 北向资金） |
| 💱 外汇 | USD/CNY 在岸人民币 | yfinance（含 DXY、主要货币对、离岸CNH） |

每个品种都提供：价格走势图 + 均线、综合信号仪表盘（0-100 评分）、关键指标、
四种策略推荐（长/中/短线 / 已持仓）、相关资产监控、品种专属面板、**投资日历**（按品种过滤的近期关键事件），以及智能行情分析。

**投资日历**：每页展示与该品种相关的未来大事（FOMC/CPI/非农、LPR、期权到期/三巫、CME 比特币到期、权重股财报、两会等），按重要性 ★ 分级、高亮 7 天内。配置 `FINNHUB_API_KEY`（[finnhub.io](https://finnhub.io) 免费）走实时财经/财报日历，否则降级为规则推算的关键事件。

**实时新闻 + 全市场预警**（均基于实时数据，与模型知识截止无关）：
- 📰 每页展示与该品种相关的实时新闻（A股用 akshare 中文快讯，其余用 Finnhub 分类新闻），并把头条**一并喂给 AI 分析作消息面参考**。
- 🔔 顶部"全市场实时预警"扫描全部品种的实时阈值信号：跌破均线、RSI 超买/超卖、单日大幅波动——让你在任一页面都能看到其他品种的异动。

**💰 API 花费监控**（顶部"💰 API花费"视图）：调用 Anthropic Cost Admin API 展示你账户的**每日花费趋势**（柱状图）与**消耗结构**（按模型/项目看哪里花得多）。需 `ANTHROPIC_ADMIN_KEY`（`sk-ant-admin...`，Console → Settings → Admin keys，仅组织 admin 可创建；⚠️ 权限大、勿提交）。未配置则显示示例数据 + 接入指引。

**🔎 A股自选股**（A股 视图内）：输入任意 A股代码（空格/逗号分隔，自动识别沪 `.SS`/深 `.SZ`，yfinance 实时取数），逐只给出现价、综合评分与技术面（趋势 / RSI / 动量 / MACD）+ 一句话建议。⚠️ 评分基于技术面，个股波动大，仅供参考。

## 架构

```
app.py                 # 入口：品种切换 + 共享 Dashboard 渲染器
lib/                   # 共享基础设施
  model.py             # 数据模型（Snapshot / Indicator / Strategy…）
  indicators.py        # 纯函数：SMA / RSI / 动量 / 回撤
  theme.py             # 暗色主题 CSS + Plotly 图表
  data.py              # yfinance / FRED / akshare / 恐惧贪婪 抓取 + 缓存 + 降级
  ai.py                # Claude 分析 + 规则引擎降级
assets/                # 各品种模块（实现统一接口）
  base.py              # 品种基类 + 实时/模拟数据工具
  gold.py / crypto.py / us_equity.py / a_share.py / forex.py
```

品种专属指标举例：黄金（机构目标价、风险热力图）、加密（恐惧贪婪指数、BTC市占率、全网算力、链上交易）、
美股（VIX、板块ETF）、A股（北向资金、估值情绪）、外汇（DXY、主要货币对、换汇时机）。

**加新品种**：在 `assets/` 新建一个模块，实现 `build_snapshot(refresh) -> Snapshot`，
然后在 `assets/__init__.py` 的 `REGISTRY` 注册即可，UI 无需改动。

## 数据与降级策略

- **优先实时**：能拿到行情就用真实数据（走势、均线、RSI 等据此计算）。
- **优雅降级**：库未安装或网络失败时，自动回退到示例数据，界面照常可用（状态条会标注数据源）。
- 黄金的 TIPS 实际利率、ETF 资金流、央行购金等无免费实时源的指标，作为可调的编辑性输入。

## 智能分析

- 配置了 `ANTHROPIC_API_KEY` → 点击「用 Claude 深度分析」调用 Claude（默认 `claude-opus-4-8`）。
- 未配置或调用失败 → 自动使用内置**规则引擎**，完全免费、无需联网。

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

本地把密钥填到 `.streamlit/secrets.toml`（已在 .gitignore，不会提交）。

快速回归自检（无需网络）：`python tests/test_smoke.py`

> 兼容性：已在 **Python 3.14** 实测 `streamlit / yfinance / anthropic / akshare` 均可正常安装与运行。
> A股北向资金的**盘中实时净额**因交易所自 2024-08 起停止披露而不可用（面板会如实说明），不影响指数/均线/RSI 等其余指标。

## 部署到 Streamlit Cloud

1. `git push` 到 GitHub
2. [share.streamlit.io](https://share.streamlit.io) → New app → 选仓库与 `app.py` → Deploy
3. App Settings → Secrets 填写 `ANTHROPIC_API_KEY`（可选 `FINNHUB_API_KEY`、`ANTHROPIC_ADMIN_KEY`、`FRED_API_KEY`、`ANTHROPIC_MODEL`）

## ⚠️ 免责声明

本工具仅供参考，不构成投资建议。投资有风险，入市需谨慎，请结合自身风险承受能力审慎决策。
