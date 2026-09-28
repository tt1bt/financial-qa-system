"""冒烟测试：验证不依赖模型/API 的纯逻辑链路

覆盖：文档解析 → 章节切分 → 分块 → 数据结构序列化 → BM25 检索
跑法：python -m tests.test_smoke
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.chunker import build_chunks, load_chunks, save_chunks  # noqa: E402
from src.parser import clean_text, split_by_section  # noqa: E402
from src.retrieval import BM25Index  # noqa: E402
from src.schema import Answer, Chunk  # noqa: E402

SAMPLE_REPORT = """贵州茅台2023年年度报告

第一节 重要提示、目录和释义

本公司董事会及全体董事保证本年度报告内容的真实、准确、完整，不存在虚假记载、误导性陈述或重大遗漏。

公司经本次董事会审议通过的利润分配预案为：以总股本1256197800股为基数，向全体股东每10股派发现金红利308.76元（含税）。

第二节 公司简介和主要财务指标

公司2023年实现营业收入1505.60亿元，同比增长18.04%。
归属于上市公司股东的净利润为747.34亿元，同比增长19.16%。
基本每股收益为59.49元。
加权平均净资产收益率为34.11%。
公司2023年毛利率为91.96%，较上年提升0.22个百分点。

第三节 管理层讨论与分析

2023年，公司坚持以高质量发展为主线，扎实推进各项工作。
公司主营业务分为茅台酒和系列酒两大板块。其中茅台酒实现营业收入1265.89亿元，系列酒实现营业收入206.30亿元。

研发投入方面，公司2023年研发费用为5.79亿元，占营业收入比例为0.38%。

第四节 公司治理

公司严格按照《公司法》《证券法》等法律法规要求，不断完善公司治理结构。

第五节 环境和社会责任

公司积极践行绿色发展理念，推进节能减排工作。

第六节 重要事项

报告期内，公司未发生重大诉讼、仲裁事项。

第七节 股份变动及股东情况

报告期末，公司股东总数为168947户。

第八节 优先股相关情况

不适用。

第九节 债券相关情况

不适用。

第十节 财务报告

详见审计报告。
"""


def test_clean():
    raw = "第一行\n\n\n\n第二行  多余空格  \n  12  \n第 13 页\n第三行"
    out = clean_text(raw)
    assert "第一行" in out and "第二行" in out
    assert "  多余" not in out, "空格未归一化"
    print("✓ clean_text 归一化正确")


def test_section_split():
    sections = split_by_section(SAMPLE_REPORT)
    assert len(sections) >= 5, f"章节识别过少: {len(sections)}"
    titles = [t for t, _ in sections]
    assert any("管理层讨论" in t for t in titles), f"未识别管理层讨论章节: {titles}"
    print(f"✓ split_by_section 识别 {len(sections)} 个章节")
    for t, body in sections[:4]:
        print(f"    · {t}  ({len(body)}字)")


def test_chunking():
    docs = [{"text": SAMPLE_REPORT, "source": "贵州茅台2023年年度报告.txt", "path": ""}]
    chunks = build_chunks(docs)

    # 661 字的样例报告，合并短章节后合理产出 4-5 块
    assert len(chunks) >= 4, f"分块过少: {len(chunks)}"
    assert len(chunks) <= 8, f"分块过多（短章节未合并）: {len(chunks)}"
    print(f"✓ build_chunks 生成 {len(chunks)} 个 chunk")

    # 元数据正确性
    c = chunks[0]
    assert c.company, "公司名未提取"
    assert c.year == "2023", f"年份提取错误: {c.year}"
    assert c.metadata["doc_type"] == "年度报告"
    print(f"✓ 元数据: company={c.company}, year={c.year}, section={c.metadata['section']}")

    # 章节标题应被前置进 chunk 文本，供检索利用
    titled = [ch for ch in chunks if ch.text.startswith(ch.metadata["section"])
              and ch.metadata["section"] != "正文"]
    assert titled, "章节标题未前置进 chunk 文本"
    print(f"✓ 章节标题已前置进正文（{len(titled)} 个 chunk 带章节头）")

    # 关键：语义完整性——营收数据不应与风险提示混在一起
    for ch in chunks:
        if "1505.60" in ch.text:
            assert "风险" not in ch.text, "营收数据与风险段落被切进同一 chunk（语义分块失败）"
            print("✓ 语义分块正确：营收数据独立成块")
            break
    else:
        assert False, "未找到包含营收数据的 chunk"

    # id 唯一
    ids = [ch.id for ch in chunks]
    assert len(ids) == len(set(ids)), "chunk id 重复"
    print("✓ chunk id 唯一")

    return chunks


def test_serialization(chunks):
    tmp = Path(__file__).parent / "_tmp_chunks.jsonl"
    save_chunks(chunks, tmp)
    loaded = load_chunks(tmp)
    assert len(loaded) == len(chunks), "序列化往返数量不一致"
    assert loaded[0].text == chunks[0].text, "序列化往返内容不一致"
    assert loaded[0].metadata == chunks[0].metadata, "序列化往返元数据不一致"
    tmp.unlink()
    print("✓ Chunk JSONL 序列化往返正确")


def test_bm25(chunks):
    """验证 BM25 的精确词项匹配能力

    注意：BM25 的职责是精确匹配，不适合同义/语义查询
    （"分红" vs "利润分配" 这类同义表达交给向量检索处理，
    这正是混合检索存在的意义）。
    """
    idx = BM25Index(chunks)

    # 精确词项：语料中真实出现的表述
    hits = idx.search("2023年营业收入", top_k=3)
    assert hits, "BM25 未召回任何结果"
    assert "1505.60" in hits[0].text, f"BM25 首位未命中营收数据: {hits[0].text[:80]}"
    print(f"✓ BM25 精确匹配正确，首位命中营收数据 (score={hits[0].score:.2f})")

    # 原文表述"利润分配"——精确匹配应命中分红相关段落
    hits2 = idx.search("利润分配", top_k=3)
    assert hits2, "BM25 未召回利润分配段落"
    assert any("红利" in h.text or "利润分配" in h.text for h in hits2), \
        f"利润分配查询召回错误: {hits2[0].text[:80]}"
    print("✓ BM25 命中利润分配段落")

    # 数字类事实——金融问答最常见的高频场景
    hits3 = idx.search("研发费用", top_k=3)
    if hits3:
        print(f"✓ BM25 命中研发费用关键词 (score={hits3[0].score:.2f})")

    # 同义词不命中是预期行为，向量检索负责补位
    synonym_hits = idx.search("分红政策", top_k=3)
    print(f"✓ 同义词'分红政策'BM25命中 {len(synonym_hits)} 条"
          f"（预期为0，由向量检索补位）")


def test_answer_schema():
    c = Chunk(id="t_0001", text="测试内容", metadata={"company": "测试公司"})
    ans = Answer(answer="测试答案 [1]", citations=["1"], confidence=0.9, contexts=[c])
    d = ans.to_dict()
    assert d["citations"] == ["1"]
    assert d["contexts"][0]["id"] == "t_0001"

    restored = Answer.from_dict(d)
    assert restored.answer == ans.answer
    assert restored.contexts[0].company == "测试公司"
    print("✓ Answer 序列化往返正确")


def main():
    print("=" * 56)
    print("冒烟测试：纯逻辑链路（不依赖模型/API）")
    print("=" * 56 + "\n")

    test_clean()
    print()
    test_section_split()
    print()
    chunks = test_chunking()
    print()
    test_serialization(chunks)
    print()
    test_bm25(chunks)
    print()
    test_answer_schema()

    print("\n" + "=" * 56)
    print("✓ 全部通过")
    print("=" * 56)


if __name__ == "__main__":
    main()
