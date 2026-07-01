"""RRG (Relative Rotation Graph) — 纯计算层,因果、无前视、仅 Yahoo 价格。

RS-Ratio / RS-Momentum 的真实 JdK 公式是**专有的**。这里是明确标注的开源近似:
  RS       = 100 * P_sector / P_SPY                      (相对强弱)
  RS_Ratio = 100 + K * causal_z( EMA(RS 水平) )          (对 RS 的**水平**做因果 z)
  RS_Mom   = 100 + K * causal_z( EMA( ΔRS_Ratio ) )      (对 RS_Ratio 的变化率做因果 z)

关键修正(来自对抗评审):RS-Ratio 用 RS **水平**的 z,而非 (ema_fast-ema_slow)/ema_slow
那种 MACD 式离差振荡器——后者会把"加速领涨"错标进 Weakening。用水平 z 后,单调/加速
的领涨者稳定落在 Leading,且顺时针旋转自然涌现。

因果性:所有 EMA/rolling 截止到 t,归一化的均值/标准差用 .shift(1) → 只用 t 之前的数据。
z 做 ±3 截断,防止安静行情里极小标准差制造巨大 z(评审确认过的坑)。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BENCH = "SPY"
SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"]
SECTORS_CORE = [s for s in SECTORS if s not in ("XLRE", "XLC")]   # 深历史模式(9 个,回溯 ~2000)

NAMES = {
    "XLK": "科技", "XLF": "金融", "XLE": "能源", "XLV": "医疗", "XLI": "工业",
    "XLY": "非必需消费", "XLP": "必需消费", "XLU": "公用事业", "XLB": "原材料",
    "XLRE": "房地产", "XLC": "通信服务",
}
COLORS = {
    "XLK": "#4d8fdb", "XLF": "#3dba6a", "XLE": "#e8a23d", "XLV": "#e05555", "XLI": "#9a7bff",
    "XLY": "#e879c0", "XLP": "#5cc2c2", "XLU": "#c0a35c", "XLB": "#7fb069",
    "XLRE": "#d17a4a", "XLC": "#8a8fd0",
}
QUAD_ORDER = ["Leading", "Weakening", "Lagging", "Improving"]
QUAD_CN = {"Leading": "领先", "Weakening": "转弱", "Lagging": "落后", "Improving": "改善"}
QCOLOR = {"Leading": "#3dba6a", "Weakening": "#e8a23d", "Lagging": "#e05555", "Improving": "#4d8fdb"}

# 周线参数
SMOOTH = 5     # RS 水平的轻度 EMA 平滑
M = 5          # RS_Ratio 的变化率回看(周)= 动量视野
D2 = 5         # 动量平滑
N = 52         # 因果 z 的滚动窗(1 年)
MP = 26        # 发出一个点前所需的最少自身历史(周)
K = 2.0        # 视觉缩放:z=+1 -> 102。仅影响刻度,象限由 sign 决定
CLIP = 3.0     # z 截断,防安静行情爆表
TAIL = 12      # 尾迹默认长度(周),JdK 常用 10-14


def to_weekly(close_daily: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """日线复权收盘 → 周五锚定的周线(每周最后一个收盘)。返回 (周线, 是否含未完成的当周)。"""
    wk = close_daily.resample("W-FRI").last()
    partial = bool(close_daily.index.max() < wk.index.max())
    return wk, partial


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False, min_periods=span).mean()


def _causal_z(x: pd.Series, k: float = K) -> pd.Series:
    """截止 t 前的滚动均值/标准差(.shift(1)),z 做 ±CLIP 截断。"""
    mu = x.rolling(N, min_periods=MP).mean().shift(1)
    sd = x.rolling(N, min_periods=MP).std(ddof=1).shift(1)
    z = (x - mu) / sd.replace(0, np.nan)
    return z.clip(-CLIP, CLIP)


def rrg_frame(closes_wk: pd.DataFrame, sectors: list[str] | None = None,
              k: float = K) -> dict[str, pd.DataFrame]:
    """每个板块 -> 周线 DataFrame(列 ratio, mom)。最后一行=箭头,最后 TAIL 行=尾迹。

    按板块各自的历史计算(不做跨板块 dropna),晚上市的板块从其上市起才有点。
    """
    sectors = sectors or SECTORS
    b = closes_wk[BENCH]
    out: dict[str, pd.DataFrame] = {}
    for tk in sectors:
        if tk not in closes_wk.columns:
            continue
        p = closes_wk[tk].dropna()
        rs = (100.0 * p / b.reindex(p.index)).dropna()
        if len(rs) < N:                       # 历史不足一年,跳过
            continue
        rs_sm = _ema(rs, SMOOTH)
        ratio = 100 + k * _causal_z(rs_sm)             # 对 RS 水平做因果 z(核心修正)
        roc = ratio - ratio.shift(M)                   # RS_Ratio 的变化率
        mom = 100 + k * _causal_z(_ema(roc, D2))       # 单次归一化(不叠加二次 z)
        df = pd.DataFrame({"ratio": ratio, "mom": mom}).dropna()
        if not df.empty:
            out[tk] = df
    return out


def quadrant(x: float, y: float) -> str:
    """x=RS_Ratio, y=RS_Mom,以 100 为中心分四象限。"""
    if x >= 100 and y >= 100:
        return "Leading"        # 强且更强
    if x >= 100 and y < 100:
        return "Weakening"      # 强但动量转弱
    if x < 100 and y < 100:
        return "Lagging"        # 弱且更弱
    return "Improving"          # 弱但动量改善


def quad_series(df: pd.DataFrame) -> pd.Series:
    return df.apply(lambda r: quadrant(r["ratio"], r["mom"]), axis=1)


def weeks_in_current(qs: pd.Series) -> int:
    """当前象限已持续多少周。"""
    if qs.empty:
        return 0
    cur, n = qs.iloc[-1], 0
    for v in reversed(qs.tolist()):
        if v == cur:
            n += 1
        else:
            break
    return n


def first_valid_dates(frames: dict[str, pd.DataFrame]) -> dict[str, pd.Timestamp]:
    """每个板块第一个可绘制点的日期(经验预热,不硬编码)。"""
    return {tk: df.index.min() for tk, df in frames.items()}


def forward_return_study(closes_wk: pd.DataFrame,
                         frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """按 (板块,象限) 的**下一周**收益。信号在 t 已知,收益在 (t, t+1] 实现(滞后一周,无前视)。

    closes_wk 须为**已完成周**(调用方已剔除未完成当周)。周收益非重叠 -> 每周独立观测。
    """
    rows = []
    for tk, df in frames.items():
        fwd = closes_wk[tk].pct_change().shift(-1)     # fwd[t] = (t, t+1] 收益
        qs = quad_series(df)
        f = fwd.reindex(qs.index)
        for name in QUAD_ORDER:
            v = f[qs == name].dropna()
            n = int(len(v))
            rows.append({"sector": tk, "quadrant": name, "n": n,
                         "mean": float(v.mean()) if n else np.nan,
                         "hit": float((v > 0).mean()) if n else np.nan})
    return pd.DataFrame(rows)
