"""Ray Dalio「增长×通胀」四象限 —— 市场隐含、无前视的纯计算层。

无任何文件/网络依赖：所有函数接收价格 DataFrame，返回轴/象限/远期收益统计。
数据由 page.py 用 yfinance 实时拉取后传入。

方法学（经 3 份设计 + 2 轮对抗评审打磨）：
  * causal_z = expanding 均值/标准差 .shift(1) → t 时刻只用 t 之前的数据。
  * 合成轴 = 各腿 z 的「加权平均」，绝不二次标准化（二次会让多年期 regime
    衰减回 0 而误标）。
  * 增长用 SPY/SHY（非 SPY/TLT）→ 剥离长久期，滞胀里的收益率飙升不会被误读成
    「增长上行」。
  * 远期收益按资产分桶（绝不跨资产混合），报有效样本 eff_n = 天数/H（每日 H 日
    窗口高度重叠、并非独立）并对 eff_n<5 打标。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── 参数 ────────────────────────────────────────────────────────────────
START = "2010-01-01"        # 展示/标注起点（此时各腿已 warm-up 完毕）
MOM_DAYS = 63               # 季度环比变化（Dalio = 意外/变化，非水平）
Z_MIN = 252                 # 因果 expanding-z 预热（约 1 交易年）
Z_CLIP = 3.0
ROLL_WIN = 756              # 自适应尺度（约 3 年）—— expanding/rolling 切换
DEADBAND = 0.25            # 迟滞：|轴| 超过此值才切换标签
PRICE_FLOOR = 1e-6          # log() 前下限（防 CL=F 2020-04 负价）
FFILL = 2                   # 期货换月跳空的有界因果前向填充

TICKERS = ["HG=F", "GC=F", "SPY", "SHY", "HYG", "LQD", "TIP", "IEF", "DBC", "CL=F"]
TRACKED = {"gold": "GC=F", "btc": "BTC-USD", "ndx": "^NDX"}
HORIZONS = [21, 63, 126]

# 增长轴：周期 + 风险偏好，久期中性（SPY/SHY 而非 SPY/TLT）
GROWTH_LEGS = [
    {"name": "copper_gold", "expr": "HG=F / GC=F", "weight": 0.40},  # Dr.Copper 增长晴雨表
    {"name": "stocks_cash", "expr": "SPY / SHY",   "weight": 0.35},  # 股 vs 近现金，剥离久期
    {"name": "credit_hy_ig", "expr": "HYG / LQD",  "weight": 0.25},  # 高收益 vs 投资级，纯信用偏好
]
# 通胀轴：盈亏平衡 + 商品（无黄金腿，保持两轴可分）
INFLATION_LEGS = [
    {"name": "breakeven",   "expr": "TIP / IEF",   "weight": 0.40},  # 最佳 Yahoo 盈亏平衡代理
    {"name": "commodities", "expr": "DBC",         "weight": 0.35},  # 广义商品成本推动
    {"name": "oil",         "expr": "CL=F",        "weight": 0.25},  # 能源冲击，最快传导
]

QUADRANTS = {
    ("+", "+"): "Reflation 再通胀",
    ("+", "-"): "Goldilocks 金发女孩",
    ("-", "+"): "Stagflation 滞胀",
    ("-", "-"): "Deflation 通缩衰退",
}

QUADRANT_PLAYBOOK = {
    "Reflation 再通胀": {
        "favor": ["大宗商品 DBC", "原油 CL", "铜 HG", "高收益债 HYG", "周期股 SPY"],
        "avoid": ["长债 TLT", "中债 IEF"],
        "gold": "两面（受益于通胀，但实际利率上行施压）",
        "logic": "增长与通胀同时上行——典型早/中周期再通胀。实物资产、商品、周期信用受益；"
                 "长久期名义债被上行的收益率压制。",
    },
    "Goldilocks 金发女孩": {
        "favor": ["纳指 NDX", "QQQ", "SPY", "高收益债 HYG", "比特币（早期）"],
        "avoid": ["大宗商品 DBC", "原油 CL", "黄金 GC"],
        "gold": "偏弱（无通胀买盘 + 实际利率上行）",
        "logic": "增长上行而通胀回落——风险股尤其是长久期成长/科技(NDX)的最佳环境："
                 "盈利上升、贴现率下降、央行可保持宽松。",
    },
    "Stagflation 滞胀": {
        "favor": ["黄金 GC（最佳）", "大宗商品 DBC", "原油 CL", "TIPS", "现金 SHY"],
        "avoid": ["纳指 NDX", "SPY", "高收益债 HYG", "长债 TLT", "比特币"],
        "gold": "最佳（实际利率下行 + 通胀对冲）",
        "logic": "增长见顶回落、通胀仍高——1970 年代式最难环境。股债同跌(2022)；"
                 "黄金/商品/TIPS 是唯一避风港，这正是 Dalio 持有黄金与商品做风险平衡的原因。",
    },
    "Deflation 通缩衰退": {
        "favor": ["长债 TLT", "中债 IEF", "投资级债 LQD", "现金 SHY"],
        "avoid": ["大宗商品 DBC", "铜 HG", "高收益债 HYG", "SPY", "纳指 NDX", "比特币"],
        "gold": "两面（急性美元荒中先杀跌，政策转向后领涨）",
        "logic": "增长与通胀同时下行——衰退/通缩、避险。收益率崩塌，长久期名义国债是主赢家；"
                 "利差走阔使投资级跑赢高收益。",
    },
}

ASSET_MAP = {
    "gold": {"best": ["滞胀", "再通胀(两面)"], "worst": ["金发女孩"],
             "why": "实际利率/通胀敏感的避险与实物资产；滞胀最佳。通缩中两面(美元荒先杀跌、政策转向后领涨)。"},
    "btc":  {"best": ["金发女孩", "再通胀(早期)"], "worst": ["滞胀", "通缩衰退"],
             "why": "经验上是高 beta 风险/流动性资产，与 NDX/HYG 同向——并非『数字黄金』。"
                    "2022 增长跌+通胀升的格子被打爆，黄金却抗住了。"},
    "ndx":  {"best": ["金发女孩"], "worst": ["滞胀"],
             "why": "典型长久期成长股：增长轴正、通胀轴负最佳；滞胀双杀(盈利降+贴现率升)。"},
}

ALLWEATHER = [
    {"sleeve": "美国长期国债 (TLT)", "pct": 40.0, "bias": "通缩/衰退 Deflation"},
    {"sleeve": "美国中期国债 (IEF)", "pct": 15.0, "bias": "久期压舱 ballast"},
    {"sleeve": "美股 (SPY)",        "pct": 30.0, "bias": "增长上行 Growth↑"},
    {"sleeve": "大宗商品 (DBC)",     "pct": 7.5,  "bias": "通胀上行 Inflation↑"},
    {"sleeve": "黄金 (GC=F)",       "pct": 7.5,  "bias": "滞胀/贬值 Stagflation"},
]


# ── 因果原语 ─────────────────────────────────────────────────────────────
def causal_z(x: pd.Series, mode: str = "expanding") -> pd.Series:
    """因果 z：均值/标准差只用 t 之前的数据（靠 .shift(1)）。"""
    if mode == "rolling":
        mu = x.rolling(ROLL_WIN, min_periods=Z_MIN).mean().shift(1)
        sd = x.rolling(ROLL_WIN, min_periods=Z_MIN).std().shift(1)
    else:
        mu = x.expanding(min_periods=Z_MIN).mean().shift(1)
        sd = x.expanding(min_periods=Z_MIN).std().shift(1)
    return ((x - mu) / sd).clip(-Z_CLIP, Z_CLIP)


def momentum(s: pd.Series) -> pd.Series:
    """63 日对数变化（Dalio = 意外/变化，非水平）。价格下限保护。"""
    s = s.clip(lower=PRICE_FLOOR)
    return np.log(s) - np.log(s.shift(MOM_DAYS))


def _leg_series(expr: str, px: pd.DataFrame) -> pd.Series:
    """A/B 比值（先内连接、再有界 ffill）或单 ticker。"""
    parts = [p.strip() for p in expr.split("/")]
    if len(parts) == 2:
        a, b = parts
        df = pd.concat([px[a].rename("a"), px[b].rename("b")], axis=1).dropna().sort_index()
        df = df.ffill(limit=FFILL)
        return (df["a"] / df["b"]).rename(expr)
    return px[parts[0]].dropna().ffill(limit=FFILL).rename(expr)


def _axis(legs: list[dict], px: pd.DataFrame, mode: str) -> tuple[pd.Series, pd.DataFrame]:
    zs = {leg["name"]: causal_z(momentum(_leg_series(leg["expr"], px)), mode=mode) for leg in legs}
    Z = pd.DataFrame(zs).dropna()                       # 要求所有腿都在
    w = pd.Series({leg["name"]: leg["weight"] for leg in legs})
    w = w / w.sum()
    composite = (Z * w).sum(axis=1)                     # 已是 z 单位；不再二次标准化
    return composite, Z


def _label(g: pd.Series, i: pd.Series) -> pd.Series:
    out, cur = [], None
    for gt, it in zip(g, i):
        gs = cur[0] if cur else ("+" if gt >= 0 else "-")
        is_ = cur[1] if cur else ("+" if it >= 0 else "-")
        if gt > DEADBAND:
            gs = "+"
        elif gt < -DEADBAND:
            gs = "-"
        if it > DEADBAND:
            is_ = "+"
        elif it < -DEADBAND:
            is_ = "-"
        cur = (gs, is_)
        out.append(QUADRANTS[cur])
    return pd.Series(out, index=g.index, name="quadrant")


def _days_in_regime(labels: pd.Series) -> pd.Series:
    out, n, prev = [], 0, None
    for v in labels:
        n = n + 1 if v == prev else 1
        out.append(n)
        prev = v
    return pd.Series(out, index=labels.index, name="days_in_regime")


# ── 公开 API ─────────────────────────────────────────────────────────────
def build_axes(px: pd.DataFrame, mode: str = "expanding"):
    """返回 (axes_df, growth_leg_z, inflation_leg_z)。

    axes_df 列：growth_z, inflation_z, quadrant, days_in_regime（限定到 START 起）。
    px 列须含 TICKERS。
    """
    growth, gz = _axis(GROWTH_LEGS, px, mode)
    infl, iz = _axis(INFLATION_LEGS, px, mode)
    df = pd.concat([growth.rename("growth_z"), infl.rename("inflation_z")],
                   axis=1).dropna().sort_index()
    df = df.loc[START:]
    df["quadrant"] = _label(df["growth_z"], df["inflation_z"])
    df["days_in_regime"] = _days_in_regime(df["quadrant"])
    return df, gz, iz


def component_contrib(gz: pd.DataFrame, iz: pd.DataFrame, at) -> dict:
    out = {"growth": [], "inflation": []}
    for axis_name, Z, legs in (("growth", gz, GROWTH_LEGS), ("inflation", iz, INFLATION_LEGS)):
        w = pd.Series({l["name"]: l["weight"] for l in legs})
        w = w / w.sum()
        z_last = Z.reindex([at]).iloc[0]
        for l in legs:
            zv = float(z_last[l["name"]])
            out[axis_name].append({"leg": l["name"], "expr": l["expr"],
                                   "z": zv, "contrib": zv * float(w[l["name"]])})
    return out


def axis_correlation(axes_df: pd.DataFrame, window: int = 126) -> pd.Series:
    return axes_df["growth_z"].rolling(window).corr(axes_df["inflation_z"])


def forward_return_study(axes_df: pd.DataFrame, tracked_px: pd.DataFrame,
                         horizons: list[int] | None = None) -> pd.DataFrame:
    """按资产、按象限的远期收益。绝不跨资产混合。

    标签 +1 bar（前一收盘可知）。报 eff_n = 该象限天数/H（每日 H 日窗口重叠、非独立），
    eff_n<5 打 low_n。tracked_px 列 = gold/btc/ndx 收盘。
    """
    horizons = horizons or HORIZONS
    label = axes_df["quadrant"].shift(1).dropna()
    rows = []
    for akey in ("gold", "btc", "ndx"):
        if akey not in tracked_px.columns:
            continue
        px = tracked_px[akey].dropna()
        for H in horizons:
            fwd = (px.shift(-H) / px - 1.0).reindex(label.index).dropna()
            lab = label.reindex(fwd.index)
            for q in QUADRANTS.values():
                vals = fwd[lab == q]
                n = int(len(vals))
                eff = n / H if H else n
                rows.append({"asset": akey, "horizon": H, "quadrant": q,
                             "n_days": n, "eff_n": round(eff, 1),
                             "mean": float(vals.mean()) if n else np.nan,
                             "median": float(vals.median()) if n else np.nan,
                             "hit": float((vals > 0).mean()) if n else np.nan,
                             "low_n": eff < 5})
    return pd.DataFrame(rows)
