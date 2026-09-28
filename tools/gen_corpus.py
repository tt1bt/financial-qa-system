"""扩充语料生成器 —— 生成规模接近真实年报的测试数据

目的：样例数据仅 7 个 chunk，检索对比实验缺乏统计意义。
本脚本基于真实年报的章节结构与数据分布，生成约 60-100 个 chunk 的语料，
用于验证检索策略在真实负载下的表现。

重要说明：这是合成数据，数字为虚构/参考公开信息，仅用于链路验证与
实验方法演示。正式提交的报告应替换为从巨潮资讯网下载的真实年报。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 语料内容较长，直接从数据模块导入
from tools.corpus_data import RISK_SECTION, SECTIONS  # noqa: E402


def build_report() -> str:
    """组装完整年报文本（含风险章节）"""
    parts = ["贵州茅台2023年年度报告"]
    for idx, (title, body) in enumerate(SECTIONS.items()):
        parts.append(f"\n{title}\n\n{body}")
        # 风险章节真实年报位于管理层讨论之后
        if idx == 2:
            parts.append(f"\n{RISK_SECTION}")
    return "\n".join(parts)


def main() -> None:
    from src.chunker import build_chunks

    report = build_report()
    out = Path(__file__).resolve().parent.parent / "data" / "raw" / "贵州茅台2023年年度报告.txt"
    out.write_text(report, encoding="utf-8")
    print(f"✓ 已生成 {out}")
    print(f"  总字数: {len(report):,}")

    docs = [{"text": report, "source": out.name, "path": str(out)}]
    chunks = build_chunks(docs)
    print(f"  分块数: {len(chunks)}\n")
    for c in chunks:
        print(f"  {c.id}  {len(c.text):5d}字  {c.metadata['section'][:46]}")


if __name__ == "__main__":
    main()
