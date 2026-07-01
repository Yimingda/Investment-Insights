"""GEM 双动量 —— 纯计算层,因果、无前视,仅用 Yahoo 总回报收盘。

规则(每月末 t,12 月回看):
  绝对动量:SPY 的 12 月回报 > 国库券的 12 月回报?
    是 → 相对动量:SPY vs 海外,谁 12 月回报高就持谁
    否 → 持债(AGG)
决策在 t 月末做(只用 ≤ t 的价格),持仓赚 t→t+1 月的收益(shift(-1) 只加在收益上)。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

US_TK = "SPY"
EXUS_CHOICES = {"VEU": "全球除美(含新兴)", "ACWX": "全球除美(含新兴)", "EFA": "发达市场除美(不含新兴)"}
BOND_CHOICES = {"AGG": "美国综合债", "BND": "美国综合债"}
CASH_CHOICES = {"BIL": "1-3月国库券ETF(总回报)", "^IRX": "13周国库券贴现收益率(近似)"}
SLEEVE_COLOR = {"US": "#4d8fdb", "EXUS": "#3dba6a", "BONDS": "#e8a23d"}
SLEEVE_CN = {"US": "美股 SPY", "EXUS": "海外股", "BONDS": "债券 AGG"}


def to_monthly(close: pd.DataFrame) -> pd.DataFrame:
    """日线 → 月末("ME";需 pandas>=2.2)。绝不用 "MS"(月初,会平移网格、破坏契约)。"""
    return close.resample("ME").last()


def trailing_return(s: pd.Series, L: int) -> pd.Series:
    """截止 t 的 L 月总回报:只用 t 和 t-L 的收盘 → ≤ t。"""
    return s / s.shift(L) - 1.0


def cash_return(cash_choice: str, m: pd.DataFrame, irx: pd.Series, L: int) -> pd.Series:
    if cash_choice == "BIL":
        # BIL 总回报(auto_adjust)已把国库券收益计入,这就是现金回报,不要再加一层收益。
        return m["BIL"] / m["BIL"].shift(L) - 1.0
    # ^IRX 是**年化贴现收益率(百分数)**,不是价格 → 绝不能 pct_change。
    # 用**前一月末**已知的收益率累计成月回报(因果),再复利 L 个月。
    y = (irx.reindex(m.index).ffill() / 100.0).clip(lower=0.0)     # 十进制年率
    m1 = (1.0 + y.shift(1)) ** (1.0 / 12.0) - 1.0                  # 前一月末定的 1 月累计
    return (1.0 + m1).rolling(L).apply(np.prod, raw=True) - 1.0


def decide(r_us, r_exus, r_cash):
    """返回 'US' | 'EXUS' | 'BONDS' | None。输入均为 t 时刻已知的标量。"""
    if any(pd.isna(x) for x in (r_us, r_exus, r_cash)):
        return None                                    # 预热/缺历史 → 不持仓
    if r_us > r_cash:                                  # 绝对动量为正(SPY vs 国库券)
        return "US" if r_us >= r_exus else "EXUS"      # 相对赢家(平手 → US,已声明)
    return "BONDS"                                      # 风险关闭 → 持债


def build_signals(m: pd.DataFrame, exus_tk: str, bond_tk: str,
                  cash_choice: str, L: int) -> pd.DataFrame:
    sig = pd.DataFrame(index=m.index)
    sig["r_us"] = trailing_return(m[US_TK], L)
    sig["r_exus"] = trailing_return(m[exus_tk], L)
    sig["r_cash"] = cash_return(cash_choice, m, m["^IRX"], L)
    # dtype=object:pandas>=2.2 下从含 None 的 list 建列会把 None 变成 float nan → col[nan] KeyError
    sig["hold"] = pd.Series([decide(a, b, c) for a, b, c in
                             zip(sig.r_us, sig.r_exus, sig.r_cash)],
                            index=m.index, dtype=object)
    return sig


def backtest(m: pd.DataFrame, sig: pd.DataFrame, exus_tk: str, bond_tk: str):
    """在 t 决策、赚 t→t+1。返回 (strat, bench, eq_s, eq_b)。"""
    assert sig.index.isin(m.index).all(), "sig 与 m 的月度网格必须一致(单一 dropna 源)"
    col = {"US": US_TK, "EXUS": exus_tk, "BONDS": bond_tk}
    fwd = m.pct_change().shift(-1)                      # fwd[t] = (t, t+1] 收益;末行 NaN
    strat = pd.Series(index=sig.index, dtype=float)
    for t in sig.index:
        h = sig.at[t, "hold"]
        if not isinstance(h, str):                     # None/NaN 预热行 → 跳过
            continue
        r = fwd.at[t, col[h]]
        if pd.isna(r):                                 # 末行/缺失
            continue
        strat.at[t] = r                                # t 决策,t→t+1 实现
    strat = strat.dropna()
    bench = fwd[US_TK].reindex(strat.index).dropna()   # SPY 买入持有,同窗口同口径
    strat = strat.reindex(bench.index)
    eq_s = (1 + strat).cumprod()
    eq_b = (1 + bench).cumprod()
    return strat, bench, eq_s, eq_b


def stats(eq: pd.Series, ret: pd.Series) -> dict:
    n = len(ret)
    if n == 0:
        return dict(cagr=np.nan, vol=np.nan, maxdd=np.nan, sharpe0=np.nan, months=0,
                    dd=pd.Series(dtype=float))
    cagr = eq.iloc[-1] ** (12.0 / n) - 1.0
    vol = ret.std(ddof=1) * (12 ** 0.5)
    dd = eq / eq.cummax() - 1.0
    return dict(cagr=cagr, vol=vol, maxdd=float(dd.min()),
                sharpe0=(ret.mean() * 12) / vol if vol else np.nan,  # rf=0,算术分子
                months=n, dd=dd)


def occupancy(sig: pd.DataFrame, strat: pd.Series):
    """在**已实现**窗口上算各 sleeve 占比 + 换手(在 dropna 后的 hold 上,避免 NaN 污染)。"""
    held = sig["hold"].reindex(strat.index).dropna()
    if held.empty:
        return pd.Series(dtype=float), 0, np.nan
    pct = held.value_counts(normalize=True)
    switches = int((held != held.shift(1)).sum()) - 1   # 减去第一行(无前值)
    switches = max(switches, 0)
    turnover = switches / (len(held) / 12.0)
    return pct, switches, turnover


def robustness(m: pd.DataFrame, exus_tk: str, bond_tk: str) -> pd.DataFrame:
    """lookback × cash 的稳健性网格(m 须同时含 BIL 与 ^IRX)。"""
    rows = []
    for L in (6, 9, 12):
        for cash in ("BIL", "^IRX"):
            sig = build_signals(m, exus_tk, bond_tk, cash, L)
            strat, bench, eq_s, eq_b = backtest(m, sig, exus_tk, bond_tk)
            if len(strat) < 24:
                rows.append({"回看": L, "现金": cash, "CAGR%": np.nan,
                             "MaxDD%": np.nan, "持债%": np.nan})
                continue
            s = stats(eq_s, strat)
            pct, _, _ = occupancy(sig, strat)
            rows.append({"回看": L, "现金": cash, "CAGR%": round(s["cagr"] * 100, 1),
                         "MaxDD%": round(s["maxdd"] * 100, 1),
                         "持债%": round(pct.get("BONDS", 0.0) * 100, 0)})
    return pd.DataFrame(rows)
