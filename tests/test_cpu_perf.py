"""CPU 推理性能实测

对比 GPU 与 CPU 下的：
- 模型加载时间
- 单条查询编码耗时
- Reranker 打分耗时
- 内存/显存占用

用法：python tests/test_cpu_perf.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 强制使用 CPU，必须在 import torch 前设置
os.environ["CUDA_VISIBLE_DEVICES"] = ""

import torch  # noqa: E402

M3_PATH = r"D:\hf_cache\bge-m3"
RERANK_PATH = r"D:\hf_cache\bge-reranker-v2-m3"

QUERIES = [
    "公司2023年的营业收入是多少？",
    "公司面临哪些经营风险？",
    "公司的研发投入情况如何？",
    "公司的分红政策是怎样的？",
    "公司的毛利率是多少？",
]

PASSAGES = [
    "公司2023年实现营业收入1505.60亿元，同比增长18.04%。",
    "公司积极践行绿色发展理念，推进节能减排工作。",
    "公司2023年研发费用为5.79亿元，同比增长10.28%。",
    "归属于上市公司股东的净利润为747.34亿元。",
]


def mem_mb() -> float:
    """当前进程内存占用（MB）"""
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1024 / 1024
    except ImportError:
        # 无 psutil 时用 Windows 原生命令
        import subprocess
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {os.getpid()}", "/FO", "CSV", "/NH"],
            text=True, errors="ignore",
        )
        parts = out.split('","')
        if len(parts) > 4:
            return int(parts[4].replace('"', "").replace(",", "")) / 1024
        return 0.0


def bench_embedding(device: str) -> dict:
    print(f"\n{'='*64}")
    print(f"Embedding 测试 (device={device})")
    print(f"{'='*64}")

    from sentence_transformers import SentenceTransformer

    t0 = time.time()
    model = SentenceTransformer(M3_PATH, device=device)
    load_time = time.time() - t0

    # 断言确实在 CPU 上运行
    actual = str(next(model.parameters()).device)
    print(f"  模型加载: {load_time:.1f}s   内存: {mem_mb():.0f} MB")
    print(f"  实际设备: {actual}")
    assert "cpu" in actual, f"未在 CPU 上运行，实际设备: {actual}"

    # 预热（首次推理含懒初始化）
    model.encode(["预热"], show_progress_bar=False)

    t0 = time.time()
    model.encode(QUERIES, show_progress_bar=False, normalize_embeddings=True)
    encode_time = time.time() - t0
    print(f"  批量编码 {len(QUERIES)} 条: {encode_time:.2f}s "
          f"({encode_time/len(QUERIES)*1000:.0f} ms/条)")

    # 单条编码（模拟真实单次查询）
    times = []
    for q in QUERIES:
        t0 = time.time()
        model.encode([q], show_progress_bar=False, normalize_embeddings=True)
        times.append(time.time() - t0)
    single = sum(times) / len(times)
    print(f"  单条编码: {single*1000:.0f} ms/条")
    print(f"  进程内存: {mem_mb():.0f} MB")

    del model
    return {"load": load_time, "single": single, "mem": mem_mb()}


def bench_reranker(device: str) -> dict:
    print(f"\n{'='*64}")
    print(f"Reranker 测试 (device={device})")
    print(f"{'='*64}")

    from sentence_transformers import CrossEncoder

    t0 = time.time()
    model = CrossEncoder(RERANK_PATH, device=device, max_length=512)
    load_time = time.time() - t0
    try:
        actual = str(next(model.model.parameters()).device)
    except (AttributeError, StopIteration):
        actual = "unknown"
    print(f"  模型加载: {load_time:.1f}s   内存: {mem_mb():.0f} MB")
    print(f"  实际设备: {actual}")

    query = QUERIES[0]
    pairs = [(query, p) for p in PASSAGES]

    # 预热
    model.predict(pairs[:1], show_progress_bar=False)

    t0 = time.time()
    model.predict(pairs, batch_size=4, show_progress_bar=False)
    rerank_time = time.time() - t0
    print(f"  打分 {len(pairs)} 个候选: {rerank_time:.2f}s "
          f"({rerank_time/len(pairs)*1000:.0f} ms/条)")

    # 模拟 20 个候选（真实 recall 数）
    many = [(query, p) for p in PASSAGES * 5]
    t0 = time.time()
    model.predict(many, batch_size=4, show_progress_bar=False)
    t20 = time.time() - t0
    print(f"  打分 20 个候选: {t20:.2f}s  ← 真实检索场景")

    del model
    return {"load": load_time, "t20": t20, "mem": mem_mb()}


def main() -> None:
    print("=" * 64)
    print("CPU 推理性能实测")
    print("=" * 64)
    print(f"CUDA 可用: {torch.cuda.is_available()}")
    print(f"CPU 核心数: {os.cpu_count()}")
    print(f"torch 线程数: {torch.get_num_threads()}")
    print("注：模型显式指定 device='cpu'，不受 CUDA 可用性影响")

    results = {}
    for device in ["cpu"]:
        results[device] = {
            "embed": bench_embedding(device),
            "rerank": bench_reranker(device),
        }

    print("\n" + "=" * 64)
    print("汇总")
    print("=" * 64)
    for dev, r in results.items():
        e, k = r["embed"], r["rerank"]
        print(f"\n[{dev}]")
        print(f"  Embedding 加载:      {e['load']:5.1f}s")
        print(f"  单条查询编码:        {e['single']*1000:5.0f} ms")
        print(f"  Reranker 加载:       {k['load']:5.1f}s")
        print(f"  Reranker 20候选打分: {k['t20']:5.2f}s")
        total = e["single"] + k["t20"]
        print(f"  ─────────────────────────────")
        print(f"  单次问答检索耗时:    {total:5.2f}s  (不含 LLM)")
        print(f"  进程内存峰值:        {e['mem']:5.0f} MB")


if __name__ == "__main__":
    main()
