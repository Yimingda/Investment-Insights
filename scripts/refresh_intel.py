"""夜间批量刷新个股深度情报 —— 生成 12 只个股 + 9 个行业政策。

由 .github/workflows/refresh-intel.yml 定时调用(周日深夜两班：提交 + 回收)。

双路由(2026-08)，看模型名：
  • claude*  → 原 Anthropic Message Batches 路径(token 五折 + 提交/回收两班制)：
      1) 先回收未完成批次(pending 文件或服务端嗅探到的孤儿批)，已付费结果绝不浪费；
      2) 只刷新超过 REFRESH_DAYS 天(默认 6)的条目，新鲜的跳过省钱；
      3) 提交后轮询至完成(最长 ~55 分钟)，超时留 pending 下次回收。
  • 其它(默认 deepseek-v4-flash) → DeepSeek 没有 Batches API(拿不到五折)，改为
      逐条并发调用、当场收结果。V4 Flash $0.14/$0.28 per MTok 比 Sonnet 便宜约 20 倍，
      即使没有批量五折，整体仍比 Claude 批量便宜近一个数量级。

结果(严格 JSON)写回 data/intel.json，由 Action 提交进仓库；云端/本地 app 的
intel._load_all() 自动读取该共享层(本地手动生成仍按较新者优先)。

custom_id 规则(可反解,不依赖 pending 里的映射)：stock-<code> / policy-<N>(N=行业排序序号)。
环境变量：DEEPSEEK_API_KEY(默认路径必填) / ANTHROPIC_API_KEY(回滚 claude* 时必填)、
          TAVILY_API_KEY(DeepSeek 联网检索用，缺失则只用训练知识)、
          LLM_MODEL 或 ANTHROPIC_MODEL(默认 deepseek-v4-flash)、
          REFRESH_DAYS(默认 6)、DRY_RUN=1 只打印任务清单、ONLY="policy:银行,stock:600036" 过滤、
          MAX_WORKERS(DeepSeek 并发数，默认 4)。
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:            # 本地 Windows 控制台是 GBK，日志里的 ✅/❌/⚠️ 会直接抛 UnicodeEncodeError
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from lib import intel, llm                               # noqa: E402
from lib.portfolio import DEFAULT_HOLDINGS               # noqa: E402

BASE = os.path.join(ROOT, "data", "intel.json")
PENDING = os.path.join(ROOT, "data", "intel_pending_batch.json")
MODEL = os.environ.get("LLM_MODEL") or os.environ.get("ANTHROPIC_MODEL") or "deepseek-v4-flash"
REFRESH_DAYS = float(os.environ.get("REFRESH_DAYS") or 6)
POLL_SECS, MAX_WAIT = 60, 55 * 60
MAX_WORKERS = max(1, int(os.environ.get("MAX_WORKERS") or 4))
MAX_SEARCHES = 2                     # 与 Anthropic 路径的 web_search max_uses 对齐

_INDUSTRIES = sorted(set(intel.INDUSTRY_OF.values()))


def cid_decode(cid: str) -> tuple[str | None, str | None, str]:
    """custom_id → (kind, key, 人类可读tag)。规则确定，无需持久化映射。"""
    if cid.startswith("stock-"):
        code = cid[6:]
        return "stock", code, f"stock:{code}"
    if cid.startswith("policy-"):
        try:
            ind = _INDUSTRIES[int(cid[7:])]
            return "policy", ind, f"policy:{ind}"
        except Exception:
            pass
    return None, None, cid


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


def build_jobs(base: dict) -> list[dict]:
    """待刷新任务(与供应商无关)：{custom_id, prompt, schema, max_tokens}。"""
    jobs = []
    for code, name in DEFAULT_HOLDINGS:
        if is_fresh(base.get("stocks", {}).get(code)):
            print(f"  跳过(新鲜) stock:{code} {name}")
            continue
        jobs.append({"custom_id": f"stock-{code}", "prompt": intel.stock_prompt(code, name),
                     "schema": intel._STOCK_SCHEMA, "max_tokens": 16000})
    for n, ind in enumerate(_INDUSTRIES):
        if is_fresh(base.get("policies", {}).get(ind)):
            print(f"  跳过(新鲜) policy:{ind}")
            continue
        jobs.append({"custom_id": f"policy-{n}", "prompt": intel.policy_prompt(ind),
                     "schema": intel._POLICY_SCHEMA, "max_tokens": 12000})
    only = {s.strip() for s in os.environ.get("ONLY", "").split(",") if s.strip()}
    if only:                                  # 调试用：ONLY="policy:银行,stock:600036"
        jobs = [j for j in jobs if cid_decode(j["custom_id"])[2] in only]
    return jobs


def _batch_requests(jobs: list[dict]) -> list[dict]:
    """jobs → Anthropic Batches 的请求体。"""
    return [{"custom_id": j["custom_id"],
             "params": _params(j["prompt"], j["schema"], j["max_tokens"])} for j in jobs]


def _params(prompt: str, schema: dict, max_tokens: int) -> dict:
    return {
        "model": MODEL,
        "max_tokens": max_tokens,
        "thinking": {"type": "adaptive"},
        "tools": [{"type": "web_search_20260209", "name": "web_search", "max_uses": 2}],
        "output_config": {"format": {"type": "json_schema", "schema": schema}},
        "messages": [{"role": "user", "content": prompt}],
    }


def resolve_pending(client, has_stale: bool) -> str | None:
    """待回收批次：pending 文件优先；否则服务端嗅探孤儿批(pending 落库失败的兜底)。
    批次只会由本脚本提交，嗅探安全。"""
    try:
        with open(PENDING, encoding="utf-8") as f:
            bid = json.load(f).get("batch_id")
        if bid:
            return bid
    except Exception:
        pass
    try:
        now = datetime.now(timezone.utc)
        for b in client.messages.batches.list(limit=10):
            age_d = (now - b.created_at).total_seconds() / 86400
            if b.processing_status != "ended" and age_d < 7:
                print(f"嗅探到未完成孤儿批 {b.id}(创建于 {age_d:.1f} 天前)，接管回收。")
                return b.id
            if b.processing_status == "ended" and age_d < 2 and has_stale:
                print(f"嗅探到已完成但未回收的孤儿批 {b.id}(创建于 {age_d:.1f} 天前)，先回收。")
                return b.id
    except Exception as e:
        print(f"(孤儿嗅探失败，忽略: {type(e).__name__})")
    return None


def main() -> int:
    is_claude = llm.is_claude(MODEL)
    api_key = (os.environ.get("ANTHROPIC_API_KEY", "") if is_claude
               else os.environ.get("DEEPSEEK_API_KEY", ""))
    if is_claude and not api_key.startswith("sk-ant-"):
        print("❌ 未配置 ANTHROPIC_API_KEY(GitHub 仓库 Settings → Secrets → Actions)")
        return 1
    if not is_claude and not api_key.strip():
        print("❌ 未配置 DEEPSEEK_API_KEY(GitHub 仓库 Settings → Secrets → Actions)")
        return 1
    print(f"模型: {MODEL}（{'Anthropic 批量五折' if is_claude else 'DeepSeek 并发直调'}）")
    if not is_claude and not os.environ.get("TAVILY_API_KEY"):
        print("⚠️ 未配置 TAVILY_API_KEY —— DeepSeek 无法联网，生成内容只能来自训练知识(可能滞后)。")

    base = load_base()
    jobs = build_jobs(base)
    if os.environ.get("DRY_RUN"):
        print(f"DRY RUN: 待刷新 {len(jobs)} 个")
        for j in jobs:
            print("  DRY:", cid_decode(j["custom_id"])[2])
        return 0

    if not is_claude:
        return _main_deepseek(jobs, base, api_key)

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    # ── 第一步：回收(pending / 孤儿)，已付费结果绝不浪费 ──
    pend_id = resolve_pending(client, has_stale=bool(jobs))
    if pend_id:
        print(f"回收批次 {pend_id} …")
        if not _wait_ended(client, pend_id):
            print("该批仍在处理，本次不提交新批(pending 保留，下次再收)。")
            _save_pending(pend_id)
            return 0
        ok, fail = _collect(client, pend_id, base)
        _clear_pending()
        if ok:
            _write_base(base)
        elif fail:
            print("⚠️ 回收批次全部失败——本次不再提交新批，避免同日烧第二批；请查上面的失败原因。")
            return 2
        base = load_base()
        jobs = build_jobs(base)              # 回收后重算剩余过期项

    if not jobs:
        print("全部新鲜，无需刷新。")
        return 0

    # ── 第二步：提交新批(五折) ──
    print(f"待刷新任务: {len(jobs)} 个 (超过 {REFRESH_DAYS:g} 天的条目)")
    batch = client.messages.batches.create(requests=_batch_requests(jobs))
    _save_pending(batch.id)
    print(f"批量任务已提交: {batch.id}(五折计费)，开始轮询…")
    if not _wait_ended(client, batch.id):
        print(f"⚠️ 超时未完成(batch={batch.id})。pending 已写盘待 Action 提交，下次运行自动回收。")
        return 0
    ok, fail = _collect(client, batch.id, base)
    if ok:
        _write_base(base)
        _clear_pending()
        return 0
    print(f"完成: 全部失败({fail})。pending 保留(批次已结束仅供排查 batch_id)。")
    return 2


# ── DeepSeek 路径：无 Batches API，逐条并发直调 ─────────────
def _main_deepseek(jobs: list[dict], base: dict, api_key: str) -> int:
    """并发跑完所有任务，当场写盘。没有 pending/回收概念(结果同步拿到)。"""
    if not jobs:
        print("全部新鲜，无需刷新。")
        return 0
    from concurrent.futures import ThreadPoolExecutor, as_completed

    print(f"待刷新任务: {len(jobs)} 个 (超过 {REFRESH_DAYS:g} 天的条目)，"
          f"并发 {MAX_WORKERS}，每条最多 {MAX_SEARCHES} 次联网检索…")

    def _one(job: dict):
        usage = llm.Usage()
        try:
            txt, _ = llm.call_text(MODEL, job["prompt"], allow_search=True,
                                   max_tokens=job["max_tokens"], max_searches=MAX_SEARCHES,
                                   schema=job["schema"], api_key=api_key, usage=usage)
            return txt, usage, None
        except Exception as e:                       # 单条失败不拖垮整轮
            return None, usage, f"{type(e).__name__}: {str(e)[:160]}"

    ok = fail = 0
    cost = 0.0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_one, j): j for j in jobs}
        for f in as_completed(futs):
            kind, key, tag = cid_decode(futs[f]["custom_id"])
            txt, usage, err = f.result()
            cost += llm.cost(MODEL, usage)
            d = intel._parse_json(txt) if txt else None
            if err or not d or kind is None:
                print(f"  ❌ {tag}: {err or '解析失败/空回复'}")
                fail += 1
                continue
            if kind == "stock":
                base.setdefault("stocks", {})[key] = intel.build_stock_rec(d)
            else:
                base.setdefault("policies", {})[key] = intel.build_policy_rec(d)
            ok += 1
            print(f"  ✅ {tag}")
    print(f"完成: 成功 {ok} / 失败 {fail} | ≈ ${cost:.3f}(不含 Tavily 检索)")
    if ok:
        _write_base(base)
        return 0
    return 2


def _wait_ended(client, batch_id: str) -> bool:
    waited = 0
    while waited < MAX_WAIT:
        try:
            b = client.messages.batches.retrieve(batch_id)
        except Exception as e:                       # 网络抖动不致命，继续轮询
            print(f"  轮询异常({type(e).__name__})，继续…", flush=True)
            time.sleep(POLL_SECS)
            waited += POLL_SECS
            continue
        if b.processing_status == "ended":
            return True
        time.sleep(POLL_SECS)
        waited += POLL_SECS
        rc = b.request_counts
        print(f"  …{waited//60} 分钟, {b.processing_status} "
              f"(成功{rc.succeeded}/失败{rc.errored}/处理中{rc.processing})", flush=True)
    return False


def _collect(client, batch_id: str, base: dict) -> tuple[int, int]:
    ok = fail = tok_in = tok_out = 0
    for result in client.messages.batches.results(batch_id):
        kind, key, tag = cid_decode(result.custom_id)
        if result.result.type != "succeeded":
            print(f"  ❌ {tag}: {result.result.type}")
            fail += 1
            continue
        msg = result.result.message
        tok_in += msg.usage.input_tokens
        tok_out += msg.usage.output_tokens
        if msg.stop_reason not in ("end_turn",):
            print(f"  ❌ {tag}: stop_reason={msg.stop_reason}(未完成，跳过)")
            fail += 1
            continue
        texts = [blk.text for blk in msg.content
                 if getattr(blk, "type", None) == "text" and getattr(blk, "text", "").strip()]
        d = intel._parse_json(texts[-1]) if texts else None
        if not d or kind is None:
            print(f"  ❌ {tag}: 解析失败")
            fail += 1
            continue
        if kind == "stock":
            base.setdefault("stocks", {})[key] = intel.build_stock_rec(d)
        else:
            base.setdefault("policies", {})[key] = intel.build_policy_rec(d)
        ok += 1
        print(f"  ✅ {tag}")
    pin, pout = intel._PRICE.get(MODEL, (3.0, 15.0))
    cost = (tok_in * pin + tok_out * pout) / 1e6 * 0.5   # Batch 五折
    print(f"回收: 成功 {ok} / 失败 {fail} | tokens {tok_in}+{tok_out} ≈ ${cost:.2f}(五折后,不含检索费)")
    return ok, fail


def _write_base(base: dict):
    os.makedirs(os.path.dirname(BASE), exist_ok=True)
    with open(BASE, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=0)


def _save_pending(batch_id: str):
    os.makedirs(os.path.dirname(PENDING), exist_ok=True)
    with open(PENDING, "w", encoding="utf-8") as f:
        json.dump({"batch_id": batch_id}, f)


def _clear_pending():
    try:
        os.remove(PENDING)
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
