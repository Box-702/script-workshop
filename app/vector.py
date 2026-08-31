# =====================================================================
# vector.py —— 可选向量检索（RAG）层
#
# 核心需求里，Agent 需要「读取相关原文」来把改编接地气。这里提供两种
# 实现（同一接口）：
#   - MilvusVectorStore：真正的向量库（生产 / Docker），按项目隔离检索；
#   - InMemoryVectorStore：进程内余弦搜索，用于无 Milvus 时本地调试。
# 二者都实现 ``VectorStore``，上层工具只依赖接口，因此 Milvus 是「可选」
# 增强而非硬依赖。
#
# 嵌入器同样可插拔：
#   - OpenAIEmbedder：OpenAI 兼容嵌入接口（需要 key）；
#   - HashingEmbedder：离线确定性哈希向量（无模型 / 无 key 也能跑通索引与检索）。
# 这样整个 RAG 链路在「没配任何外部服务」的机器上也能演示机制。
#
# 使用约定：库名统一用 settings.milvus_collection，向量维度取 embedder.dim，
# 并且每条记录都带 project_id 字段，检索时按项目过滤，避免串数据。
# =====================================================================

from __future__ import annotations

import hashlib
import math
from typing import Any, Protocol

from .config import Settings
from .domain import Script
from .store import Project, Store


class Embedder(Protocol):
    """文本 -> 向量。"""

    @property
    def dim(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class VectorStore(Protocol):
    """向量检索后端接口。"""

    def upsert(self, rows: list[dict[str, Any]]) -> None: ...

    def search(self, query_vec: list[float], *, project_id: str, k: int = 4) -> list[dict[str, Any]]: ...

    def delete_project(self, project_id: str) -> None: ...

    def reset(self) -> None: ...


# ---------- 嵌入器 ----------


class HashingEmbedder:
    """确定性离线哈希嵌入。

    把文本按字符 n-gram 哈希到固定维度并将向量归一化。优点是完全离线、
    无需模型；缺点是没有语义相似度，只用于演示向量索引 / 检索机制，
    或作为没有嵌入 key 时的兜底。
    """

    def __init__(self, dim: int = 768) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def _features(self, text: str) -> list[str]:
        tokens: list[str] = []
        t = text.lower()
        for n in (3, 2, 1):
            tokens.extend(t[i : i + n] for i in range(len(t) - n + 1))
        # 加入词级特征，增强区分度。
        tokens.extend(t.split())
        return [x for x in tokens if x]

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self._dim
            for token in self._features(text):
                h = int(hashlib.md5(token.encode("utf-8")).hexdigest()[:8], 16)
                idx = h % self._dim
                sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
                vec[idx] += sign
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            out.append(vec)
        return out


class OpenAIEmbedder:
    """基于 langchain OpenAIEmbeddings 的嵌入器（OpenAI 兼容接口）。

    维度在首次嵌入时探测（有些模型允许 `dimensions` 参数缩维），
    从而与 Milvus collection 维度保持一致。
    """

    def __init__(self, *, api_key: str, base_url: str, model: str, dim: int) -> None:
        from langchain_openai import OpenAIEmbeddings

        self._dim = dim
        # 优先尝试显式 dimensions；若模型不支持则退化为不带该参数。
        try:
            self._client = OpenAIEmbeddings(
                model=model, api_key=api_key, base_url=base_url, dimensions=dim
            )
        except Exception:  # noqa: BLE001
            self._client = OpenAIEmbeddings(model=model, api_key=api_key, base_url=base_url)
        self._dims: int | None = None

    @property
    def dim(self) -> int:
        return self._dims or self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._client.embed_documents(texts)
        if self._dims is None and vectors:
            self._dims = len(vectors[0])
        return vectors


def build_embedder(settings: Settings) -> Embedder:
    """按配置构造嵌入器。openai 需要 key；否则回退为离线哈希。"""
    if (
        settings.embedding_provider == "openai"
        and settings.embedding_api_key.strip()
    ):
        return OpenAIEmbedder(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
            model=settings.embedding_model,
            dim=settings.embedding_dim,
        )
    return HashingEmbedder(dim=settings.embedding_dim)


# ---------- 向量后端 ----------


class InMemoryVectorStore:
    """进程内向量库：余弦相似度检索。

    用于无 Milvus 时的本地调试，接口与 Milvus 实现一致。
    """

    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] = []

    def upsert(self, rows: list[dict[str, Any]]) -> None:
        self._rows.extend(rows)

    def delete_project(self, project_id: str) -> None:
        self._rows = [r for r in self._rows if r.get("project_id") != project_id]

    def reset(self) -> None:
        self._rows = []

    def search(self, query_vec: list[float], *, project_id: str, k: int = 4) -> list[dict[str, Any]]:
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in self._rows:
            if row.get("project_id") != project_id:
                continue
            vec = row.get("vector") or []
            score = _cosine(query_vec, vec)
            scored.append((score, row))
        scored.sort(key=lambda x: x[0], reverse=True)
        hits = []
        for score, row in scored[:k]:
            item = dict(row)
            item["score"] = score
            hits.append(item)
        return hits


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class MilvusVectorStore:
    """基于 Milvus 的向量库，按 project_id 过滤检索。

    连接失败时由 factory 捕获并回退到 InMemoryVectorStore。
    """

    def __init__(self, *, uri: str, collection: str, dim: int, user: str = "", password: str = "") -> None:
        from pymilvus import DataType, MilvusClient

        self._client = MilvusClient(uri=uri, user=user, password=password)
        self._collection = collection
        self._dim = dim
        if not self._client.has_collection(collection):
            self._client.create_collection(
                collection_name=collection,
                dimension=dim,
                primary_field_name="id",
                id_type="string",
                metric_type="COSINE",
                enable_dynamic_field=True,
                max_length=512,
            )

    def upsert(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        data = [
            {
                "id": r["id"],
                "vector": r["vector"],
                "text": r["text"],
                "project_id": str(r.get("project_id") or ""),
                "chapter_index": int(r.get("chapter_index") or 0),
            }
            for r in rows
        ]
        self._client.upsert(collection_name=self._collection, data=data)

    def delete_project(self, project_id: str) -> None:
        self._client.delete(
            collection_name=self._collection,
            filter=f'project_id == "{project_id}"',
        )

    def reset(self) -> None:
        self._client.drop_collection(self._collection)

    def search(self, query_vec: list[float], *, project_id: str, k: int = 4) -> list[dict[str, Any]]:
        res = self._client.search(
            collection_name=self._collection,
            data=[query_vec],
            limit=k,
            output_fields=["text", "project_id", "chapter_index"],
            filter=f'project_id == "{project_id}"',
        )
        hits: list[dict[str, Any]] = []
        for item in res[0] if res else []:
            entity = item.get("entity") or item  # pymilvus 返回可能是 dict 或对象
            text = entity.get("text") if isinstance(entity, dict) else getattr(entity, "text", "")
            hits.append({"text": text, "score": item.get("distance", 0.0)})
        return hits


def build_vector_store(settings: Settings, embedder: Embedder) -> VectorStore:
    """构造向量后端。

    - 只有显式开启 RAG 且 Milvus 可达时才用 Milvus；
    - 否则用 InMemoryVectorStore，保证无外部服务也能演示。
    """
    if not settings.enable_rag:
        return InMemoryVectorStore()
    try:
        store = MilvusVectorStore(
            uri=settings.milvus_uri,
            collection=settings.milvus_collection,
            dim=embedder.dim,
            user=settings.milvus_user,
            password=settings.milvus_password,
        )
        # 探测服务器可用性。
        store.search([0.0] * embedder.dim, project_id="__probe__", k=1)
        return store
    except Exception:  # noqa: BLE001
        return InMemoryVectorStore()


# ---------- RAG 工具 ----------


def chunk_text(text: str, *, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    """把原始文本切成带重叠的块，便于向量化与检索。"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", "。", "！", "？", ".", " ", ""],
    )
    return [c.strip() for c in splitter.split_text(text) if c.strip()]


def index_project(
    vector: VectorStore,
    embedder: Embedder,
    *,
    project_id: str,
    raw_text: str,
    title: str,
) -> int:
    """把一个项目的原始文本切块、嵌入并写入向量库。返回写入的块数。"""
    chunks = chunk_text(raw_text or "")
    if not chunks:
        return 0
    # 用「标题 + 块」进行嵌入，提升检索的上下文质量。
    vectors = embedder.embed([f"{title}\n{c}" for c in chunks])
    rows = [
        {
            "id": f"{project_id}_{i:04d}",
            "vector": vectors[i],
            "text": chunks[i],
            "project_id": project_id,
            "chapter_index": i,
        }
        for i in range(len(chunks))
    ]
    vector.upsert(rows)
    return len(rows)


def retrieve(
    vector: VectorStore,
    embedder: Embedder,
    *,
    project_id: str,
    query: str,
    k: int = 4,
) -> list[str]:
    """按查询向量检索最相关的原文片段。"""
    vec = embedder.embed([query])[0]
    hits = vector.search(vec, project_id=project_id, k=k)
    return [str(h.get("text") or "") for h in hits if str(h.get("text") or "")]
