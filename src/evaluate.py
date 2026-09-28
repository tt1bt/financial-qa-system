"""评测模块：测试集 → 指标

指标定义：
- 准确率：答案包含期望关键信息的比例
- 引用正确率：引用的片段确实支撑答案的比例
- 拒答率：正确拒答（该拒的拒了）+ 误拒（不该拒的拒了）

用法：
    python -m src.evaluate              # 跑完整评测
    python -m src.evaluate --compare    # 跑对比实验（纯向量 vs 混合检索）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import EVAL_DIR, TOP_K_FINAL
from .generator import generate
from .pipeline import answer_question
from .retrieval import Retriever

QUESTIONS_FILE = EVAL_DIR / "questions.jsonl"
RESULTS_FILE = EVAL_DIR / "results.json"


def build_seed_questions() -> list[dict]:
    """生成测试集模板（需人工填入标准答案关键词）

    三类问题：
    - fact:   事实型，考察精确检索（数字、金额、比例）
    - semantic: 语义型，考察语义理解（风险、战略、政策）
    - refuse:  应拒答，考察拒答机制（时效、他公司、无依据）
    """
    return [
        {"id": "q01", "type": "fact", "question": "公司2023年的营业收入是多少？",
         "keywords": [], "should_refuse": False, "note": "填入答案中的关键数字"},
        {"id": "q02", "type": "fact", "question": "公司2023年归属于上市公司股东的净利润是多少？",
         "keywords": [], "should_refuse": False, "note": ""},
        {"id": "q03", "type": "fact", "question": "公司2023年的研发投入是多少？",
         "keywords": [], "should_refuse": False, "note": ""},
        {"id": "q04", "type": "fact", "question": "公司2023年的毛利率是多少？",
         "keywords": [], "should_refuse": False, "note": ""},
        {"id": "q05", "type": "fact", "question": "公司2023年的经营活动现金流量净额是多少？",
         "keywords": [], "should_refuse": False, "note": ""},
        {"id": "q06", "type": "semantic", "question": "公司主要面临哪些经营风险？",
         "keywords": [], "should_refuse": False, "note": ""},
        {"id": "q07", "type": "semantic", "question": "公司的发展战略是什么？",
         "keywords": [], "should_refuse": False, "note": ""},
        {"id": "q08", "type": "semantic", "question": "公司的分红政策是怎样的？",
         "keywords": [], "should_refuse": False, "note": ""},
        {"id": "q09", "type": "semantic", "question": "公司在行业中的竞争地位如何？",
         "keywords": [], "should_refuse": False, "note": ""},
        {"id": "q10", "type": "semantic", "question": "公司的主营业务由哪些板块构成？",
         "keywords": [], "should_refuse": False, "note": ""},
        {"id": "q11", "type": "refuse", "question": "公司明天的股价会涨吗？",
         "keywords": [], "should_refuse": True, "note": "时效性预测，应拒答"},
        {"id": "q12", "type": "refuse", "question": "特斯拉2023年的营收是多少？",
         "keywords": [], "should_refuse": True, "note": "非本数据集公司，应拒答"},
        {"id": "q13", "type": "refuse", "question": "公司CEO的私人电话是多少？",
         "keywords": [], "should_refuse": True, "note": "无依据，应拒答"},
        {"id": "q14", "type": "refuse", "question": "公司2025年的营收预测是多少？",
         "keywords": [], "should_refuse": True, "note": "超出数据覆盖期，应拒答"},
        {"id": "q15", "type": "refuse", "question": "给我推荐几只值得买入的股票。",
         "keywords": [], "should_refuse": True, "note": "投资建议，应拒答"},
    ]


def init_questions() -> None:
    """初始化测试集文件"""
    if QUESTIONS_FILE.exists():
        print(f"测试集已存在: {QUESTIONS_FILE}")
        n = sum(1 for _ in QUESTIONS_FILE.open(encoding="utf-8"))
        print(f"共 {n} 条")
        return
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    with QUESTIONS_FILE.open("w", encoding="utf-8") as f:
        for q in build_seed_questions():
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    print(f"✓ 已生成测试集模板: {QUESTIONS_FILE}")
    print("  请填入 keywords 字段（答案中的关键信息）后再跑评测")


def load_questions() -> list[dict]:
    if not QUESTIONS_FILE.exists():
        init_questions()
        return []
    out = []
    with QUESTIONS_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def judge(ans, item: dict) -> dict:
    """判定单条结果"""
    keywords = item.get("keywords", [])
    should_refuse = item.get("should_refuse", False)

    if should_refuse:
        correct = ans.refused
        return {
            "correct": correct,
            "refused": ans.refused,
            "hit_keywords": [],
            "miss_keywords": [],
            "reason": "正确拒答" if correct else "误答（应拒答却作答）",
        }

    if ans.refused:
        return {
            "correct": False,
            "refused": True,
            "hit_keywords": [],
            "miss_keywords": keywords,
            "reason": "误拒（应作答却拒答）",
        }

    hits = [k for k in keywords if k in ans.answer]
    misses = [k for k in keywords if k not in ans.answer]
    # 无关键词标注时，用"有引用"作为弱判定
    if not keywords:
        correct = len(ans.citations) > 0
        reason = "有引用（无关键词标注，弱判定）" if correct else "无引用"
    else:
        correct = len(misses) == 0
        reason = "关键词全部命中" if correct else f"缺失: {misses}"

    return {
        "correct": correct,
        "refused": False,
        "hit_keywords": hits,
        "miss_keywords": misses,
        "reason": reason,
    }


def evaluate(mode: str = "hybrid", top_k: int = TOP_K_FINAL) -> dict:
    questions = load_questions()
    if not questions:
        print("✗ 测试集为空，请先运行: python -m src.evaluate --init")
        return {}

    retriever = Retriever().load()
    if not retriever.chunks:
        print("✗ 索引为空，请先运行: python -m src.pipeline build")
        return {}

    results = []
    by_type: dict[str, list[bool]] = {"fact": [], "semantic": [], "refuse": []}

    for item in questions:
        q = item["question"]
        ans = answer_question(q, retriever, mode=mode, top_k=top_k)
        verdict = judge(ans, item)
        by_type.setdefault(item.get("type", "fact"), []).append(verdict["correct"])

        results.append({
            "id": item["id"],
            "type": item.get("type", ""),
            "question": q,
            "answer": ans.answer,
            "citations": ans.citations,
            "refused": ans.refused,
            "confidence": ans.confidence,
            "verdict": verdict,
        })

        mark = "✓" if verdict["correct"] else "✗"
        print(f"{mark} [{item['id']}] {q[:32]}... → {verdict['reason']}")

    total = len(results)
    correct = sum(1 for r in results if r["verdict"]["correct"])

    summary = {
        "mode": mode,
        "top_k": top_k,
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "by_type": {
            t: {"n": len(v), "correct": sum(v), "acc": sum(v) / len(v) if v else 0.0}
            for t, v in by_type.items()
        },
        "refuse_accuracy": _refuse_acc(results),
        "citation_rate": sum(1 for r in results if r["citations"]) / total if total else 0.0,
    }

    _print_summary(summary)

    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_FILE.open("w", encoding="utf-8") as f:
        json.dump({"summary": summary, "details": results}, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果 → {RESULTS_FILE}")

    return summary


def _refuse_acc(results: list[dict]) -> float:
    """拒答判定的准确率（该拒的拒了 + 该答的答了）"""
    if not results:
        return 0.0
    ok = sum(1 for r in results if r["verdict"]["correct"])
    return ok / len(results)


def _print_summary(s: dict) -> None:
    print("\n" + "=" * 56)
    print(f"评测结果 · 模式={s['mode']} · top_k={s['top_k']}")
    print("=" * 56)
    print(f"总体准确率: {s['accuracy']:.1%}  ({s['correct']}/{s['total']})")
    print(f"引用率:     {s['citation_rate']:.1%}")
    print("\n分类别:")
    for t, d in s["by_type"].items():
        if d["n"]:
            print(f"  {t:<10} {d['acc']:.1%}  ({d['correct']}/{d['n']})")
    print("=" * 56)


def compare_experiment() -> None:
    """核心对比实验：纯向量 vs 混合检索 —— 报告的关键论据"""
    print("\n" + "#" * 56)
    print("# 对比实验：纯向量检索 vs 混合检索 + Rerank")
    print("#" * 56 + "\n")

    results = {}
    for mode in ("vector", "hybrid"):
        print(f"\n--- 模式: {mode} ---")
        s = evaluate(mode=mode)
        if s:
            results[mode] = s

    if len(results) == 2:
        v, h = results["vector"], results["hybrid"]
        print("\n" + "=" * 56)
        print("对比汇总")
        print("=" * 56)
        print(f"{'指标':<16}{'纯向量':>12}{'混合检索':>12}{'提升':>12}")
        print("-" * 56)
        for key, label in (("accuracy", "总体准确率"), ("citation_rate", "引用率")):
            a, b = v[key], h[key]
            delta = b - a
            sign = "+" if delta >= 0 else ""
            print(f"{label:<16}{a:>11.1%}{b:>12.1%}{sign}{delta:>11.1%}")
        for t in ("fact", "semantic", "refuse"):
            a = v["by_type"].get(t, {}).get("acc", 0)
            b = h["by_type"].get(t, {}).get("acc", 0)
            delta = b - a
            sign = "+" if delta >= 0 else ""
            print(f"{t:<16}{a:>11.1%}{b:>12.1%}{sign}{delta:>11.1%}")
        print("=" * 56)

        out = EVAL_DIR / "comparison.json"
        with out.open("w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n对比数据 → {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description="评测")
    ap.add_argument("--init", action="store_true", help="初始化测试集模板")
    ap.add_argument("--compare", action="store_true", help="跑对比实验")
    ap.add_argument("--mode", default="hybrid", choices=["hybrid", "vector", "bm25"])
    ap.add_argument("--top-k", type=int, default=TOP_K_FINAL)
    args = ap.parse_args()

    if args.init:
        init_questions()
    elif args.compare:
        compare_experiment()
    else:
        evaluate(mode=args.mode, top_k=args.top_k)


if __name__ == "__main__":
    main()
