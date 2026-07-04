"""生成/刷新共享行情快照(供 极值追踪 / 宏观四象限 / RRG / GEM 四页读取)。

拉取所有页面用到的 ticker 并集的复权收盘 + 成交量,存成两个压缩 parquet:
  data/snapshot_close.parquet
  data/snapshot_volume.parquet
由 .github/workflows/refresh-data.yml 每日运行并提交。也可本地手动跑:
  python scripts/refresh_snapshot.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yfinance as yf

# 所有页面用到的 ticker 并集(新增页面记得在此补上)
TICKERS = sorted(set([
    # 极值追踪
    "GC=F", "BTC-USD", "^NDX", "GLD", "QQQ",
    # 宏观四象限 (Dalio) + 美林时钟代理
    "HG=F", "SPY", "SHY", "HYG", "LQD", "TIP", "IEF", "DBC", "CL=F",
    # 双动量 GEM
    "VEU", "ACWX", "EFA", "AGG", "BND", "BIL", "^IRX",
    # RRG 行业板块
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC",
]))

START = "1998-01-01"     # 覆盖 RRG 行业板块(~1998)与其它页的预热


def main() -> None:
    print(f"[snapshot] downloading {len(TICKERS)} tickers from {START} …")
    df = yf.download(TICKERS, start=START, interval="1d",
                     auto_adjust=True, progress=False)
    if df is None or len(df) == 0:
        raise SystemExit("yfinance returned no data")
    close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df
    vol = df["Volume"] if isinstance(df.columns, pd.MultiIndex) else None

    out = Path(__file__).resolve().parent.parent / "data"
    out.mkdir(exist_ok=True)
    # float32 足够(喂给 z-score/比价/动量,精度损失可忽略),文件减半、每日提交更省
    close.sort_index().astype("float32").to_parquet(
        out / "snapshot_close.parquet", compression="zstd")
    if vol is not None:
        vol.sort_index().astype("float32").to_parquet(
            out / "snapshot_volume.parquet", compression="zstd")
    print(f"[snapshot] saved close {close.shape} "
          f"({close.index.min().date()} → {close.index.max().date()})")


if __name__ == "__main__":
    main()
