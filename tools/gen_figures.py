"""生成报告图表

基于实验数据生成对比图：
1. 消融实验对比（三种方案的准确率）
2. 检索模式对比（三种模式的 Recall/MRR）
3. 分问题类型对比

用法：python tools/gen_figures.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from src.config import EVAL_DIR  # noqa: E402

OUT_DIR = EVAL_DIR / "figures"

# 中文字体
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# 配色：不使用默认紫白
C_BASE = "#94a3b8"
C_VECTOR = "#f59e0b"
C_HYBRID = "#0ea5e9"
C_GRID = "#e2e8f0"


def fig_ablation() -> None:
    """消融实验对比"""
    path = EVAL_DIR / "ablation.json"
    if not path.exists():
        print("✗ 缺少 ablation.json")
        return
    data = json.loads(path.read_text(encoding="utf-8"))

    labels = ["无 RAG\n（基线）", "纯向量检索", "混合检索\n+Rerank"]
    keys = ["no_rag", "vector_only", "hybrid"]
    colors = [C_BASE, C_VECTOR, C_HYBRID]

    overall = [data[k]["accuracy"] * 100 for k in keys]
    fact = [data[k]["by_type"].get("fact", {}).get("acc", 0) * 100 for k in keys]
    semantic = [data[k]["by_type"].get("semantic", {}).get("acc", 0) * 100 for k in keys]
    refuse = [data[k]["by_type"].get("refuse", {}).get("acc", 0) * 100 for k in keys]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # 左图：总体准确率
    ax = axes[0]
    bars = ax.bar(labels, overall, color=colors, width=0.55, edgecolor="white", linewidth=1.5)
    for b, v in zip(bars, overall):
        ax.text(b.get_x() + b.get_width() / 2, v + 2, f"{v:.0f}%",
                ha="center", fontsize=13, fontweight="bold")
    ax.set_ylabel("准确率 (%)", fontsize=11)
    ax.set_title("消融实验：RAG 组件贡献", fontsize=13, fontweight="bold", pad=15)
    ax.set_ylim(0, 115)
    ax.grid(axis="y", color=C_GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    # 右图：分类型
    ax = axes[1]
    x = np.arange(len(labels))
    w = 0.26
    ax.bar(x - w, fact, w, label="事实型", color="#ef4444", edgecolor="white")
    ax.bar(x, semantic, w, label="语义型", color="#8b5cf6", edgecolor="white")
    ax.bar(x + w, refuse, w, label="拒答型", color="#10b981", edgecolor="white")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("准确率 (%)", fontsize=11)
    ax.set_title("分问题类型表现", fontsize=13, fontweight="bold", pad=15)
    ax.set_ylim(0, 115)
    ax.legend(frameon=False, fontsize=10)
    ax.grid(axis="y", color=C_GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    plt.tight_layout()
    out = OUT_DIR / "ablation.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"✓ {out}")


def fig_retrieval() -> None:
    """检索模式对比"""
    path = EVAL_DIR / "retrieval_comparison.json"
    if not path.exists():
        print("✗ 缺少 retrieval_comparison.json")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = data["summary"]

    labels = ["纯向量", "纯 BM25", "混合检索"]
    keys = ["vector", "bm25", "hybrid"]
    colors = [C_VECTOR, "#a78bfa", C_HYBRID]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # 左图：Recall 指标
    ax = axes[0]
    x = np.arange(len(labels))
    w = 0.26
    r1 = [summary[k]["recall@1"] * 100 for k in keys]
    r3 = [summary[k]["recall@3"] * 100 for k in keys]
    r5 = [summary[k]["recall@5"] * 100 for k in keys]
    ax.bar(x - w, r1, w, label="Recall@1", color="#0369a1", edgecolor="white")
    ax.bar(x, r3, w, label="Recall@3", color="#0ea5e9", edgecolor="white")
    ax.bar(x + w, r5, w, label="Recall@5", color="#7dd3fc", edgecolor="white")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Recall (%)", fontsize=11)
    ax.set_title("检索召回率对比", fontsize=13, fontweight="bold", pad=15)
    ax.set_ylim(0, 115)
    ax.legend(frameon=False, fontsize=10, ncol=3, loc="upper center",
              bbox_to_anchor=(0.5, -0.12))
    ax.grid(axis="y", color=C_GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    # 右图：MRR
    ax = axes[1]
    mrr = [summary[k]["mrr"] for k in keys]
    bars = ax.bar(labels, mrr, color=colors, width=0.55, edgecolor="white", linewidth=1.5)
    for b, v in zip(bars, mrr):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.3f}",
                ha="center", fontsize=13, fontweight="bold")
    ax.set_ylabel("MRR", fontsize=11)
    ax.set_title("平均倒数排名（MRR）", fontsize=13, fontweight="bold", pad=15)
    ax.set_ylim(0, 1.15)
    ax.grid(axis="y", color=C_GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    plt.tight_layout()
    out = OUT_DIR / "retrieval.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"✓ {out}")


def fig_complementarity() -> None:
    """互补性分析：向量 vs BM25 在不同问题类型上的强弱"""
    path = EVAL_DIR / "retrieval_comparison.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = data["summary"]

    types = ["fact", "semantic"]
    type_labels = ["事实型", "语义型"]
    vec = [summary["vector"]["by_type"][t]["recall@1"] * 100 for t in types]
    bm = [summary["bm25"]["by_type"][t]["recall@1"] * 100 for t in types]
    hyb = [summary["hybrid"]["by_type"][t]["recall@1"] * 100 for t in types]

    fig, ax = plt.subplots(figsize=(8.5, 5))
    x = np.arange(len(types))
    w = 0.26
    ax.bar(x - w, vec, w, label="纯向量", color=C_VECTOR, edgecolor="white")
    ax.bar(x, bm, w, label="纯 BM25", color="#a78bfa", edgecolor="white")
    ax.bar(x + w, hyb, w, label="混合检索", color=C_HYBRID, edgecolor="white")

    for i, (v, b, h) in enumerate(zip(vec, bm, hyb)):
        ax.text(i - w, v + 2, f"{v:.0f}", ha="center", fontsize=10)
        ax.text(i, b + 2, f"{b:.0f}", ha="center", fontsize=10)
        ax.text(i + w, h + 2, f"{h:.0f}", ha="center", fontsize=10, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(type_labels, fontsize=12)
    ax.set_ylabel("Recall@1 (%)", fontsize=11)
    ax.set_title("检索方法互补性分析", fontsize=13, fontweight="bold", pad=15)
    ax.set_ylim(0, 120)
    ax.legend(frameon=False, fontsize=10, ncol=3, loc="upper center",
              bbox_to_anchor=(0.5, -0.1))
    ax.grid(axis="y", color=C_GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    plt.tight_layout()
    out = OUT_DIR / "complementarity.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"✓ {out}")


def fig_rerank() -> None:
    """Reranker 作用：区分度提升"""
    fig, ax = plt.subplots(figsize=(8.5, 5))
    items = ["营业收入段落", "净利润段落", "研发费用段落", "环保理念段落"]
    emb = [0.834, 0.618, 0.762, 0.445]
    rer = [0.997, 0.038, 0.308, 0.001]

    x = np.arange(len(items))
    w = 0.35
    ax.bar(x - w / 2, emb, w, label="Embedding 相似度", color=C_VECTOR, edgecolor="white")
    ax.bar(x + w / 2, rer, w, label="Reranker 打分", color=C_HYBRID, edgecolor="white")

    for i, (e, r) in enumerate(zip(emb, rer)):
        ax.text(i - w / 2, e + 0.02, f"{e:.3f}", ha="center", fontsize=9)
        ax.text(i + w / 2, r + 0.02, f"{r:.3f}", ha="center", fontsize=9, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(items, fontsize=10)
    ax.set_ylabel("得分", fontsize=11)
    ax.set_title("Reranker 对同域文档的区分能力（query: 营业收入是多少）",
                 fontsize=12, fontweight="bold", pad=15)
    ax.set_ylim(0, 1.2)
    ax.legend(frameon=False, fontsize=10)
    ax.grid(axis="y", color=C_GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    ax.annotate("区分度 0.216", xy=(0.5, 0.75), xytext=(1.2, 1.05),
                fontsize=10, color="#ef4444",
                arrowprops=dict(arrowstyle="->", color="#ef4444", lw=1.5))
    ax.annotate("区分度 0.959", xy=(1.0, 0.5), xytext=(1.8, 0.85),
                fontsize=10, color="#10b981",
                arrowprops=dict(arrowstyle="->", color="#10b981", lw=1.5))

    plt.tight_layout()
    out = OUT_DIR / "rerank.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"✓ {out}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("生成报告图表...\n")
    fig_ablation()
    fig_retrieval()
    fig_complementarity()
    fig_rerank()
    print(f"\n图表目录: {OUT_DIR}")


if __name__ == "__main__":
    main()
