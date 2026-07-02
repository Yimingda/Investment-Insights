"""数据源封装 —— yfinance / FRED / akshare / 加密 Fear&Greed。

设计原则：任何库缺失或网络失败都返回 None，由调用方回退到示例数据。
所有联网函数都用 st.cache_data 缓存，避免每次重渲染都打外部接口。
"""
from __future__ import annotations

import streamlit as st


# ── 可选依赖的惰性加载 ───────────────────────────────────────
def _yf():
    try:
        import yfinance as yf
        return yf
    except Exception:
        return None


def _ak():
    try:
        import akshare as ak
        return ak
    except Exception:
        return None


def _requests():
    try:
        import requests
        return requests
    except Exception:
        return None


def secret(key: str, default=None):
    """安全读取 st.secrets（secrets.toml 不存在时不报错）。"""
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


def libs_status() -> dict[str, bool]:
    """供 UI 显示哪些数据库可用。"""
    return {
        "yfinance": _yf() is not None,
        "akshare": _ak() is not None,
        "requests": _requests() is not None,
    }


# ── yfinance：股票/ETF/外汇/加密/期货/指数 ───────────────────
@st.cache_data(ttl=900, show_spinner=False)
def yf_history(ticker: str, period: str = "3mo", interval: str = "1d"):
    """返回 (收盘价 list, 日期标签 list) 或 None。"""
    yf = _yf()
    if yf is None:
        return None
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval)
        if df is None or df.empty:
            return None
        df = df[df["Close"].notna()]          # 去掉尾部 NaN（当日未收盘/停牌行），否则末值为 nan
        if df.empty:
            return None
        closes = [float(x) for x in df["Close"].tolist()]
        dates = [d.strftime("%m/%d") for d in df.index]
        return closes, dates
    except Exception:
        return None


@st.cache_data(ttl=600, show_spinner=False)
def yf_last(ticker: str):
    """返回某标的最新价（float）或 None。"""
    res = yf_history(ticker, period="5d", interval="1d")
    if not res or not res[0]:
        return None
    return res[0][-1]


# ── FRED：宏观真实数据（需免费 API key）──────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def fred_latest(series_id: str, api_key: str | None):
    """返回 FRED 序列最新观测值（float）或 None。需在 secrets 配置 FRED_API_KEY。"""
    if not api_key:
        return None
    requests = _requests()
    if requests is None:
        return None
    try:
        url = (
            "https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={api_key}"
            "&file_type=json&sort_order=desc&limit=1"
        )
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        obs = r.json().get("observations", [])
        for o in obs:
            v = o.get("value")
            if v not in (None, ".", ""):
                return float(v)
        return None
    except Exception:
        return None


# ── 加密 Fear & Greed（alternative.me 免费公开接口，无需 key）─
@st.cache_data(ttl=1800, show_spinner=False)
def crypto_fear_greed():
    """返回 (数值 0-100, 文字分类) 或 None。"""
    requests = _requests()
    if requests is None:
        return None
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=8)
        r.raise_for_status()
        d = r.json()["data"][0]
        return int(d["value"]), d.get("value_classification", "")
    except Exception:
        return None


# ── akshare：A股指数/个股 ────────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def ak_index_history(symbol: str = "sh000300"):
    """A股指数历史（默认沪深300）。返回 (收盘价 list, 日期标签 list) 或 None。"""
    ak = _ak()
    if ak is None:
        return None
    try:
        df = ak.stock_zh_index_daily(symbol=symbol)
        if df is None or df.empty:
            return None
        df = df.tail(90)
        closes = [float(x) for x in df["close"].tolist()]
        # date 列可能是 datetime 或字符串
        dates = [str(d)[5:10].replace("-", "/") for d in df["date"].tolist()]
        return closes, dates
    except Exception:
        return None


# ── 加密链上 / 市值（CoinGecko + blockchain.info，均免费无 key）──
@st.cache_data(ttl=1800, show_spinner=False)
def crypto_global():
    """返回 {btc_dominance, total_mcap_usd, mcap_change_24h} 或 None。"""
    requests = _requests()
    if requests is None:
        return None
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=8)
        r.raise_for_status()
        d = r.json()["data"]
        return {
            "btc_dominance": d["market_cap_percentage"]["btc"],
            "total_mcap_usd": d["total_market_cap"]["usd"],
            "mcap_change_24h": d["market_cap_change_percentage_24h_usd"],
        }
    except Exception:
        return None


@st.cache_data(ttl=1800, show_spinner=False)
def btc_network_stats():
    """返回 {hash_rate_eh, n_tx_24h, market_price, difficulty} 或 None。"""
    requests = _requests()
    if requests is None:
        return None
    try:
        r = requests.get("https://api.blockchain.info/stats", timeout=8)
        r.raise_for_status()
        d = r.json()
        return {
            "hash_rate_eh": d.get("hash_rate", 0) / 1e9,  # GH/s → EH/s
            "n_tx_24h": int(d.get("n_tx", 0)),
            "market_price": d.get("market_price_usd", 0),
            "difficulty": d.get("difficulty", 0),
        }
    except Exception:
        return None


# ── A股北向资金（akshare；披露口径随版本变化，best-effort 降级）──
@st.cache_data(ttl=1800, show_spinner=False)
def ak_northbound():
    """返回北向资金当日净流入（亿元，float）或 None。"""
    ak = _ak()
    if ak is None:
        return None
    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        if df is None or df.empty:
            return None
        col = next((c for c in df.columns if "净买" in c or "净流入" in c), None)
        if col is None:
            return None
        if "资金方向" in df.columns:
            sub = df[df["资金方向"].astype(str).str.contains("北")]
        else:
            sub = df
        total = float(sub[col].astype(float).fillna(0).sum())
        # 北向实时净买额自 2024-08 起停止披露，返回值恒为 0；视为不可用
        if total == 0:
            return None
        return round(total, 2)
    except Exception:
        return None


# ── A股中文财经快讯（akshare）──────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def ak_global_news(limit: int = 6):
    """返回 [(标题, 来源, 时间, url), ...] 或 None。"""
    ak = _ak()
    if ak is None:
        return None
    try:
        df = ak.stock_info_global_em()
        if df is None or df.empty:
            return None
        tcol = next((c for c in df.columns if "标题" in c), df.columns[0])
        wcol = next((c for c in df.columns if "时间" in c), None)
        out = []
        for _, row in df.head(limit).iterrows():
            title = str(row[tcol]).strip()
            when = str(row[wcol])[5:16] if wcol else ""
            out.append((title, "东财快讯", when, ""))
        return out or None
    except Exception:
        return None
