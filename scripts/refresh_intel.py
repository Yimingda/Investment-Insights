"""夜间批量刷新个股深度情报 —— DeepSeek 直调 12 只个股 + 9 个行业政策。

由 .github/workflows/refresh-intel.yml 每周日深夜定时调用：
  1) 只刷新超过 REFRESH_DAYS 天(默认 6)的条目，新鲜的跳过省钱；
  2) 逐条「检索材料(Google News RSS 免费) → DeepSeek 生成 → 校验清洗」，
     失败重试一次后跳过，成功的写回 data/intel.json，由 Action 提交进仓库；
  3) 云端/本地 app 的 intel._load_all() 自动读取该共享层(本地手动生成仍按较新者优先)。

说明：DeepSeek 无 Batch API，但 v4-flash 单价极低且 cron 落在北京凌晨非高峰时段，
直接顺序调用即可 —— 原「提交批量/轮询/pending 回收」两班制机制已整体移除。

环境变量：DEEPSEEK_API_KEY(必填)、DEEPSEEK_MODEL(默认 deepseek-v4-flash)、
          REFRESH_DAYS(默认 6)、DRY_RUN=1 只打印任务清单、ONLY="policy:银行,stock:600036" 过滤。
"""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import intel, llm, websearch                     # noqa: E402
from lib.portfolio import DEFAULT_HOLDINGS                # noqa: E402

BASE = os.path.join(ROOT, "data", "intel.json")
REFRESH_DAYS = float(os.environ.get("REFRESH_DAYS") or 6)

_INDUSTRIES = sorted(set(intel.INDUSTRY_OF.values()))


def load_base() -> dict:
    try:
        with open(BASE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def is_fresh(rec) -> bool:
    if not isinstance(rec, dict):
        return False
    try:
        return (time.time() - float(rec.get("generated_at") or 0)) < REFRESH_DAYS * 86400
    except Exception:
        return False


def build_tasks(base: dict) -> list[tuple[str, str, str]]:
    """[(kind, key, 人类可读tag)]。kind=stock 时 key=代码；kind=policy 时 key=行业。"""
    tasks = []
    for code, name in DEFAULT_HOLDINGS:
        if is_fresh(base.get("stocks", {}).get(code)):
            print(f"  跳过(新鲜) stock:{code} {name}")
            continue
        tasks.append(("stock", code, f"stock:{code}"))
    for ind in _INDUSTRIES:
        if is_fresh(base.get("policies", {}).get(ind)):
            print(f"  跳过(新鲜) policy:{ind}")
            continue
        tasks.append(("policy", ind, f"policy:{ind}"))
    only = {s.strip() for s in os.environ.get("ONLY", "").split(",") if s.strip()}
    if only:                                  # 调试用：ONLY="policy:银行,stock:600036"
        tasks = [t for t in tasks if t[2] in only]
    return tasks


def _gen(kind: str, key: str, api_key: str):
    """单条生成。返回 (rec|None, cost)。失败自动重试一次（llm.chat 内部还有 JSON 重试）。"""
    name = dict(DEFAULT_HOLDINGS).get(key, key) if kind == "stock" else key
    total = 0.0
    for attempt in (1, 2):
        if kind == "stock":
            prompt = intel.stock_prompt(key, name, websearch.stock_material(key, name))
            d, c = llm.chat(prompt, api_key=api_key, max_tokens=8000,
                            schema=intel._STOCK_SCHEMA, category="个股情报")
        else:
            prompt = intel.policy_prompt(key, websearch.policy_material(key))
            d, c = llm.chat(prompt, api_key=api_key, max_tokens=6000,
                            schema=intel._POLICY_SCHEMA, category="行业政策")
        total += c
        if d == "__AUTH__":
            raise SystemExit("❌ DEEPSEEK_API_KEY 无效或已被吊销")
        if isinstance(d, dict):
            rec = intel.build_stock_rec(d) if kind == "stock" else intel.build_policy_rec(d)
            return rec, total
        print(f"    …第 {attempt} 次失败({llm.LAST_FAIL})", flush=True)
    return None, total


def main() -> int:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key.startswith("sk-"):
        print("❌ 未配置 DEEPSEEK_API_KEY(GitHub 仓库 Settings → Secrets → Actions)")
        return 1

    base = load_base()
    tasks = build_tasks(base)
    if os.environ.get("DRY_RUN"):
        print(f"DRY RUN: 待刷新 {len(tasks)} 个")
        for _, _, tag in tasks:
            print("  DRY:", tag)
        return 0
    if not tasks:
        print("全部新鲜，无需刷新。")
        return 0

    print(f"待刷新任务: {len(tasks)} 个 (超过 {REFRESH_DAYS:g} 天的条目)，模型 {llm.model_name()}")
    ok = fail = 0
    total_cost = 0.0
    for kind, key, tag in tasks:
        try:
            rec, c = _gen(kind, key, api_key)
        except SystemExit:
            raise
        except Exception as e:
            rec, c = None, 0.0
            print(f"  ❌ {tag}: {type(e).__name__}")
        total_cost += c
        if rec is None:
            fail += 1
            print(f"  ❌ {tag}: 生成失败")
            continue
        if kind == "stock":
            base.setdefault("stocks", {})[key] = rec
        else:
            base.setdefault("policies", {})[key] = rec
        _write_base(base)                    # 逐条落盘：中途失败也保住已成功的
        ok += 1
        print(f"  ✅ {tag}")
    print(f"完成: 成功 {ok} / 失败 {fail} ≈ ${total_cost:.3f}")
    return 0 if ok or not fail else 2


def _write_base(base: dict):
    os.makedirs(os.path.dirname(BASE), exist_ok=True)
    with open(BASE, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=0)


if __name__ == "__main__":
    sys.exit(main())
