"""消融实验：验证 RAG 各组件的贡献

对比方案：
1. no_rag       —— 不用检索，直接问 LLM（基线，暴露幻觉）
2. vector_only  —— 纯向量检索
3. hybrid       —— 混合检索 + Rerank（完整方案）

评价维度：
- 准确率：答案是否包含期望关键信息
- 拒答准确率：该拒的是否拒了
- 幻觉率：无检索时是否编造数据

用法：python -m src.ablation
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import EVAL_DIR  # noqa: E402
from src.evaluate import judge, load_questions  # noqa: E402
from src.generator import generate  # noqa: E402
from src.retrieval import Retriever  # noqa: E402
from src.schema import Answer, Chunk  # noqa: E402

OUT_FILE = EVAL_DIR / "ablation.json"


def no_rag_answer(question: str) -> Answer:
    """基线：不提供任何参考资料，直接问 LLM

    这是验证 RAG 价值的关键对照组——如果 LLM 靠先验知识
    就能答对，说明 RAG 没必要；如果它编造数据，说明 RAG 必需。
    """
    from src.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
    from openai import OpenAI

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": "你是一名金融分析师，请简洁回答问题。"},
            {"role": "user", "content": question},
        ],
        temperature=0.0,
        max_tokens=300,
    )
    text = resp.choices[0].message.content or ""
    return Answer(answer=text, citations=[], confidence=0.0, refused=False, contexts=[])


def run_condition(name: str, questions: list[dict], retriever: Retriever | None,
                  mode: str | None) -> dict:
    """跑一个实验条件"""
    results = []
    for item in questions:
        q = item["question"]
        if name == "no_rag":
            ans = no_rag_answer(q)
        else:
            chunks = retriever.search(q, top_k=5, mode=mode)
            ans = generate(q, chunks)

        verdict = judge(ans, item)
        results.append({
            "id": item["id"],
            "type": item.get("type", ""),
            "question": q,
            "answer": ans.answer[:200],
            "citations": ans.citations,
            "refused": ans.refused,
            "correct": verdict["correct"],
            "reason": verdict["reason"],
        })

    n = len(results)
    by_type = {}
    for t in ("fact", "semantic", "refuse"):
        sub = [r for r in results if r["type"] == t]
        if sub:
            by_type[t] = {
                "n": len(sub),
                "correct": sum(1 for r in sub if r["correct"]),
                "acc": sum(1 for r in sub if r["correct"]) / len(sub),
            }

    return {
        "condition": name,
        "n": n,
        "correct": sum(1 for r in results if r["correct"]),
        "accuracy": sum(1 for r in results if r["correct"]) / n,
        "citation_rate": sum(1 for r in results if r["citations"]) / n,
        "by_type": by_type,
        "details": results,
    }


def main() -> None:
    questions = load_questions()
    if not questions:
        print("✗ 评测集为空，请先运行: python -m src.evaluate --init && python tools/fill_eval.py")
        return

    print("=" * 76)
    print("消融实验：RAG 各组件的贡献")
    print("=" * 76)
    print(f"测试集: {len(questions)} 条问题\n")

    retriever = Retriever().load()
    conditions = [
        ("no_rag", None, None),
        ("vector_only", retriever, "vector"),
        ("hybrid", retriever, "hybrid"),
    ]

    all_results = {}
    for name, ret, mode in conditions:
        print(f"\n{'─'*76}")
        print(f"条件: {name}")
        print(f"{'─'*76}")
        t0 = time.time()
        res = run_condition(name, questions, ret, mode)
        res["elapsed_sec"] = round(time.time() - t0, 1)
        all_results[name] = res
        print(f"  准确率 {res['accuracy']:.1%} ({res['correct']}/{res['n']})  "
              f"耗时 {res['elapsed_sec']}s")

    # --- 汇总表 ---
    print("\n" + "=" * 76)
    print("汇总对比（报告核心数据）")
    print("=" * 76)
    print(f"{'方案':<16}{'总体准确率':>14}{'事实型':>12}{'语义型':>12}{'拒答型':>12}")
    print("-" * 76)
    for name, r in all_results.items():
        bt = r["by_type"]
        label = {"no_rag": "无 RAG（基线）", "vector_only": "纯向量检索",
                 "hybrid": "混合检索+Rerank"}[name]
        print(f"{label:<16}{r['accuracy']:>13.1%}"
              f"{bt.get('fact', {}).get('acc', 0):>12.1%}"
              f"{bt.get('semantic', {}).get('acc', 0):>12.1%}"
              f"{bt.get('refuse', {}).get('acc', 0):>12.1%}")

    # --- 提升幅度 ---
    print("\n" + "=" * 76)
    print("RAG 贡献分析")
    print("=" * 76)
    base = all_results["no_rag"]["accuracy"]
    vec = all_results["vector_only"]["accuracy"]
    hyb = all_results["hybrid"]["accuracy"]
    print(f"  RAG（混合检索）相比无检索基线: {base:.1%} → {hyb:.1%}  ({(hyb-base)*100:+.1f}pp)")
    print(f"  混合检索相比纯向量:            {vec:.1%} → {hyb:.1%}  ({(hyb-vec)*100:+.1f}pp)")

    # 展示无 RAG 的错误案例（幻觉证据）
    print("\n【无 RAG 基线的典型错误（幻觉证据）】")
    shown = 0
    for r in all_results["no_rag"]["details"]:
        if not r["correct"] and shown < 5:
            print(f"  ✗ {r['question'][:30]}")
            print(f"    回答: {r['answer'][:100]}")
            print(f"    判定: {r['reason']}")
            shown += 1

    with OUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n实验数据 → {OUT_FILE}")


if __name__ == "__main__":
    main()
