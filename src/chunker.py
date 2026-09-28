"""分块：文档 → Chunk 列表

策略：先按财报章节结构切，章节内再按段落边界 + 长度上限切。
保证每个 chunk 语义完整，不会把"营收"和"风险提示"混在一起。
"""
from __future__ import annotations

import re
from pathlib import Path

from .config import CHUNK_OVERLAP, CHUNK_SIZE, MIN_CHUNK_SIZE
from .parser import split_by_section
from .schema import Chunk


def _split_long_text(text: str, size: int, overlap: int) -> list[str]:
    """将超长文本按句子边界切成若干段，优先在句号/换行处断开"""
    if len(text) <= size:
        return [text] if text.strip() else []

    # 句子边界：中文句号、问号、叹号、分号、换行
    sentences = re.split(r"(?<=[。！？；\n])", text)
    sentences = [s for s in sentences if s.strip()]

    chunks: list[str] = []
    buf = ""
    for sent in sentences:
        if len(buf) + len(sent) <= size:
            buf += sent
        else:
            if buf.strip():
                chunks.append(buf.strip())
            # 单句本身就超长 → 硬切
            if len(sent) > size:
                for i in range(0, len(sent), size - overlap):
                    piece = sent[i : i + size].strip()
                    if piece:
                        chunks.append(piece)
                buf = ""
            else:
                # 带上一点重叠，保住跨句语义
                tail = buf[-overlap:] if len(buf) > overlap else buf
                buf = tail + sent
    if buf.strip():
        chunks.append(buf.strip())

    return chunks


def _detect_year(source: str, text: str) -> str:
    """从文件名或正文开头提取年份"""
    for pattern in (r"(20\d{2})\s*年", r"(20\d{2})"):
        m = re.search(pattern, source)
        if m:
            return m.group(1)
    m = re.search(r"(20\d{2})\s*年度报告", text[:500])
    if m:
        return m.group(1)
    return ""


def _detect_company(source: str, text: str) -> str:
    """从文件名或正文提取公司简称"""
    # 文件名形如 "贵州茅台2023年年度报告.txt"
    m = re.match(r"^([\u4e00-\u9fa5A-Za-z]{2,10}?)(?:20\d{2}|年度|年报)", source)
    if m:
        return m.group(1)
    m = re.search(r"([\u4e00-\u9fa5]{2,8}?)(?:股份)?有限公司", text[:800])
    if m:
        return m.group(1)
    return Path(source).stem[:8]


def _merge_short_sections(
    sections: list[tuple[str, str]],
    min_len: int = MIN_CHUNK_SIZE,
) -> list[tuple[str, str]]:
    """合并过短的相邻章节

    财报里有大量短章节（"优先股相关情况：不适用"），直接丢弃会丢失信息
    （有些短章节恰恰含关键内容，如分红预案），碎片化又不利于检索。
    策略：把短章节累积到缓冲区，攒够长度后与其标题一起成块。
    """
    merged: list[tuple[str, str]] = []
    buf_titles: list[str] = []
    buf_body: list[str] = []

    def flush() -> None:
        if buf_body:
            # 标题串过长会污染 chunk 语义，只保留前两个作为定位信息
            if len(buf_titles) > 2:
                label = " / ".join(buf_titles[:2]) + f" 等{len(buf_titles)}节"
            else:
                label = " / ".join(buf_titles) if buf_titles else "正文"
            merged.append((label, "\n".join(buf_body)))

    for title, body in sections:
        buf_titles.append(title)
        buf_body.append(body)
        if sum(len(b) for b in buf_body) >= min_len:
            flush()
            buf_titles, buf_body = [], []

    # 尾部不足 min_len 的碎片：若非纯占位内容（"不适用"等）则保留，否则丢弃
    tail = "\n".join(buf_body).strip()
    if tail and not _is_placeholder(tail):
        flush()
    return merged


_PLACEHOLDER_RE = re.compile(
    r"^(?:不适用|无|不涉及|详见[^。]{0,20}。?|略|—+|-\s*)+$"
)


def _is_placeholder(text: str) -> bool:
    """判断是否为占位内容（如整节只有"不适用"），这类块无检索价值"""
    body = text.strip()
    if not body or len(body) > 60:
        return False
    return bool(_PLACEHOLDER_RE.match(body))


def build_chunks(
    docs: list[dict],
    company: str | None = None,
    doc_type: str = "年度报告",
) -> list[Chunk]:
    """把解析后的文档切成 Chunk 列表

    Args:
        docs: load_documents() 的输出
        company: 指定公司名；None 则自动推断
        doc_type: 文档类型标签（年度报告/公告/研报/新闻）
    """
    all_chunks: list[Chunk] = []

    for doc in docs:
        source = doc["source"]
        text = doc["text"]
        comp = company or _detect_company(source, text)
        year = _detect_year(source, text)
        doc_id = Path(source).stem

        seq = 0
        sections = split_by_section(text)

        # 章节切不出来（非财报结构）→ 整体当作一节
        if not sections:
            sections = [("正文", text)]

        sections = _merge_short_sections(sections)

        for sec_title, sec_body in sections:
            for piece in _split_long_text(sec_body, CHUNK_SIZE, CHUNK_OVERLAP):
                if len(piece) < MIN_CHUNK_SIZE:
                    continue
                # 把章节标题前置进正文：向量模型能"看到"内容归属，
                # 检索"管理层讨论"这类问题时可命中整节内容
                enriched = f"{sec_title}\n{piece}" if sec_title != "正文" else piece
                all_chunks.append(
                    Chunk(
                        id=f"{doc_id}_{seq:04d}",
                        text=enriched,
                        metadata={
                            "company": comp,
                            "year": year,
                            "doc_type": doc_type,
                            "section": sec_title,
                            "source": source,
                            "seq": seq,
                        },
                        score=0.0,
                    )
                )
                seq += 1

    return all_chunks


def save_chunks(chunks: list[Chunk], path: Path) -> None:
    """落盘为 JSONL —— 这是模块间的契约文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(c.to_json() + "\n")


def load_chunks(path: Path) -> list[Chunk]:
    import json

    chunks: list[Chunk] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(Chunk.from_dict(json.loads(line)))
    return chunks
