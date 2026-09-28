"""端到端编排 —— 命令行入口

用法：
    python -m src.pipeline config         # 检查配置（首次使用先跑这个）
    python -m src.pipeline build          # 建索引（解析 → 分块 → 向量化 → BM25）
    python -m src.pipeline ask "问题"      # 单次问答
    python -m src.pipeline chat           # 交互式问答
    python -m src.pipeline demo           # 内置问题跑一遍，验证链路
"""
from __future__ import annotations

import sys
from pathlib import Path

from .chunker import build_chunks, load_chunks, save_chunks
from .config import (
    BM25_FILE,
    CHUNKS_FILE,
    RAW_DIR,
    TOP_K_FINAL,
    check_config,
    print_config,
)
from .generator import generate
from .parser import load_documents
from .retrieval import BM25Index, Retriever, build_vector_index


def cmd_config() -> None:
    """检查配置并给出修复建议"""
    print_config()
    problems = check_config(require_api=True)
    if not problems:
        print("\n✓ 配置完整，可以开始使用")
        print("\n下一步:")
        print("  python -m src.pipeline chat   # 命令行问答")
        print("  streamlit run app/streamlit_app.py   # 网页界面")
    else:
        print(f"\n✗ 发现 {len(problems)} 个问题需要解决")
        sys.exit(1)


# --- 索引构建 ---

def build_index(company: str | None = None, doc_type: str = "年度报告") -> int:
    """完整索引流程：解析 → 分块 → 向量化 → BM25

    Returns:
        chunk 总数
    """
    print(f"[1/4] 解析文档: {RAW_DIR}")
    docs = load_documents(RAW_DIR)
    if not docs:
        print("  ✗ 未找到文档。请先把年报/公告放到 data/raw/ 目录。")
        return 0
    print(f"  ✓ 解析 {len(docs)} 篇文档")

    print("[2/4] 语义分块")
    chunks = build_chunks(docs, company=company, doc_type=doc_type)
    save_chunks(chunks, CHUNKS_FILE)
    print(f"  ✓ 生成 {len(chunks)} 个 chunk → {CHUNKS_FILE}")

    print("[3/4] 向量化写入 Chroma")
    build_vector_index(chunks)

    print("[4/4] 构建 BM25 索引")
    bm25 = BM25Index(chunks)
    bm25.save(BM25_FILE)
    print(f"  ✓ BM25 索引 → {BM25_FILE}")

    return len(chunks)


# --- 检索 + 生成 ---

def answer_question(
    question: str,
    retriever: Retriever | None = None,
    mode: str = "hybrid",
    top_k: int = TOP_K_FINAL,
    verbose: bool = False,
):
    """端到端问答：检索 → 生成"""
    if retriever is None:
        retriever = Retriever().load()

    chunks = retriever.search(question, top_k=top_k, mode=mode)

    if verbose:
        print(f"\n[检索] mode={mode}, 命中 {len(chunks)} 条")
        for i, c in enumerate(chunks, 1):
            print(f"  [{i}] score={c.score:.4f} {c.brief(70)}")

    ans = generate(question, chunks)
    return ans


# --- 命令行界面 ---

def cmd_build(argv: list[str]) -> None:
    company = argv[0] if argv else None
    build_index(company=company)


def cmd_ask(argv: list[str]) -> None:
    if not argv:
        print("用法: python -m src.pipeline ask \"你的问题\"")
        return
    question = " ".join(argv)
    ans = answer_question(question, verbose=True)

    print("\n" + "=" * 60)
    if ans.refused:
        print("【拒答】")
    print(ans.answer)
    print("=" * 60)
    if ans.citations:
        print(f"引用: {', '.join('[' + c + ']' for c in ans.citations)}")
    print(f"置信度: {ans.confidence:.2f}")

    print("\n【溯源】")
    for cid in ans.citations:
        idx = int(cid) - 1
        if 0 <= idx < len(ans.contexts):
            c = ans.contexts[idx]
            print(f"  [{cid}] {c.company} {c.year} {c.metadata.get('section', '')}")
            print(f"      {c.text[:120]}...")


def cmd_chat() -> None:
    retriever = Retriever().load()
    if not retriever.chunks:
        print("✗ 索引为空，请先运行: python -m src.pipeline build")
        return

    print(f"已加载 {len(retriever.chunks)} 个 chunk。输入问题，q 退出。\n")
    while True:
        try:
            q = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in ("q", "quit", "exit"):
            break
        if not q:
            continue

        ans = answer_question(q, retriever)
        tag = "【拒答】" if ans.refused else ""
        print(f"\n{tag}{ans.answer}")
        if ans.citations:
            print(f"引用: {', '.join('[' + c + ']' for c in ans.citations)} | 置信度 {ans.confidence:.2f}")
        print()


DEMO_QUESTIONS = [
    "公司2023年的营业收入是多少？",          # 事实型
    "公司主要面临哪些经营风险？",            # 语义型
    "公司的分红政策是怎样的？",              # 语义型
    "公司明天的股价会涨吗？",                # 应拒答
    "特斯拉2023年的营收是多少？",            # 应拒答（其他公司）
]


def cmd_demo() -> None:
    """用内置问题验证链路，是 D1 的核心验收手段"""
    retriever = Retriever().load()
    if not retriever.chunks:
        print("✗ 索引为空，请先运行: python -m src.pipeline build")
        return

    print(f"索引: {len(retriever.chunks)} chunks\n")
    for q in DEMO_QUESTIONS:
        print("=" * 60)
        print(f"问: {q}")
        ans = answer_question(q, retriever)
        tag = "【拒答】" if ans.refused else ""
        print(f"{tag}{ans.answer[:200]}")
        if ans.citations:
            print(f"引用: {ans.citations} | 置信度 {ans.confidence:.2f}")
    print("=" * 60)


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return

    cmd = argv[0].lower()
    rest = argv[1:]

    if cmd == "config":
        cmd_config()
        return

    if cmd == "build":
        cmd_build(rest)
    elif cmd == "ask":
        cmd_ask(rest)
    elif cmd == "chat":
        cmd_chat()
    elif cmd == "demo":
        cmd_demo()
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
