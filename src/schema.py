"""核心数据结构 —— 模块间契约

这些结构是 indexer / retrieval / generator / app 之间的接口约定，
任何模块改动都不得破坏这里的字段语义。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Chunk:
    """一个检索单元（文档片段）

    Attributes:
        id: 全局唯一标识，格式 f"{doc_id}_{seq:04d}"
        text: 片段正文
        metadata: 溯源元数据（公司/年份/文档类型/页码/章节）
        score: 检索得分，索引阶段为 0.0
    """

    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0

    @property
    def company(self) -> str:
        return self.metadata.get("company", "")

    @property
    def year(self) -> str:
        return str(self.metadata.get("year", ""))

    @property
    def doc_type(self) -> str:
        return self.metadata.get("doc_type", "")

    @property
    def source(self) -> str:
        return self.metadata.get("source", "")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Chunk":
        return cls(
            id=d["id"],
            text=d["text"],
            metadata=d.get("metadata", {}),
            score=float(d.get("score", 0.0)),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def brief(self, n: int = 60) -> str:
        """用于日志与调试的简短表示"""
        head = self.text[:n].replace("\n", " ")
        return f"[{self.id}] ({self.company}/{self.year}) {head}..."


@dataclass
class Answer:
    """生成层的结构化输出

    Attributes:
        answer: 回答正文
        citations: 引用的 chunk id 列表
        confidence: 模型自评置信度 0-1
        refused: 是否拒答（无法从检索内容得出答案时为 True）
        contexts: 实际使用的检索片段（用于前端溯源）
    """

    answer: str
    citations: list[str] = field(default_factory=list)
    confidence: float = 0.0
    refused: bool = False
    contexts: list[Chunk] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["contexts"] = [c.to_dict() for c in self.contexts]
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Answer":
        return cls(
            answer=d.get("answer", ""),
            citations=d.get("citations", []),
            confidence=float(d.get("confidence", 0.0)),
            refused=bool(d.get("refused", False)),
            contexts=[Chunk.from_dict(c) for c in d.get("contexts", [])],
        )
