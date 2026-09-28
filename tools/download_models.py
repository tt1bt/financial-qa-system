"""模型下载脚本 —— 串行 + 重试，避免并发写锁冲突

用法：
    python tools/download_models.py                # 下载全部到 ./models
    python tools/download_models.py m3             # 只下 bge-m3
    python tools/download_models.py rerank         # 只下 reranker
    python tools/download_models.py --to D:/hf_cache   # 指定下载目录

说明：
使用 ModelScope 国内源，速度远快于 HuggingFace。
模型默认下载到项目内的 models/ 目录，使项目自包含、便于迁移。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MODELS = {
    "m3": "BAAI/bge-m3",
    "rerank": "BAAI/bge-reranker-v2-m3",
}

# 权重文件候选名（不同模型仓库命名不同）
WEIGHT_CANDIDATES = ["model.safetensors", "pytorch_model.bin"]


def _dir_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1024 / 1024


def download(model_id: str, target_dir: Path, max_retries: int = 5) -> bool:
    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"下载 {model_id}")
    print(f"目标 {target_dir}")
    print(f"{'='*60}")

    try:
        from modelscope import snapshot_download
    except ImportError:
        print("✗ 缺少 modelscope，请先运行: pip install modelscope")
        return False

    for attempt in range(1, max_retries + 1):
        before = _dir_size_mb(target_dir)
        print(f"[尝试 {attempt}/{max_retries}] 当前 {before:.1f} MB")
        try:
            snapshot_download(model_id, local_dir=str(target_dir), max_workers=2)
            after = _dir_size_mb(target_dir)

            has_weights = any(
                (target_dir / name).exists()
                and (target_dir / name).stat().st_size > 100 * 1024 * 1024
                for name in WEIGHT_CANDIDATES
            )
            if has_weights:
                print(f"✓ 完成，共 {after:.1f} MB")
                return True
            print("  ⚠ 权重文件缺失或过小，重试")
        except Exception as e:
            print(f"  ✗ {type(e).__name__}: {str(e)[:120]}")

        time.sleep(3)

    print(f"✗ {model_id} 下载失败")
    print("  提示：ModelScope 偶发网络问题，重跑本脚本即可断点续传")
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description="下载本地模型")
    ap.add_argument("models", nargs="*", choices=list(MODELS.keys()) + [[]],
                    help="要下载的模型，留空则全部下载")
    ap.add_argument("--to", default=None,
                    help="下载目录，默认为项目内 models/")
    args = ap.parse_args()

    keys = args.models or list(MODELS.keys())
    base = Path(args.to) if args.to else ROOT / "models"

    print(f"下载目录: {base}")
    print(f"待下载: {', '.join(MODELS[k] for k in keys)}")

    results = {}
    for k in keys:
        subdir = "bge-m3" if k == "m3" else "bge-reranker-v2-m3"
        results[k] = download(MODELS[k], base / subdir)

    print(f"\n{'='*60}")
    print("下载结果")
    print(f"{'='*60}")
    for k, ok in results.items():
        subdir = "bge-m3" if k == "m3" else "bge-reranker-v2-m3"
        size = _dir_size_mb(base / subdir)
        print(f"  {'✓' if ok else '✗'} {MODELS[k]:32s} {size:8.1f} MB")

    if all(results.values()):
        print("\n全部就绪。下一步：")
        print("  1. 配置 .env（填入 LLM API Key）")
        print("  2. 运行: python -m src.pipeline config   # 检查配置")
        print("  3. 运行: streamlit run app/streamlit_app.py   # 启动界面")
    else:
        print("\n部分模型下载失败，请重跑本脚本（支持断点续传）")
        sys.exit(1)


if __name__ == "__main__":
    main()
