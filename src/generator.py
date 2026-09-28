"""生成层：LLM API 调用 + 提示词注入 + 引用校验 + 拒答

设计决策：
- 强制引用是金融场景的生命线。要求模型逐句标注来源编号，
  无来源即拒答。这既是防幻觉手段，也是可信度的工程落地。
- 输出结构化 JSON，便于评测与前端渲染。
"""
from __future__ import annotations

import json
import re
from typing import Any

from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from .schema import Answer, Chunk

# --- 提示词模板 ---

SYSTEM_PROMPT = """你是一名严谨的金融分析师，专门回答关于中国上市公司的问题。

【核心规则】
1. 只依据<参考资料>中的内容作答，绝不使用你的先验知识补充事实。
2. 每一个事实性陈述都必须标注来源编号，格式如 [1]、[2]。
3. 如果参考资料中没有足够信息回答问题，必须拒答，不许猜测。
4. 涉及数字（营收、利润、毛利率等）必须与原文完全一致，不得换算或估算。

【拒答规则】
以下情况必须拒答（refused=true）：
- 参考资料中完全没有相关信息
- 问题涉及未来预测、股价走势等参考资料无法回答的内容
- 问题涉及其他公司或参考资料未覆盖的时间段

【输出格式】
必须返回严格的 JSON，不要包含 markdown 代码块标记：
{
  "answer": "回答正文，含 [1] 这样的引用标注",
  "citations": ["1", "2"],
  "confidence": 0.0-1.0 之间的置信度,
  "refused": false
}"""

FEW_SHOT = """【示例1 · 正常回答】
参考资料：
[1] 公司2023年实现营业收入1505.60亿元，同比增长18.04%。
[2] 归属于上市公司股东的净利润为747.34亿元，同比增长19.16%。
问题：公司2023年的营收和净利润是多少？
输出：
{"answer": "公司2023年实现营业收入1505.60亿元，同比增长18.04% [1]；归属于上市公司股东的净利润747.34亿元，同比增长19.16% [2]。", "citations": ["1", "2"], "confidence": 0.95, "refused": false}

【示例2 · 必须拒答】
参考资料：
[1] 公司2023年实现营业收入1505.60亿元。
问题：公司明天的股价会涨吗？
输出：
{"answer": "参考资料中未包含股价预测相关信息，无法回答该问题。本系统仅基于已披露的财务报告内容作答。", "citations": [], "confidence": 0.0, "refused": true}"""

USER_TEMPLATE = """<参考资料>
{context}
</参考资料>

问题：{question}

请按系统提示要求的 JSON 格式输出。"""


def build_context(chunks: list[Chunk]) -> str:
    """把检索片段编号后拼成上下文 —— 编号是引用校验的基础"""
    if not chunks:
        return "（无参考资料）"
    parts = []
    for i, c in enumerate(chunks, start=1):
        meta = f"{c.company} {c.year} {c.doc_type}".strip()
        header = f"[{i}] 来源：{meta}"
        if c.metadata.get("section"):
            header += f" · {c.metadata['section']}"
        parts.append(f"{header}\n{c.text}")
    return "\n\n".join(parts)


def _get_client():
    from openai import OpenAI

    if not LLM_API_KEY:
        raise RuntimeError(
            "未配置 LLM_API_KEY。请复制 .env.example 为 .env 并填入 API Key。"
        )
    return OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)


def _extract_json(text: str) -> dict[str, Any]:
    """从模型输出中稳健地抠出 JSON（容忍 markdown 包裹与前后废话）"""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 退而求其次：抓第一个平衡的 {...}
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i, ch in enumerate(text[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    # 彻底失败：当作纯文本回答，标记低置信
    return {"answer": text, "citations": [], "confidence": 0.0, "refused": False}


def _validate_citations(data: dict, chunks: list[Chunk]) -> tuple[list[str], bool]:
    """校验引用编号是否合法；返回 (合法引用列表, 是否需要拒答)"""
    valid_ids = {str(i) for i in range(1, len(chunks) + 1)}
    raw = data.get("citations", [])
    if isinstance(raw, str):
        raw = re.findall(r"\d+", raw)
    citations = [str(c) for c in raw if str(c) in valid_ids]

    # 答案里出现 [n] 但 n 不在合法范围内 → 引用越界
    cited_in_text = set(re.findall(r"\[(\d+)\]", data.get("answer", "")))
    has_out_of_range = bool(cited_in_text - valid_ids)

    # 有实质性答案却没有任何合法引用 → 判定为不可信，强制拒答
    answer_text = data.get("answer", "").strip()
    no_citation = len(answer_text) > 30 and not citations and not data.get("refused")

    need_refuse = has_out_of_range or no_citation

    return citations, need_refuse


def generate(question: str, chunks: list[Chunk], temperature: float = 0.0) -> Answer:
    """生成回答 —— 这是生成层的主契约接口

    Args:
        question: 用户问题
        chunks: 检索到的参考片段（已按相关性排序）
        temperature: 金融问答建议 0，保证可复现
    """
    if not chunks:
        return Answer(
            answer="未检索到相关参考资料，无法回答该问题。",
            citations=[],
            confidence=0.0,
            refused=True,
            contexts=[],
        )

    client = _get_client()
    context = build_context(chunks)
    user_msg = USER_TEMPLATE.format(context=context, question=question)

    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": FEW_SHOT + "\n\n" + user_msg},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
    )

    raw = resp.choices[0].message.content or ""
    data = _extract_json(raw)
    citations, need_refuse = _validate_citations(data, chunks)

    return Answer(
        answer=data.get("answer", ""),
        citations=citations,
        confidence=float(data.get("confidence", 0.0)),
        refused=bool(data.get("refused", False)) or need_refuse,
        contexts=chunks,
    )
