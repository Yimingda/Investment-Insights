"""极值追踪 —— 纯计算层,仅用 Yahoo 价格/成交量。

信号(均为**滚动、截止 t 的**因果 nowcast;这是描述性温度计,非回测信号):
  px_ma_z : 价格相对 200 日均线的 z 分数(离均线多远)
  vol_z   : 成交量相对近 20 日的 z 分数(放量/缩量)
  ret_n   : 20 日动量(%)
  roro    : 跨资产风险偏好 = (BTC/黄金、纳指/黄金)比价的 90 日 z 均值
  gauge   : 以上标准化后取均值的**合成 regime 温度计**(±0.8 = TOP/BOTTOM 观察)
  ath/dd  : 历史新高(expanding max)与自新高回撤
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ASSETS = {"gold": "GC=F", "btc": "BTC-USD", "ndx": "^NDX"}
ASSET_CN = {"gold": "黄金", "btc": "比特币", "ndx": "纳指100"}
VOL_PROXY = {"gold": "GLD", "btc": "BTC-USD", "ndx": "QQQ"}   # 借用 ETF 成交量(^NDX 无量)
FETCH_TK = ["GC=F", "BTC-USD", "^NDX", "GLD", "QQQ"]

TOP_TYPES = {"avers_top", "euphoria_top", "growth_top"}
BOT_TYPES = {"policy_bottom", "crisis_bottom", "capitulation_bottom"}
HI, LO = 0.8, -0.8

# 策展事件(嵌入,免 pyyaml)。type: *_top / *_bottom / policy_pivot / shock
EVENTS = [
    {"id": "gold_ath_2011", "date": "2011-09-06", "asset": "gold", "type": "avers_top", "trigger": "美债上限危机 + 标普下调美国评级 + 欧债危机", "rotation": "风险 → 黄金/美债"},
    {"id": "btc_top_2017", "date": "2017-12-17", "asset": "btc", "type": "euphoria_top", "trigger": "CME 期货上市 + ICO 狂热顶", "rotation": "法币 → 加密(随后 ~85% 崩)"},
    {"id": "volmageddon_2018", "date": "2018-02-05", "asset": "ndx", "type": "growth_top", "trigger": "通胀升 + 加息担忧 + XIV 做空波动率爆仓", "rotation": "股/短波 → 现金"},
    {"id": "fed_pivot_2018", "date": "2018-12-24", "asset": "ndx", "type": "policy_bottom", "trigger": "鲍威尔转鸽,结束 2015-18 加息周期", "rotation": "现金 → 股(风险重启)"},
    {"id": "covid_crash_2020", "date": "2020-03-23", "asset": "ndx", "type": "crisis_bottom", "trigger": "新冠冲击 + 美联储无限 QE", "rotation": "一切 → 现金 → 流动性后全面再通胀"},
    {"id": "gold_ath_2020", "date": "2020-08-07", "asset": "gold", "type": "avers_top", "trigger": "负实际利率 + 大规模 QE + 弱美元", "rotation": "债/现金 → 黄金"},
    {"id": "btc_top_2021", "date": "2021-11-10", "asset": "btc", "type": "euphoria_top", "trigger": "流动性见顶,taper 临近", "rotation": "顶部派发(巨鲸转入交易所)"},
    {"id": "ndx_top_2021", "date": "2021-11-22", "asset": "ndx", "type": "growth_top", "trigger": "CPI >6%,美联储快速转鹰", "rotation": "成长/ARKK → 价值/现金"},
    {"id": "gold_geo_2022", "date": "2022-03-08", "asset": "gold", "type": "avers_top", "trigger": "俄乌战争 + 本轮首次加息", "rotation": "风险 → 黄金/商品"},
    {"id": "ndx_bottom_2022", "date": "2022-10-13", "asset": "ndx", "type": "policy_bottom", "trigger": "CPI 同比拐点 + 盘中深 V 反转", "rotation": "现金 → 股(试探)"},
    {"id": "ftx_btc_bottom_2022", "date": "2022-11-21", "asset": "btc", "type": "capitulation_bottom", "trigger": "FTX 破产 + 链上投降", "rotation": "加密 → 现金(投降=吸筹区)"},
    {"id": "svb_2023", "date": "2023-03-10", "asset": "btc", "type": "shock", "trigger": "SVB 倒闭 + BTFP 流动性兜底", "rotation": "银行股 → 黄金/BTC/大科技"},
    {"id": "fed_cut_2024", "date": "2024-09-18", "asset": "ndx", "type": "policy_pivot", "trigger": "美联储开启降息 -50bp", "rotation": "现金/货基 → 风险 + 黄金"},
    {"id": "btc_100k_2024", "date": "2024-12-05", "asset": "btc", "type": "euphoria_top", "trigger": "特朗普胜选 + 亲加密 + 现货 ETF 流入激增", "rotation": "法币/稳定币 → 加密"},
    {"id": "tariff_shock_2025", "date": "2025-04-02", "asset": "ndx", "type": "shock", "trigger": "'解放日'关税 → 暴跌;4/9 暂停 → 历史反弹", "rotation": "股 → 黄金/现金 → 快速再上险"},
    {"id": "dual_euphoria_2025", "date": "2025-10-06", "asset": "btc", "type": "euphoria_top", "trigger": "宽松 + 充裕流动性 + 央行购金/去美元化", "rotation": "疑似分阶段派发(待链上确认)"},
]


def ev_color(t: str) -> str:
    if t in TOP_TYPES:
        return "#e05555"
    if t in BOT_TYPES:
        return "#3dba6a"
    return "#8a8fa3"


def events_df(asset: str | None = None) -> pd.DataFrame:
    df = pd.DataFrame(EVENTS)
    df["date"] = pd.to_datetime(df["date"])
    if asset:
        df = df[df["asset"] == asset]
    return df.reset_index(drop=True)


def _roll_z(x: pd.Series, win: int, clip: float = 4.0) -> pd.Series:
    mp = max(10, win // 2)
    mu = x.rolling(win, min_periods=mp).mean()
    sd = x.rolling(win, min_periods=mp).std()
    return ((x - mu) / sd.replace(0, np.nan)).clip(-clip, clip)


def roro(closes: dict[str, pd.Series], win: int = 90) -> pd.Series:
    """跨资产风险偏好:BTC/黄金、纳指/黄金 两比价的 90 日 z 均值。>0 偏进攻,<0 偏避险。"""
    g = closes["gold"]
    z1 = _roll_z((closes["btc"] / g).dropna(), win)
    z2 = _roll_z((closes["ndx"] / g).dropna(), win)
    return pd.concat([z1, z2], axis=1).mean(axis=1)


def build(asset: str, close: pd.Series, vol: pd.Series,
          closes_all: dict[str, pd.Series]) -> pd.DataFrame:
    close = close.dropna()
    f = pd.DataFrame(index=close.index)
    f["close"] = close
    f["px_ma_z"] = _roll_z(close - close.rolling(200, min_periods=100).mean(), 200)
    f["vol_z"] = _roll_z(vol.reindex(close.index), 20)
    f["ret_n"] = close.pct_change(20) * 100
    f["roro"] = roro(closes_all).reindex(close.index)
    ret_z = _roll_z(f["ret_n"], 252)
    comp = pd.concat([f["px_ma_z"], f["vol_z"], f["roro"], ret_z], axis=1)
    f["gauge"] = comp.mean(axis=1)
    f["ath"] = close.cummax()
    f["dd"] = close / f["ath"] - 1.0
    return f


def runs(mask: pd.Series):
    """连续 True 的 (start, end) 区间。"""
    out, start, prev, inside = [], None, None, False
    for dt, v in mask.items():
        if bool(v) and not inside:
            start, inside = dt, True
        elif not bool(v) and inside:
            out.append((start, prev)); inside = False
        prev = dt
    if inside:
        out.append((start, prev))
    return out
