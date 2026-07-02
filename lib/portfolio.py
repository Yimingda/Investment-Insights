"""持仓监控 —— 一股一盘所需的数据模型 / 持久化 / 盈亏与建议逻辑。

- 持仓表(代码/名称/成本价/股数)存本地 .holdings.json（已 gitignore）。
- CATALYSTS：每只「关键上涨影响因子」(基本面驱动 + 当前压制项)，供参考。
- verdict()：结合技术面评分 + 套牢深度，给出相对客观的持有/减仓/控险建议。
"""
from __future__ import annotations

import json
import os

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     ".holdings.json")

# 默认持仓（用户此前给的 12 只；成本价/股数默认 0，进页面自行填写）
DEFAULT_HOLDINGS = [
    ("002352", "顺丰控股"), ("600036", "招商银行"), ("600050", "中国联通"),
    ("600089", "特变电工"), ("600104", "上汽集团"), ("600276", "恒瑞医药"),
    ("600729", "重庆百货"), ("600941", "中国移动"), ("601166", "兴业银行"),
    ("601336", "新华保险"), ("601633", "长城汽车"), ("603501", "韦尔股份"),
]

# 每只「关键上涨影响因子」= 往上走要靠什么 → 当前主要压制项
CATALYSTS = {
    "002352": "快递量价企稳 + 时效件/国际及供应链放量 + 鄂州枢纽产能利用率提升、资本开支见顶回落 → 压制：价格战、油价与人力成本。",
    "600036": "净息差企稳 + 零售与财富管理复苏 + 地产风险出清、分红率提升(高股息) → 压制：息差下行、地产与化债敞口。",
    "600050": "算力/IDC与联通云等数字化第二曲线 + 5G ARPU 稳、提质增效高股息 → 压制：传统电信增长慢、资本开支大。",
    "600089": "特高压/电网投资加码 + 变压器出海 + 多晶硅价格回升 → 压制：多晶硅价格低迷拖累新能源板块。",
    "600104": "销量与出口(海外)回升 + 自主品牌/新能源转型见效 + 华为/大众等合作 → 压制：价格战、合资品牌萎缩。",
    "600276": "创新药放量与出海(license-out) + 集采影响出清 + 新品密集获批 → 压制：集采降价、研发或不及预期。",
    "600729": "消费复苏 + 参股马上消费金融贡献利润 + 区域零售整合、高股息 → 压制：线下零售长期承压。",
    "600941": "算力/移动云与数字化第二曲线 + 高分红「中特估」+ ARPU 稳 → 压制：传统业务见顶、资本开支高。",
    "601166": "净息差企稳 + 绿色/财富/投行「三张名片」+ 地产与城投风险出清、低估值修复 → 压制：资产质量担忧。",
    "601336": "负债端新单/NBV 改善 + 投资端权益回暖 + 利率企稳 → 压制：长端利率下行、权益市场波动(弹性大)。",
    "601633": "新能源与出海(坦克/皮卡/欧拉)放量 + 单车盈利改善、高端化 → 压制：国内价格战、新能源转型偏慢。",
    "603501": "手机 CIS 复苏与高端化 + 汽车 CIS(智能驾驶)放量 + 库存去化完成 → 压制：消费电子疲软、竞争加剧。",
}


def load_holdings() -> list[dict]:
    """返回持仓行 [{code,name,cost,shares}]；无文件→默认 12 只、成本/股数为 0。"""
    try:
        with open(_PATH, encoding="utf-8") as f:
            rows = json.load(f)
        out = []
        for r in rows:
            if r.get("code"):
                out.append({"code": str(r["code"]).strip(), "name": r.get("name", ""),
                            "cost": float(r.get("cost") or 0), "shares": float(r.get("shares") or 0)})
        if out:
            return out
    except Exception:
        pass
    return [{"code": c, "name": n, "cost": 0.0, "shares": 0.0} for c, n in DEFAULT_HOLDINGS]


def save_holdings(rows: list[dict]) -> bool:
    try:
        clean = [{"code": str(r["code"]).strip(), "name": r.get("name", ""),
                  "cost": float(r.get("cost") or 0), "shares": float(r.get("shares") or 0)}
                 for r in rows if str(r.get("code", "")).strip()]
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False)
        return True
    except Exception:
        return False


def pnl(price: float, cost: float, shares: float) -> dict:
    """盈亏 / 回本。cost<=0 视为未填。"""
    if not cost or cost <= 0:
        return {"has_cost": False}
    amt = (price - cost) * shares if shares else 0.0
    pct = (price - cost) / cost * 100
    to_breakeven = (cost - price) / price * 100 if price else 0.0   # 回本还需涨幅%
    return {"has_cost": True, "cost": cost, "shares": shares,
            "market_value": price * shares, "cost_value": cost * shares,
            "pnl_amt": amt, "pnl_pct": pct, "breakeven": cost,
            "to_breakeven": max(0.0, to_breakeven)}


def verdict(a: dict, cost: float = 0.0) -> tuple[str, str, str]:
    """结合技术面 + 套牢深度 → (级别标签, 颜色, 建议正文)。a 为 stocks.analyze() 结果。"""
    price, score, rsi = a["price"], a["score"], a["rsi"]
    below60 = price < a["ma60"]
    macd_up = (a.get("macd_hist") or 0) > 0
    pl = ((price - cost) / cost * 100) if cost and cost > 0 else None
    deep = pl is not None and pl <= -20        # 深套
    shallow = pl is not None and pl > -10       # 浅套

    # 技术面状态
    if score >= 60 and not below60:
        tech = "up"
    elif score >= 55 or rsi < 32 or macd_up:
        tech = "stab"
    elif score < 45 and below60 and not macd_up:
        tech = "weak"
    else:
        tech = "neutral"

    G, A_, R = "#3dba6a", "#e0a458", "#e05555"
    if tech == "up":
        return ("持有偏多", G,
                "技术转强、已站上 60 日线。可持有待回本；加仓等回调分批、不追高，仓位≤5%/只。")
    if tech == "stab":
        return ("持有搏反弹", G,
                "出现企稳/反弹迹象(RSI 低位或 MACD 金叉)。可持有搏反弹，反弹到压力位或回本附近先减压一部分。")
    if tech == "weak":
        if deep:
            return ("控制风险", R,
                    "深套且趋势未企稳——切忌下跌中盲目重仓补仓。先判断基本面(见关键因子)是否恶化："
                    "未恶化可分批持有、等右侧企稳信号再动；已恶化则认赔离场。务必设一条硬止损纪律。")
        return ("减仓/观望", A_,
                "趋势偏弱、仍在均线下方。浅套可持有观察，但跌破前低应减仓控险；不接飞刀、不急于补。")
    # neutral
    if shallow:
        return ("持有观察", A_,
                "信号中性、浅套。可持有观察，等量价或基本面催化明朗再决定加减。")
    return ("观望", A_,
            "信号中性。等待量价配合或基本面催化，小仓观察，暂不重仓补。")
