"""智能分析层：有 Anthropic API key 就调用 Claude，否则降级到规则引擎。

对外只暴露 analyze()，返回 (当前形势, 主要风险, 投资者建议, 是否由Claude生成)。
"""
from __future__ import annotations

from .model import Snapshot

# 默认模型：Claude Opus 4.8（最强）。可在 secrets 用 ANTHROPIC_MODEL 覆盖为
# claude-sonnet-4-6 / claude-haiku-4-5 等以控制成本。
DEFAULT_MODEL = "claude-opus-4-8"

_SYSTEM = (
    "你是一位严谨的中文投资分析师，服务于一个多品种行情监控面板。"
    "根据给定的结构化行情数据，输出三段简洁、专业、克制的中文分析：\n"
    "1) 当前形势：综合技术面与基本面给出方向判断；\n"
    "2) 主要风险：列出当前最值得关注的 2-3 个风险点；\n"
    "3) 投资者建议：一句可执行、强调仓位与风控的建议。\n"
    "要求：基于给定数据，不杜撰未提供的数字；不做收益保证；语言面向中文散户投资者。"
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "situation": {"type": "string"},
        "risks": {"type": "string"},
        "advice": {"type": "string"},
    },
    "required": ["situation", "risks", "advice"],
    "additionalProperties": False,
}


# ── 对外接口 ─────────────────────────────────────────────────
def analyze(asset_name: str, snap: Snapshot, api_key: str | None = None,
            model: str | None = None) -> tuple[str, str, str, bool]:
    if api_key:
        out = _claude_analyze(asset_name, snap, api_key, model or DEFAULT_MODEL)
        if out is not None:
            return out[0], out[1], out[2], True
    s, r, a = _rule_based(asset_name, snap)
    return s, r, a, False


# ── Claude 实现 ──────────────────────────────────────────────
def _claude_analyze(asset_name: str, snap: Snapshot, api_key: str, model: str):
    try:
        import anthropic
    except Exception:
        return None
    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=1500,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": _SCHEMA},
            },
            system=_SYSTEM,
            messages=[{"role": "user", "content": _build_facts_text(asset_name, snap)}],
        )
        import json
        text = next((b.text for b in resp.content if b.type == "text"), "")
        data = json.loads(text)
        return data["situation"], data["risks"], data["advice"]
    except Exception:
        # 任何失败（网络/额度/格式）都静默降级到规则引擎
        return None


def _build_facts_text(asset_name: str, snap: Snapshot) -> str:
    lines = [
        f"品种：{asset_name}",
        f"最新价：{snap.price_fmt}",
        f"近一日变动：{snap.change:+.2f}（{snap.change_pct:+.2f}%）",
        f"综合信号得分：{snap.score}/100（{snap.score_label}）",
    ]
    if snap.ma_ref:
        rel = "高于" if snap.price > snap.ma_ref else "低于"
        lines.append(f"价格{rel}{snap.ma_label or '均线'}（参考 {snap.ma_ref:,.2f}）")
    if snap.indicators:
        lines.append("关键指标：")
        for ind in snap.indicators:
            lines.append(f"  - {ind.name}：{ind.value}（{ind.badge_text}）")
    for k, v in snap.ai_facts.items():
        lines.append(f"{k}：{v}")
    lines.append("数据来源：" + ("实时行情" if snap.data_live else "示例/缓存数据"))
    return "\n".join(lines)


# ── 规则引擎降级（无需任何 API）──────────────────────────────
def _rule_based(asset_name: str, snap: Snapshot) -> tuple[str, str, str]:
    score = snap.score

    # 第一段：形势（直接复用仪表盘标签，保证与评分一致）
    trend = f"{asset_name}当前综合信号「{snap.score_label}」（得分 {score}/100）"

    ma_status = ""
    if snap.ma_ref:
        if snap.price > snap.ma_ref:
            ma_status = f"，价格高于{snap.ma_label or '均线'}，技术面维持多头结构"
        else:
            ma_status = f"，价格低于{snap.ma_label or '均线'}，技术面偏空，需警惕进一步下行"
    change_txt = f"，近一日{'上涨' if snap.change >= 0 else '下跌'} {abs(snap.change_pct):.2f}%"
    situation = f"{trend}{ma_status}{change_txt}。"

    # 第二段：风险（从看空/警示指标提取）
    bearish = [f"{i.name}（{i.badge_text}）" for i in snap.indicators if i.badge_cls == "badge-dn"]
    warn = [f"{i.name}（{i.badge_text}）" for i in snap.indicators if i.badge_cls == "badge-warn"]
    risk_items = bearish[:2] + warn[:2]
    if risk_items:
        risks = "当前最值得关注的风险：" + "；".join(risk_items[:3]) + "。"
    else:
        risks = "当前主要指标未见明显偏空信号，但仍需警惕宏观与流动性层面的超预期变化。"

    # 第三段：建议
    if score >= 60:
        advice = "结构性偏多逻辑较完整，可在回调区间分批建仓，单一品种仓位建议控制在组合的15%以内，切勿一次性满仓。"
    elif score >= 45:
        advice = "信号中性，方向尚不明朗，建议以观望为主，等待趋势确认后再做仓位决策，不宜追涨杀跌。"
    else:
        advice = "多项指标偏空，建议以控制风险为先，已有仓位严格执行止损，新仓等待企稳信号后再逢低布局。"

    return situation, risks, advice
