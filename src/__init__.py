"""金融领域问答系统

模块划分：
- config    全局配置（路径、模型、检索参数）
- schema    核心数据结构（Chunk / Answer）—— 模块间契约
- parser    文档解析（HTML/PDF/TXT → 文本）
- chunker   分块（按财报章节语义切分）
- retrieval 混合检索（BM25 + 向量 → RRF → Rerank）
- generator 生成（LLM API + 提示词注入 + 引用校验）
- pipeline  端到端编排
"""
from .schema import Answer, Chunk  # noqa: F401

__all__ = ["Chunk", "Answer"]
__version__ = "0.1.0"
