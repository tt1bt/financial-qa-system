"""一键安装脚本 —— 让项目开箱即用

一条命令完成：
  1. 检查 Python 环境与依赖
  2. 安装缺失的依赖包
  3. 下载模型（BGE-M3 + Reranker，约 4.3GB）
  4. 生成 .env 配置文件
  5. 校验整体配置

用法：
    python setup.py                # 完整安装
    python setup.py --skip-deps    # 跳过依赖安装
    python setup.py --skip-models  # 跳过模型下载
    python setup.py --check        # 只做环境检查，不安装任何东西
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS_DIR = ROOT / "models"

# 依赖包：(import 名, pip 包名, 最低版本说明)
REQUIRED_PACKAGES = [
    ("torch", "torch", "深度学习框架"),
    ("transformers", "transformers", "模型加载"),
    ("sentence_transformers", "sentence-transformers", "嵌入与重排模型"),
    ("chromadb", "chromadb", "向量数据库"),
    ("rank_bm25", "rank_bm25", "BM25 关键词检索"),
    ("jieba", "jieba", "中文分词"),
    ("openai", "openai", "LLM API 客户端"),
    ("streamlit", "streamlit", "Web 界面"),
    ("dotenv", "python-dotenv", "环境变量加载"),
]

MODEL_SPECS = {
    "bge-m3": ("BAAI/bge-m3", "嵌入模型", "约 2.1GB"),
    "bge-reranker-v2-m3": ("BAAI/bge-reranker-v2-m3", "重排模型", "约 2.2GB"),
}

WEIGHT_CANDIDATES = ["model.safetensors", "pytorch_model.bin"]

# 终端颜色（Windows 10+ 支持 ANSI）
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"

    @classmethod
    def disable(cls):
        for attr in ("RESET", "BOLD", "GREEN", "YELLOW", "RED", "CYAN", "GRAY"):
            setattr(cls, attr, "")


if platform.system() == "Windows" and not os.environ.get("WT_SESSION"):
    # 老版本 Windows 控制台可能不支持 ANSI，尝试启用
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        C.disable()


def banner(text: str) -> None:
    print(f"\n{C.BOLD}{C.CYAN}{'='*60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  {text}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'='*60}{C.RESET}")


def step(n: int, total: int, text: str) -> None:
    print(f"\n{C.BOLD}[{n}/{total}] {text}{C.RESET}")


def ok(text: str) -> None:
    print(f"  {C.GREEN}✓{C.RESET} {text}")


def warn(text: str) -> None:
    print(f"  {C.YELLOW}!{C.RESET} {text}")


def fail(text: str) -> None:
    print(f"  {C.RED}✗{C.RESET} {text}")


def info(text: str) -> None:
    print(f"  {C.GRAY}{text}{C.RESET}")


# --- 步骤 1：环境检查 ---

def check_python() -> bool:
    v = sys.version_info
    if v < (3, 10):
        fail(f"Python 版本过低: {v.major}.{v.minor}，需要 3.10+")
        return False
    ok(f"Python {v.major}.{v.minor}.{v.micro}")
    return True


def check_disk() -> bool:
    """检查磁盘空间（模型约 4.3GB，需要预留 6GB）"""
    try:
        usage = shutil.disk_usage(ROOT)
        free_gb = usage.free / 1024**3
        if free_gb < 6:
            warn(f"剩余磁盘空间 {free_gb:.1f}GB，建议至少 6GB（模型约 4.3GB）")
            return False
        ok(f"磁盘空间充足（剩余 {free_gb:.1f}GB）")
        return True
    except Exception:
        info("磁盘空间检查跳过")
        return True


def check_gpu() -> None:
    """报告 GPU 情况（非必需，仅影响速度）"""
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            mem = torch.cuda.get_device_properties(0).total_memory / 1024**3
            ok(f"GPU 可用: {name} ({mem:.1f}GB)")
            if mem < 5:
                warn("显存偏小，建议在 .env 中设置 ENABLE_RERANK=0")
        else:
            warn("未检测到 GPU，将使用 CPU 运行（较慢，但功能完整）")
            info("CPU 模式单次检索约需 2-3 秒；可在 .env 设 ENABLE_RERANK=0 加速")
    except ImportError:
        info("torch 未安装，跳过 GPU 检查")


def check_env_code() -> bool:
    """检查配置文件状态"""
    if (ROOT / ".env").exists():
        ok(".env 已存在")
        content = (ROOT / ".env").read_text(encoding="utf-8", errors="ignore")
        if "sk-在此填入你的Key" in content or "your-key" in content.lower():
            warn(".env 中的 API Key 仍是占位符，需要填入真实 Key")
        return True
    else:
        warn(".env 不存在，稍后将自动创建")
        return False


def _find_model_dir(name: str) -> Path | None:
    """按与 src/config.py 一致的优先级查找模型目录

    顺序：环境变量 → 项目内 models/ → 常见全局缓存目录
    这样用户把模型放在任何一处都能被识别，不会误报"未下载"。
    """
    import re

    env_var = {
        "bge-m3": "EMBEDDING_MODEL_PATH",
        "bge-reranker-v2-m3": "RERANKER_MODEL_PATH",
    }.get(name)
    if env_var:
        val = os.environ.get(env_var)
        if val and Path(val).exists():
            return Path(val)

    # 读 .env 中的显式配置
    env_file = ROOT / ".env"
    if env_file.exists() and env_var:
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = re.match(rf"^\s*{env_var}\s*=\s*(.+?)\s*$", line)
            if m and m.group(1) and not m.group(1).startswith("#"):
                p = Path(m.group(1).strip().strip('"').strip("'"))
                if p.exists():
                    return p

    candidates = [
        MODELS_DIR / name,
        Path.home() / ".cache" / "huggingface" / name,
        Path("D:/hf_cache") / name,
        Path("C:/hf_cache") / name,
    ]
    for c in candidates:
        if c.exists() and any(c.iterdir()):
            return c
    return None


def check_models() -> dict[str, tuple[bool, Path | None]]:
    """检查模型是否已下载，返回 {name: (是否就绪, 所在路径)}"""
    status = {}
    for name in MODEL_SPECS:
        path = _find_model_dir(name)
        has_weights = False
        if path:
            has_weights = any(
                (path / f).exists() and (path / f).stat().st_size > 100 * 1024 * 1024
                for f in WEIGHT_CANDIDATES
            )
        status[name] = (has_weights, path if has_weights else None)
    return status


def check_index() -> None:
    """检查索引是否就绪"""
    chroma = ROOT / "index" / "chroma" / "chroma.sqlite3"
    bm25 = ROOT / "index" / "bm25.pkl"
    chunks = ROOT / "data" / "chunks.jsonl"

    if chroma.exists() and bm25.exists():
        size_kb = chroma.stat().st_size / 1024
        ok(f"检索索引已就绪（{size_kb:.0f} KB）")
    else:
        warn("索引不存在，需要运行: python -m src.pipeline build")

    if chunks.exists():
        n = sum(1 for _ in chunks.open(encoding="utf-8"))
        ok(f"语料分块已就绪（{n} 个片段）")
    else:
        warn("未找到 data/chunks.jsonl，需要先准备语料")


# --- 步骤 2：依赖安装 ---

def get_missing_packages() -> list[tuple[str, str, str]]:
    missing = []
    for import_name, pip_name, desc in REQUIRED_PACKAGES:
        try:
            __import__(import_name)
        except ImportError:
            missing.append((import_name, pip_name, desc))
    return missing


def install_deps(missing: list[tuple[str, str, str]]) -> bool:
    if not missing:
        ok("所有依赖已安装")
        return True

    names = [m[1] for m in missing]
    print(f"  缺失 {len(missing)} 个依赖:")
    for _, pip_name, desc in missing:
        print(f"    - {pip_name}  ({desc})")

    use_mirror = "y" in input(
        f"\n  {C.BOLD}是否使用清华镜像加速安装？[Y/n]{C.RESET} "
    ).strip().lower() or True

    cmd = [sys.executable, "-m", "pip", "install", "--user"]
    if use_mirror:
        cmd += ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]
    cmd += names

    print(f"\n  执行: {' '.join(cmd[3:])}\n")
    try:
        subprocess.check_call(cmd)
        ok("依赖安装完成")
        return True
    except subprocess.CalledProcessError:
        fail("依赖安装失败，请手动执行:")
        print(f"    pip install {' '.join(names)}")
        return False


# --- 步骤 3：模型下载 ---

def download_model(name: str, model_id: str, desc: str, size: str) -> bool:
    target = MODELS_DIR / name
    print(f"\n  {C.BOLD}{desc}: {model_id}{C.RESET}")
    print(f"  目标: {target}  ({size})")

    try:
        from modelscope import snapshot_download
    except ImportError:
        fail("缺少 modelscope，请先运行: pip install modelscope")
        return False

    for attempt in range(1, 4):
        try:
            snapshot_download(model_id, local_dir=str(target), max_workers=2)
            has_weights = any(
                (target / f).exists() and (target / f).stat().st_size > 100 * 1024 * 1024
                for f in WEIGHT_CANDIDATES
            )
            if has_weights:
                ok(f"{desc} 下载完成")
                return True
            warn(f"权重文件不完整，重试 ({attempt}/3)")
        except Exception as e:
            warn(f"下载出错: {type(e).__name__} ({attempt}/3)")
        time.sleep(2)

    fail(f"{desc} 下载失败，请重试本脚本（支持断点续传）")
    return False


def handle_models(skip: bool) -> bool:
    status = check_models()

    if all(ready for ready, _ in status.values()):
        for name, (ready, path) in status.items():
            _, desc, _ = MODEL_SPECS[name]
            ok(f"{desc} 已就绪  ({path})")
        return True

    for name, (ready, path) in status.items():
        if ready:
            model_id, desc, _ = MODEL_SPECS[name]
            ok(f"{desc} 已存在，跳过  ({path})")

    todo = [n for n, (r, _) in status.items() if not r]
    if skip:
        warn(f"跳过了 {len(todo)} 个模型的下载")
        return False

    print(f"\n  需要下载 {len(todo)} 个模型，共约 4.3GB")
    info("使用 ModelScope 国内源，通常 5-15 分钟")
    info("下载失败可直接重跑，支持断点续传")

    answer = input(f"\n  {C.BOLD}现在下载？[Y/n]{C.RESET} ").strip().lower()
    if answer and answer not in ("y", "yes"):
        warn("已跳过模型下载")
        return False

    all_ok = True
    for name in todo:
        model_id, desc, size = MODEL_SPECS[name]
        if not download_model(name, model_id, desc, size):
            all_ok = False
    return all_ok


# --- 步骤 4：生成 .env ---

def create_env() -> None:
    env_path = ROOT / ".env"
    example = ROOT / ".env.example"

    if env_path.exists():
        ok(".env 已存在，保留现有配置")
        return

    if not example.exists():
        fail(".env.example 缺失")
        return

    content = example.read_text(encoding="utf-8")
    # 显式指定 UTF-8 写入：Windows 默认编码为 GBK，会导致中文注释乱码
    env_path.write_text(content, encoding="utf-8", newline="\n")
    ok("已从 .env.example 创建 .env")


# --- 步骤 5：配置校验 ---

def validate() -> bool:
    sys.path.insert(0, str(ROOT))
    try:
        from src.config import check_config, print_config
    except Exception as e:
        fail(f"无法导入配置模块: {e}")
        return False

    print_config()
    problems = check_config(require_api=True)

    if not problems:
        ok("配置完整")
        return True

    print(f"\n  {C.YELLOW}待处理事项:{C.RESET}")
    for i, p in enumerate(problems, 1):
        print(f"    {i}. {p}")
    return False


# --- 主流程 ---

def main() -> None:
    ap = argparse.ArgumentParser(description="一键安装金融问答系统")
    ap.add_argument("--skip-deps", action="store_true", help="跳过依赖安装")
    ap.add_argument("--skip-models", action="store_true", help="跳过模型下载")
    ap.add_argument("--check", action="store_true", help="只检查环境，不做任何安装")
    args = ap.parse_args()

    banner("金融领域问答系统 · 一键安装")
    print(f"  项目目录: {ROOT}")
    print(f"  操作系统: {platform.system()} {platform.release()}")

    check_only = args.check
    total = 5

    # --- 1. 环境检查 ---
    step(1, total, "环境检查")
    if not check_python():
        sys.exit(1)
    check_disk()
    check_gpu()

    if check_only:
        check_env_code()
        status = check_models()
        for name, (ready, path) in status.items():
            _, desc, _ = MODEL_SPECS[name]
            if ready:
                ok(f"{desc}: 已就绪  ({path})")
            else:
                warn(f"{desc}: 未找到")
        check_index()
        print()
        sys.exit(0)

    # --- 2. 依赖 ---
    step(2, total, "依赖安装")
    missing = get_missing_packages()
    if args.skip_deps:
        if missing:
            warn(f"跳过了 {len(missing)} 个缺失依赖")
        else:
            ok("所有依赖已安装")
    else:
        if not install_deps(missing):
            fail("依赖安装失败，后续步骤可能无法进行")

    # --- 3. 模型 ---
    step(3, total, "模型下载")
    models_ready = handle_models(args.skip_models)

    # --- 4. 配置文件 ---
    step(4, total, "配置文件")
    create_env()

    # --- 5. 校验 ---
    step(5, total, "配置校验")
    config_ready = validate()

    # --- 总结 ---
    banner("安装结果")

    deps_ok = not get_missing_packages()
    index_ok = (ROOT / "index" / "chroma" / "chroma.sqlite3").exists()

    checks = [
        ("依赖包", deps_ok),
        ("模型文件", models_ready),
        ("配置文件", (ROOT / ".env").exists()),
        ("检索索引", index_ok),
        ("API 配置", config_ready),
    ]

    for label, passed in checks:
        (ok if passed else warn)(f"{label}: {'就绪' if passed else '待处理'}")

    all_ready = all(p for _, p in checks)

    print()
    if all_ready:
        print(f"{C.GREEN}{C.BOLD}  一切就绪！{C.RESET}\n")
        print("  启动方式:")
        print(f"    {C.CYAN}streamlit run app/streamlit_app.py{C.RESET}   # 网页界面")
        print(f"    {C.CYAN}python -m src.pipeline chat{C.RESET}          # 命令行问答")
        print(f"    {C.CYAN}python -m src.pipeline demo{C.RESET}          # 快速验证")
    else:
        print(f"{C.YELLOW}{C.BOLD}  还有事项待处理：{C.RESET}")
        if not deps_ok:
            print("    - 依赖未装全: pip install -r requirements.txt")
        if not models_ready:
            print("    - 模型未就绪: python setup.py --skip-deps")
        if not config_ready:
            print("    - 请在 .env 中填入 LLM_API_KEY")
            print(f"      申请地址: {C.CYAN}https://platform.deepseek.com/{C.RESET}")
        if not index_ok:
            print("    - 索引缺失: python -m src.pipeline build")
        print("\n  完成后重新运行: python setup.py")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{C.YELLOW}已中断。可重新运行 python setup.py 继续。{C.RESET}\n")
        sys.exit(130)
