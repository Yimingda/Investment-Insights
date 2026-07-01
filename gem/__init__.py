"""双动量 GEM (Global Equities Momentum) 子包 —— 由投资面板顶部导航进入。

Gary Antonacci《Dual Momentum Investing》(2014)。月度、12 月回看,两道过滤:
相对动量(SPY vs 海外)+ 绝对动量(SPY vs 国库券)→ 否则持债。回测无前视
(在 t 月末决策、赚 t→t+1 月收益),数据 100% yfinance 实时总回报收盘。
"""
