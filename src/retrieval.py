"""检索层：混合召回（BM25 + 向量）→ RRF 融合 → Rerank 重排

设计决策：
1. 混合检索而非纯向量 —— 金融问题分语义型（"经营风险如何"）和
   事实型（"2023Q3毛利率"）。纯向量在事实型问题上召回明显掉点，
   需要 BM25 关键词匹配兜底。
2. RRF 之后必须加 Reranker —— RRF 只融合"排序意见"，不理解
   query 与 passage 的语义交互；cross-encoder 直接对 (query, doc)
   打分，是 top-5 命中率提升性价比最高的一步。
"""
from __future__ import annotations

import pickle
from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi

from .config import (
    BM25_FILE,
    CHROMA_DIR,
    COLLECTION_NAME,
    DEVICE,
    EMBEDDING_MODEL_PATH,
    ENABLE_RERANK,
    RERANKER_MODEL_PATH,
    TOP_K_FINAL,
    TOP_K_RECALL,
)
from .schema import Chunk

_embedder = None
_reranker = None


# --- 模型懒加载（避免 import 时就吃掉显存）---

def get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        print(f"[模型] 加载 embedding: {EMBEDDING_MODEL_PATH} (device={DEVICE})")
        _embedder = SentenceTransformer(EMBEDDING_MODEL_PATH, device=DEVICE)
    return _embedder


def get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        print(f"[模型] 加载 reranker: {RERANKER_MODEL_PATH} (device={DEVICE})")
        # 8GB 显存约束：fp16 + 小 batch，OOM 就把 max_length 降到 256
        _reranker = CrossEncoder(
            RERANKER_MODEL_PATH,
            device=DEVICE,
            max_length=512,
        )
    return _reranker


# --- 关键词检索 ---

def tokenize(text: str) -> list[str]:
    """中文分词，过滤空白与单字噪声"""
    return [t for t in jieba.lcut(text) if t.strip() and len(t) > 1]


class BM25Index:
    """BM25 关键词索引"""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.corpus_tokens = [tokenize(c.text) for c in chunks]
        self.bm25 = BM25Okapi(self.corpus_tokens) if chunks else None

    def search(self, query: str, top_k: int = TOP_K_RECALL) -> list[Chunk]:
        if not self.bm25 or not self.chunks:
            return []
        scores = self.bm25.get_scores(tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        out: list[Chunk] = []
        for i in ranked:
            if scores[i] <= 0:
                continue
            c = self.chunks[i]
            out.append(
                Chunk(id=c.id, text=c.text, metadata=c.metadata, score=float(scores[i]))
            )
        return out

    def save(self, path: Path = BM25_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: Path = BM25_FILE) -> "BM25Index":
        with path.open("rb") as f:
            return pickle.load(f)


# --- 向量检索 ---

def get_collection():
    import chromadb

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )


def build_vector_index(chunks: list[Chunk], batch_size: int = 64) -> None:
    """向量化并写入 Chroma（幂等：先清空再写）"""
    import chromadb

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(
        name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )

    embedder = get_embedder()
    total = len(chunks)
    for i in range(0, total, batch_size):
        batch = chunks[i : i + batch_size]
        vectors = embedder.encode(
            [c.text for c in batch],
            batch_size=16,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        collection.add(
            ids=[c.id for c in batch],
            embeddings=[v.tolist() for v in vectors],
            documents=[c.text for c in batch],
            metadatas=[_clean_meta(c.metadata) for c in batch],
        )
        print(f"[索引] {min(i + batch_size, total)}/{total}", end="\r")
    print(f"\n[索引] 完成，共 {total} 条")


def _clean_meta(meta: dict) -> dict:
    """Chroma 只接受 str/int/float/bool，其他类型统一转 str"""
    out = {}
    for k, v in meta.items():
        out[k] = v if isinstance(v, (str, int, float, bool)) else str(v)
    return out


def vector_search(query: str, top_k: int = TOP_K_RECALL) -> list[Chunk]:
    embedder = get_embedder()
    qv = embedder.encode([query], normalize_embeddings=True)[0]
    collection = get_collection()
    res = collection.query(query_embeddings=[qv.tolist()], n_results=top_k)

    out: list[Chunk] = []
    ids = res.get("ids", [[]])[0]
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    for cid, doc, meta, dist in zip(ids, docs, metas, dists):
        out.append(
            Chunk(id=cid, text=doc, metadata=dict(meta), score=1.0 - float(dist))
        )
    return out


# --- RRF 融合 ---

def rrf_fuse(result_lists: list[list[Chunk]], k: int = 60, top_k: int = TOP_K_RECALL) -> list[Chunk]:
    """Reciprocal Rank Fusion

    score(d) = Σ 1 / (k + rank_i(d))
    k=60 是原论文默认值，无需调参，对异构排序器鲁棒。
    """
    fused: dict[str, float] = {}
    store: dict[str, Chunk] = {}

    for results in result_lists:
        for rank, chunk in enumerate(results, start=1):
            fused[chunk.id] = fused.get(chunk.id, 0.0) + 1.0 / (k + rank)
            store.setdefault(chunk.id, chunk)

    ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    return [
        Chunk(id=cid, text=store[cid].text, metadata=store[cid].metadata, score=score)
        for cid, score in ranked
    ]


# --- Rerank ---

def rerank(query: str, candidates: list[Chunk], top_k: int = TOP_K_FINAL) -> list[Chunk]:
    """cross-encoder 重排：直接对 (query, passage) 打分"""
    if not candidates:
        return []
    if not ENABLE_RERANK:
        return candidates[:top_k]

    model = get_reranker()
    pairs = [(query, c.text) for c in candidates]
    scores = model.predict(pairs, batch_size=4, show_progress_bar=False)

    ranked = sorted(zip(candidates, scores), key=lambda x: float(x[1]), reverse=True)[:top_k]
    return [
        Chunk(id=c.id, text=c.text, metadata=c.metadata, score=float(s) + 0.01)
        for c, s in ranked
    ]


# --- 对外统一接口 ---

class Retriever:
    """混合检索器 —— 这是模块间的主契约接口"""

    def __init__(self, chunks: list[Chunk] | None = None):
        self.chunks = chunks or []
        self.bm25_index: BM25Index | None = None

    def load(self) -> "Retriever":
        """从磁盘加载 BM25 索引（向量库由 Chroma 自己管理）"""
        if BM25_FILE.exists():
            self.bm25_index = BM25Index.load(BM25_FILE)
            self.chunks = self.bm25_index.chunks
        return self

    def search(
        self,
        query: str,
        top_k: int = TOP_K_FINAL,
        mode: str = "hybrid",
    ) -> list[Chunk]:
        """检索入口

        Args:
            mode: "vector" | "bm25" | "hybrid"（默认，含 RRF + Rerank）
        """
        if mode == "vector":
            return vector_search(query, top_k=top_k)

        if mode == "bm25":
            if self.bm25_index is None:
                self.load()
            return (self.bm25_index.search(query, top_k) if self.bm25_index else [])[:top_k]

        # hybrid：两路召回 → RRF → Rerank
        vec_hits = vector_search(query, top_k=TOP_K_RECALL)
        bm25_hits = self.bm25_index.search(query, top_k=TOP_K_RECALL) if self.bm25_index else []
        fused = rrf_fuse([vec_hits, bm25_hits], top_k=TOP_K_RECALL)
        return rerank(query, fused, top_k=top_k)
