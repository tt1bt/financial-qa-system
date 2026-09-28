"""金融问答系统 - 全局配置

配置优先级（从高到低）：
1. 环境变量
2. 项目根目录下的 .env 文件
3. 代码中的默认值

模型路径的查找顺序：
1. 环境变量 EMBEDDING_MODEL_PATH / RERANKER_MODEL_PATH
2. 项目根目录下的 models/<name>（推荐，clone 后自包含）
3. 常见的全局缓存目录（~/.cache/huggingface 等）
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# --- 项目根目录 ---
ROOT_DIR = Path(__file__).resolve().parent.parent

load_dotenv(ROOT_DIR / ".env")

# --- 路径配置 ---
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
EVAL_DIR = DATA_DIR / "eval"
INDEX_DIR = ROOT_DIR / "index"
MODELS_DIR = ROOT_DIR / "models"

CHUNKS_FILE = DATA_DIR / "chunks.jsonl"
CHROMA_DIR = INDEX_DIR / "chroma"
BM25_FILE = INDEX_DIR / "bm25.pkl"

for _d in (RAW_DIR, EVAL_DIR, INDEX_DIR, CHROMA_DIR, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _resolve_model_path(env_var: str, default_name: str) -> str:
    """按优先级查找模型路径，找不到时返回项目内默认位置（提示用户下载）"""
    # 1. 环境变量
    if val := os.getenv(env_var):
        return val

    # 2. 项目内 models/ 目录（推荐方式，clone 后自包含）
    local = MODELS_DIR / default_name
    if local.exists() and any(local.iterdir()):
        return str(local)

    # 3. 常见全局缓存位置
    candidates = [
        Path.home() / ".cache" / "huggingface" / default_name,
        Path("D:/hf_cache") / default_name,
        Path("C:/hf_cache") / default_name,
    ]
    for c in candidates:
        if c.exists() and any(c.iterdir()):
            return str(c)

    # 4. 兜底：返回项目内路径，由用户在运行时报错中看到提示
    return str(local)


EMBEDDING_MODEL_PATH = _resolve_model_path("EMBEDDING_MODEL_PATH", "bge-m3")
RERANKER_MODEL_PATH = _resolve_model_path("RERANKER_MODEL_PATH", "bge-reranker-v2-m3")

# --- LLM API（任意 OpenAI 兼容端点）---
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

# --- 检索参数 ---
TOP_K_RECALL = int(os.getenv("TOP_K_RECALL", "20"))
TOP_K_FINAL = int(os.getenv("TOP_K_FINAL", "5"))
ENABLE_RERANK = os.getenv("ENABLE_RERANK", "1") == "1"

# --- 分块参数 ---
CHUNK_SIZE = 500
CHUNK_OVERLAP = 80
MIN_CHUNK_SIZE = 80

# --- 向量库 ---
COLLECTION_NAME = "finance_qa"

# --- 设备 ---
import torch  # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


# --- 配置校验 ---

class ConfigError(RuntimeError):
    """配置缺失或无效"""


def check_config(require_api: bool = True) -> list[str]:
    """检查配置完整性，返回问题列表（空列表表示全部正常）

    Args:
        require_api: 是否要求 LLM API 已配置（仅做检索时不需要）
    """
    problems: list[str] = []

    # 模型检查
    emb = Path(EMBEDDING_MODEL_PATH)
    if not emb.exists() or not any(emb.iterdir()):
        problems.append(
            f"嵌入模型未找到: {EMBEDDING_MODEL_PATH}\n"
            f"    解决: python tools/download_models.py m3"
        )

    if ENABLE_RERANK:
        rer = Path(RERANKER_MODEL_PATH)
        if not rer.exists() or not any(rer.iterdir()):
            problems.append(
                f"重排模型未找到: {RERANKER_MODEL_PATH}\n"
                f"    解决: python tools/download_models.py rerank\n"
                f"    或设置 ENABLE_RERANK=0 跳过重排"
            )

    # API 检查
    if require_api:
        if not LLM_API_KEY:
            problems.append(
                "LLM_API_KEY 未配置\n"
                "    解决: 复制 .env.example 为 .env 并填入你的 API Key"
            )
        if not LLM_BASE_URL:
            problems.append("LLM_BASE_URL 未配置")

    return problems


def print_config() -> None:
    """打印当前生效配置（用于排查问题）"""
    print("=" * 60)
    print("当前配置")
    print("=" * 60)
    print(f"项目根目录 : {ROOT_DIR}")
    print(f"运行设备   : {DEVICE}")
    print(f"嵌入模型   : {EMBEDDING_MODEL_PATH}")
    print(f"重排模型   : {RERANKER_MODEL_PATH}  (启用: {ENABLE_RERANK})")
    print(f"LLM 端点   : {LLM_BASE_URL}")
    print(f"LLM 模型   : {LLM_MODEL}")
    print(f"API Key    : {'已配置' if LLM_API_KEY else '未配置'}")
    print(f"检索参数   : recall={TOP_K_RECALL}, final={TOP_K_FINAL}")

    problems = check_config(require_api=False)
    if problems:
        print("\n发现以下问题:")
        for p in problems:
            print(f"  - {p}")
    print("=" * 60)
