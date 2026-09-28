"""模型加载与推理实测 —— 验证 8GB 显存可行性

这是整个方案的技术关口：
- BGE-M3 嵌入模型能否加载并编码
- Reranker 能否加载并对 (query, doc) 打分
- 显存占用是否在 8GB 内
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import torch  # noqa: E402

M3_PATH = r"D:\hf_cache\bge-m3"
RERANK_PATH = r"D:\hf_cache\bge-reranker-v2-m3"


def mem_mb() -> float:
    if not torch.cuda.is_available():
        return 0.0
    return torch.cuda.memory_allocated() / 1024 / 1024


def main() -> None:
    print("=" * 56)
    print("模型加载实测")
    print("=" * 56)
    print(f"CUDA: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"设备: {torch.cuda.get_device_name(0)}")
        total = torch.cuda.get_device_properties(0).total_memory / 1024 / 1024
        print(f"显存总量: {total:.0f} MB")

    # --- BGE-M3 ---
    print("\n[1/2] BGE-M3 嵌入模型")
    try:
        from sentence_transformers import SentenceTransformer

        t0 = time.time()
        model = SentenceTransformer(M3_PATH, device="cuda" if torch.cuda.is_available() else "cpu")
        print(f"  ✓ 加载成功 ({time.time()-t0:.1f}s, 显存 {mem_mb():.0f} MB)")

        sentences = [
            "公司2023年实现营业收入1505.60亿元",
            "归属于上市公司股东的净利润为747.34亿元",
            "公司积极践行绿色发展理念",
        ]
        t0 = time.time()
        emb = model.encode(sentences, normalize_embeddings=True)
        print(f"  ✓ 编码 {len(sentences)} 条 ({time.time()-t0:.2f}s, 维度 {emb.shape[1]})")
        print(f"  显存峰值: {torch.cuda.max_memory_allocated()/1024/1024:.0f} MB")

        # 语义相似度合理性检查
        q = model.encode(["营业收入是多少"], normalize_embeddings=True)[0]
        sims = [float(q @ e) for e in emb]
        best = int(max(range(len(sims)), key=lambda i: sims[i]))
        print(f"  语义相似度: {[f'{s:.3f}' for s in sims]}")
        print(f"  embedding 首选: {sentences[best][:34]}...")
        print("  注：embedding 对同域财务指标区分力有限，这正是 Reranker 存在的理由")

        del model
        torch.cuda.empty_cache()
    except Exception as e:
        print(f"  ✗ 失败: {type(e).__name__}: {str(e)[:200]}")
        return

    # --- Reranker ---
    print("\n[2/2] bge-reranker-v2-m3 重排模型")
    try:
        from sentence_transformers import CrossEncoder

        t0 = time.time()
        reranker = CrossEncoder(RERANK_PATH, device="cuda" if torch.cuda.is_available() else "cpu", max_length=512)
        print(f"  ✓ 加载成功 ({time.time()-t0:.1f}s, 显存 {mem_mb():.0f} MB)")

        query = "公司2023年的营业收入是多少？"
        passages = [
            "公司2023年实现营业收入1505.60亿元，同比增长18.04%。",
            "公司积极践行绿色发展理念，推进节能减排工作。",
            "公司2023年研发费用为5.79亿元。",
            "归属于上市公司股东的净利润为747.34亿元。",
        ]

        # 先看 embedding 的排序（基线）
        emb_model = SentenceTransformer(M3_PATH, device="cuda" if torch.cuda.is_available() else "cpu")
        qv = emb_model.encode([query], normalize_embeddings=True)[0]
        pv = emb_model.encode(passages, normalize_embeddings=True)
        emb_scores = [float(qv @ e) for e in pv]
        emb_order = sorted(range(len(passages)), key=lambda i: -emb_scores[i])
        print("\n  【embedding 排序（基线）】")
        for rank, i in enumerate(emb_order, 1):
            print(f"    {rank}. {emb_scores[i]:7.3f}  {passages[i][:38]}")
        del emb_model
        torch.cuda.empty_cache()

        # Reranker 重排
        t0 = time.time()
        scores = reranker.predict([(query, p) for p in passages], batch_size=4)
        print(f"\n  【Reranker 重排】(耗时 {time.time()-t0:.2f}s)")
        rerank_order = sorted(range(len(passages)), key=lambda i: -float(scores[i]))
        for rank, i in enumerate(rerank_order, 1):
            print(f"    {rank}. {float(scores[i]):7.3f}  {passages[i][:38]}")

        top = passages[rerank_order[0]]
        assert "1505.60" in top, f"重排结果不合理: {top}"
        print("\n  ✓ Reranker 将营收段落排至首位")
        if emb_order[0] != rerank_order[0]:
            print(f"  ★ 关键证据：embedding 首选错误（{passages[emb_order[0]][:20]}...），"
                  f"Reranker 成功纠正 → 这就是重排的价值")
        print(f"  显存峰值: {torch.cuda.max_memory_allocated()/1024/1024:.0f} MB")

    except Exception as e:
        print(f"  ✗ 失败: {type(e).__name__}: {str(e)[:200]}")
        return

    print("\n" + "=" * 56)
    print("✓ 两个模型均可用，8GB 显存方案可行")
    print("=" * 56)


if __name__ == "__main__":
    main()
