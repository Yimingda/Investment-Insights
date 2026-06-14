"""品种模块注册表。

每个品种实现 AssetModule.build_snapshot(refresh) -> Snapshot，
共享 Dashboard 渲染器消费 Snapshot，从而做到"一套 UI、多个品种"。
"""
from __future__ import annotations

from .base import AssetModule
from .gold import GoldModule
from .crypto import CryptoModule
from .us_equity import USEquityModule
from .a_share import AShareModule
from .forex import ForexModule

REGISTRY: list[AssetModule] = [
    GoldModule(),
    CryptoModule(),
    USEquityModule(),
    AShareModule(),
    ForexModule(),
]


def get_module(asset_id: str) -> AssetModule:
    for m in REGISTRY:
        if m.id == asset_id:
            return m
    return REGISTRY[0]
