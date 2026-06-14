"""离线冒烟/回归测试：无需网络、无需安装 streamlit/plotly。

用法：python tests/test_smoke.py
原理：stub 掉 streamlit/plotly 的最小接口，并强制所有外部数据源返回 None，
从而在纯离线、确定性的条件下验证：
  - 全部品种 build_snapshot() 能产出合法 Snapshot；
  - 评分在合理区间、各面板字段齐全；
  - 规则引擎分析（无 key 降级路径）正常。
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _install_stubs():
    st = types.ModuleType("streamlit")

    def cache_data(*a, **k):
        def deco(fn):
            return fn
        return deco
    cache_data.clear = lambda: None
    st.cache_data = cache_data
    st.session_state = {}

    class _Secrets:
        def get(self, k, d=None):
            return d
    st.secrets = _Secrets()
    sys.modules["streamlit"] = st

    plotly = types.ModuleType("plotly")
    go = types.ModuleType("plotly.graph_objects")
    plotly.graph_objects = go
    sys.modules["plotly"] = plotly
    sys.modules["plotly.graph_objects"] = go


def main():
    _install_stubs()
    from lib import data, ai, indicators
    from lib.model import Snapshot

    # 强制离线：所有外部数据源返回 None → 走降级路径
    data._yf = lambda: None
    data._ak = lambda: None
    data._requests = lambda: None

    # 指标自检
    seq = [10, 11, 12, 11, 13, 14, 13, 15, 16, 15, 17, 18, 17, 19, 20, 19]
    assert indicators.sma(seq, 5) is not None
    assert 0 <= indicators.rsi(seq, 14) <= 100
    assert indicators.drawdown_from_high(seq) <= 0

    from assets import REGISTRY
    assert len(REGISTRY) >= 5, "至少应注册 5 个品种"

    for m in REGISTRY:
        snap = m.build_snapshot(refresh=False)
        assert isinstance(snap, Snapshot), m.id
        assert snap.kpis and snap.indicators and snap.strategies and snap.related, m.id
        assert 5 <= snap.score <= 95, (m.id, snap.score)
        assert snap.score_label, m.id
        s, r, a, by_claude = ai.analyze(m.name, snap)
        assert s and r and a and by_claude is False, m.id
        # 分析文字应与仪表盘标签一致
        assert snap.score_label in s, (m.id, "形势文字未引用评分标签")
        print(f"  ✓ {m.id:9} score={snap.score:>2}/{snap.score_label} "
              f"指标={len(snap.indicators)} 卡={len(snap.extra_cards)}")

    print(f"OK: {len(REGISTRY)} 个品种全部通过离线冒烟测试")


if __name__ == "__main__":
    main()
