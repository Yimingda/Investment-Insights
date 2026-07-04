"""共享行情快照加载器 —— 冷启动读仓库里提交的 parquet(秒开),再尽力补最近几根。

背景:Streamlit Cloud 文件系统临时、且会休眠重启,`@st.cache_data` 内存缓存重启即失。
把每日 GitHub Action 生成的 parquet 快照**提交进仓库**,就随代码一起部署 → 冷启动不必
重下 16 年,只做一次极小的"补最近 5 天"实时拉取。快照缺失时自动回退到全量实时拉取。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

_DIR = Path(__file__).resolve().parent.parent / "data"
_CLOSE = _DIR / "snapshot_close.parquet"
_VOL = _DIR / "snapshot_volume.parquet"


@st.cache_data(ttl=86400, show_spinner=False)
def _committed():
    """读提交进仓库的快照(近乎瞬时)。缺失返回 (None, None)。"""
    if not _CLOSE.exists():
        return None, None
    close = pd.read_parquet(_CLOSE)
    close.index = pd.to_datetime(close.index)
    vol = None
    if _VOL.exists():
        vol = pd.read_parquet(_VOL)
        vol.index = pd.to_datetime(vol.index)
    return close.sort_index(), (vol.sort_index() if vol is not None else None)


@st.cache_data(ttl=3600, show_spinner="更新最新行情…")
def _topup(tickers: tuple[str, ...], need_vol: bool):
    """只拉最近 5 天,补上快照之后的最新 bar(尽力而为,失败返回 None)。"""
    try:
        import yfinance as yf
        df = yf.download(list(tickers), period="5d", interval="1d",
                         auto_adjust=True, progress=False)
        if df is None or len(df) == 0 or not isinstance(df.columns, pd.MultiIndex):
            return None, None
        close = df["Close"]
        vol = df["Volume"] if need_vol else None
        return close, vol
    except Exception:
        return None, None


@st.cache_data(ttl=86400, show_spinner="首次拉取行情(无快照,较慢)…")
def _full_live(tickers: tuple[str, ...], need_vol: bool, start: str):
    """快照缺失时的回退:全量实时拉取(旧行为)。"""
    try:
        import yfinance as yf
        df = yf.download(list(tickers), start=start, interval="1d",
                         auto_adjust=True, progress=False)
        if df is None or len(df) == 0 or not isinstance(df.columns, pd.MultiIndex):
            return None, None
        return df["Close"], (df["Volume"] if need_vol else None)
    except Exception:
        return None, None


def load(tickers: list[str], with_volume: bool = False, start: str = "1998-01-01"):
    """返回 (close_df, vol_df|None),列为 `tickers` 中可得的部分。

    冷启动路径:读提交的快照(秒开)+ 补最近 5 天。快照缺失则回退全量实时拉取。
    """
    close, vol = _committed()
    key = tuple(sorted(set(tickers)))
    if close is None:                                  # 无快照 → 回退全量实时拉取
        close, vol = _full_live(key, with_volume, start)
        if close is None:
            return None, None
    else:
        # 每日 Action 保证快照≤1 交易日新 → 仅当明显过期(>2 日,如 Action 挂了)才实时补
        last = close.index.max()
        stale_days = (pd.Timestamp.now().normalize() - last.normalize()).days
        if stale_days > 2:
            rc, rv = _topup(key, with_volume)
            if rc is not None:
                close = rc.combine_first(close)        # recent 覆盖重叠日,历史补齐其余
                if with_volume and rv is not None and vol is not None:
                    vol = rv.combine_first(vol)

    cols = [t for t in tickers if t in close.columns]
    out_close = close[cols]
    out_vol = None
    if with_volume and vol is not None:
        vcols = [t for t in tickers if t in vol.columns]
        out_vol = vol[vcols]
    return out_close, out_vol
