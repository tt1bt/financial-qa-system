"""检索层实测 —— 三模式对比实验（报告核心数据来源）

对比：纯向量 / 纯关键词 / 混合检索+Rerank
指标：Recall@1/@3/@5、MRR
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import EVAL_DIR  # noqa: E402
from src.retrieval import Retriever  # noqa: E402

# (问题, 期望命中的关键内容, 问题类型)
# 覆盖真实金融问答的三类分布
CASES: list[tuple[str, str | None, str]] = [
    # --- 事实型：精确数字 ---
    ("公司2023年的营业收入是多少？", "1505.60", "fact"),
    ("公司2023年的净利润是多少？", "747.34", "fact"),
    ("公司的研发费用是多少？", "5.79", "fact"),
    ("公司的毛利率是多少？", "91.96", "fact"),
    ("公司的股东总数是多少？", "168947", "fact"),
    ("公司的资产负债率是多少？", "17.42", "fact"),
    ("公司2023年的每股收益是多少？", "59.49", "fact"),
    ("公司的海外收入是多少？", "43.54", "fact"),
    ("公司的直销渠道收入是多少？", "672.33", "fact"),
    ("公司的分红金额是多少？", "387.86", "fact"),
    ("公司的环保投入是多少？", "2.83", "fact"),
    ("公司的员工总数是多少？", "35486", "fact"),
    # --- 语义型：需要理解概念 ---
    ("公司主营业务分哪几个板块？", "茅台酒", "semantic"),
    ("公司面临哪些经营风险？", "风险", "semantic"),
    ("公司的分红政策是怎样的？", "红利", "semantic"),
    ("公司在食品安全方面有什么措施？", "食品安全", "semantic"),
    ("公司的毛利率变动原因是什么？", "毛利率", "semantic"),
    ("公司如何应对原材料价格波动？", "原材料", "semantic"),
    ("公司的渠道改革进展如何？", "直销", "semantic"),
    ("公司的产能情况如何？", "基酒产量", "semantic"),
    ("公司履行了哪些社会责任？", "捐赠", "semantic"),
    ("公司的研发方向有哪些？", "研发", "semantic"),
    # --- 拒答型：不应作答 ---
    ("公司明天的股价会涨吗？", None, "refuse"),
    ("特斯拉2023年的营收是多少？", None, "refuse"),
]


def hit_rank(chunks, expect: str | None) -> int | None:
    """返回期望内容首次出现的位置（1-based）"""
    if expect is None:
        return None
    for i, c in enumerate(chunks, 1):
        if expect in c.text:
            return i
    return None


def run_mode(retriever: Retriever, mode: str, top_k: int = 5) -> list[dict]:
    out = []
    for question, expect, qtype in CASES:
        chunks = retriever.search(question, top_k=top_k, mode=mode)
        out.append({
            "question": question,
            "expect": expect,
            "type": qtype,
            "rank": hit_rank(chunks, expect),
        })
    return out


def summarize(results: list[dict]) -> dict:
    judged = [r for r in results if r["expect"]]
    n = len(judged)
    if not n:
        return {}

    def rate(k: int) -> float:
        return sum(1 for r in judged if r["rank"] and r["rank"] <= k) / n

    mrr = sum(1.0 / r["rank"] for r in judged if r["rank"]) / n

    by_type: dict[str, dict] = {}
    for t in ("fact", "semantic"):
        sub = [r for r in judged if r["type"] == t]
        if sub:
            by_type[t] = {
                "n": len(sub),
                "recall@1": sum(1 for r in sub if r["rank"] == 1) / len(sub),
                "mrr": sum(1.0 / r["rank"] for r in sub if r["rank"]) / len(sub),
            }

    return {"n": n, "recall@1": rate(1), "recall@3": rate(3), "recall@5": rate(5),
            "mrr": mrr, "by_type": by_type}


def main() -> None:
    print("=" * 76)
    print("检索层实测：三模式对比（报告核心实验）")
    print("=" * 76)

    retriever = Retriever().load()
    if not retriever.chunks:
        print("✗ 索引为空，请先运行: python -m src.pipeline build")
        return
    print(f"语料规模: {len(retriever.chunks)} chunks | 测试问题: {len(CASES)} 条\n")

    all_results: dict[str, list[dict]] = {}
    all_summary: dict[str, dict] = {}

    for mode in ("vector", "bm25", "hybrid"):
        results = run_mode(retriever, mode)
        all_results[mode] = results
        s = summarize(results)
        all_summary[mode] = s
        print(f"[{mode}] Recall@1={s['recall@1']:.1%}  Recall@3={s['recall@3']:.1%}  "
              f"Recall@5={s['recall@5']:.1%}  MRR={s['mrr']:.3f}")

    # --- 逐题对比 ---
    print("\n" + "=" * 76)
    print("逐题对比（数字为命中位置，MISS 表示前5未命中）")
    print("=" * 76)
    print(f"{'问题':<32}{'类型':<10}{'向量':>8}{'BM25':>8}{'混合':>8}")
    print("-" * 76)
    for i, (q, expect, qtype) in enumerate(CASES):
        if expect is None:
            continue
        row = []
        for mode in ("vector", "bm25", "hybrid"):
            r = all_results[mode][i]["rank"]
            row.append(f"R{r}" if r else "MISS")
        qd = q[:30] + ".." if len(q) > 32 else q
        print(f"{qd:<32}{qtype:<10}{row[0]:>8}{row[1]:>8}{row[2]:>8}")

    # --- 指标汇总 ---
    print("\n" + "=" * 76)
    print("指标汇总（报告核心数据）")
    print("=" * 76)
    print(f"{'模式':<12}{'Recall@1':>12}{'Recall@3':>12}{'Recall@5':>12}{'MRR':>10}")
    print("-" * 76)
    for mode, s in all_summary.items():
        print(f"{mode:<12}{s['recall@1']:>11.1%}{s['recall@3']:>12.1%}"
              f"{s['recall@5']:>12.1%}{s['mrr']:>10.3f}")

    # --- 分类别看 ---
    print("\n按问题类型:")
    for mode, s in all_summary.items():
        parts = []
        for t, d in s["by_type"].items():
            parts.append(f"{t} R@1={d['recall@1']:.0%} MRR={d['mrr']:.3f}")
        print(f"  {mode:<10} {' | '.join(parts)}")

    # --- 提升幅度 ---
    if "vector" in all_summary and "hybrid" in all_summary:
        v, h = all_summary["vector"], all_summary["hybrid"]
        print("\n" + "=" * 76)
        print("混合检索 vs 纯向量 (Δ)")
        print("=" * 76)
        for key, label in (("recall@1", "Recall@1"), ("recall@3", "Recall@3"),
                           ("recall@5", "Recall@5"), ("mrr", "MRR")):
            d = h[key] - v[key]
            fmt = "{:+.1%}" if "recall" in key else "{:+.3f}"
            print(f"  {label:<12} {v[key]:.3f} → {h[key]:.3f}   {fmt.format(d)}")

    # --- 保存 ---
    out = EVAL_DIR / "retrieval_comparison.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump({
            "corpus_size": len(retriever.chunks),
            "n_questions": len(CASES),
            "summary": all_summary,
            "details": {m: all_results[m] for m in all_results},
        }, f, ensure_ascii=False, indent=2)
    print(f"\n对比数据 → {out}")


if __name__ == "__main__":
    main()
