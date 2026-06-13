# 🥇 Au Watch · 黄金行情监控

基于 Streamlit + Claude AI 构建的黄金投资监控 Dashboard，支持一键部署到 Streamlit Cloud。

## 功能

- 📊 实时价格走势图 + 技术指标（MA200、RSI、DXY、TIPS、ETF资金流）
- 🎯 综合信号仪表盘（0-100 评分）
- 🤖 Claude AI 实时分析（形势判断 + 风险 + 建议）
- 📋 四种策略推荐（长线 / 中线 / 短线 / 已持仓）
- 🏦 机构目标价追踪（高盛、JPMorgan、UBS 等）
- 🌡️ 风险因子热力图
- 📈 相关资产监控（白银、GLD、GDX、DXY、原油）

## 部署到 Streamlit Cloud（3步）

### 第一步：Push 到 GitHub
```bash
git add .
git commit -m "feat: add streamlit gold monitor"
git push
```

### 第二步：在 Streamlit Cloud 创建 App
1. 打开 [share.streamlit.io](https://share.streamlit.io)
2. 点击 **New app**
3. 选择你的 GitHub 仓库和 `app.py`
4. 点击 **Deploy**

### 第三步：配置 Secrets
在 App Settings → Secrets 中填写：
```toml
ANTHROPIC_API_KEY = "sk-ant-你的密钥"
```

> 获取 Anthropic API Key：[console.anthropic.com](https://console.anthropic.com)

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

本地运行需在 `.streamlit/secrets.toml` 中填写你的 API Key（已加入 .gitignore，不会被提交）。

## 文件结构

```
├── app.py                    # 主程序
├── requirements.txt          # 依赖
├── .streamlit/
│   ├── config.toml           # 暗色主题配置
│   └── secrets.toml          # API密钥（本地用，不提交）
└── README.md
```

## ⚠️ 免责声明

本工具仅供参考，不构成投资建议。黄金投资存在本金损失风险，请结合自身风险承受能力审慎决策。
