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
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import Settings
from .domain import Script
from .store import Project, Store

log = logging.getLogger(__name__)


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

    def list_project(self, project_id: str) -> list[dict[str, Any]]: ...

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

    构造时用一次探测嵌入拿到模型**真实输出维度**，确保 Milvus collection
    的维度与向量一致（不同模型维度不同：embedding-3=2048、text-embedding-3-small=1536）。
    探测失败（如网络不可达）时退回声明维度，方便离线降级。
    """

    def __init__(self, *, api_key: str, base_url: str, model: str, dim: int) -> None:
        from langchain_openai import OpenAIEmbeddings

        self._dim = dim
        self._client = OpenAIEmbeddings(model=model, api_key=api_key, base_url=base_url)
        self._dims: int | None = None
        try:
            probe = self._client.embed_documents(["探"])
            if probe:
                self._dims = len(probe[0])
        except Exception:  # noqa: BLE001
            self._dims = None

    @property
    def dim(self) -> int:
        return self._dims or self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._client.embed_documents(texts)
        if self._dims is None and vectors:
            self._dims = len(vectors[0])
        return vectors


def build_embedder(settings: Settings) -> Embedder:
    """按配置构造嵌入器。

    优先级：
      1. EMBEDDING_PROVIDER=hashing   -> 离线哈希嵌入（无 key 演示用）；
      2. EMBEDDING_API_KEY            -> OpenAI 兼容嵌入（显式 EMBEDDING_* 生效）；
      3. ZHIPUAI_API_KEY              -> 智谱 embedding-3（OpenAI 兼容）；
      4. 都没有                         -> 离线哈希嵌入。
    注意：不能用「默认值 or 智谱值」的方式取 base_url，否则默认的 OpenAI
    地址会盖过智谱地址（默认值永远非空）。
    """
    if settings.embedding_provider == "hashing":
        return HashingEmbedder(dim=settings.embedding_dim)
    if settings.embedding_api_key.strip():
        return OpenAIEmbedder(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url.rstrip("/"),
            model=settings.embedding_model,
            dim=settings.embedding_dim,
        )
    if settings.zhipuai_api_key.strip():
        return OpenAIEmbedder(
            api_key=settings.zhipuai_api_key,
            base_url=settings.zhipuai_base_url.rstrip("/"),
            model=settings.zhipuai_model,
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

    def list_project(self, project_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self._rows if r.get("project_id") == project_id]

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
        from pymilvus import MilvusClient

        self._client = MilvusClient(uri=uri, user=user, password=password)
        self._collection = collection
        self._dim = dim
        if not self._client.has_collection(collection):
            self._create_collection(dim)
        elif self._existing_dim() != dim:
            # 集合维度与当前嵌入维度不一致（换过嵌入模型）时自愈：删除重建。
            self._client.drop_collection(collection)
            self._create_collection(dim)

    def _existing_dim(self) -> int | None:
        """读取集合里向量字段的维度；读不到时返回 None。

        注意：pymilvus 3.x 里 str(DataType.FLOAT_VECTOR) 返回数字 "101"，
        必须用 DataType(...).name 拿枚举名来识别向量字段。
        """
        from pymilvus import DataType

        try:
            desc = self._client.describe_collection(self._collection)
            for field in desc.get("fields", []):
                ftype = field.get("type")
                if isinstance(ftype, str):
                    name = ftype.lower()
                else:
                    try:
                        name = DataType(ftype).name.lower()
                    except Exception:  # noqa: BLE001
                        name = str(ftype).lower()
                if name.endswith("_vector") or "vector" in name:
                    params = field.get("params") or {}
                    return int(params.get("dim") or 0)
        except Exception:  # noqa: BLE001
            return None
        return None

    def _create_collection(self, dim: int) -> None:
        self._client.create_collection(
            collection_name=self._collection,
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
                "kind": str(r.get("kind") or "source"),
                "source": str(r.get("source") or ""),
                "chapter": str(r.get("chapter") or ""),
                "char_offset": int(r.get("char_offset") or 0),
                "doc_id": str(r.get("doc_id") or ""),
                "keywords": ",".join(r.get("keywords") or []) if isinstance(r.get("keywords"), list) else str(r.get("keywords") or ""),
            }
            for r in rows
        ]
        self._client.upsert(collection_name=self._collection, data=data)

    def delete_project(self, project_id: str) -> None:
        self._client.delete(
            collection_name=self._collection,
            filter=f'project_id == "{project_id}"',
        )

    def list_project(self, project_id: str) -> list[dict[str, Any]]:
        try:
            res = self._client.query(
                collection_name=self._collection,
                filter=f'project_id == "{project_id}"',
                output_fields=["text", "project_id", "chapter_index", "kind", "source", "chapter", "char_offset", "doc_id", "keywords"],
                limit=10000,  # pymilvus query 默认 limit 较小，需显式放大以免截断
            )
            return [
                {
                    "text": str(e.get("text") or ""),
                    "project_id": str(e.get("project_id") or ""),
                    "chapter_index": int(e.get("chapter_index") or 0),
                    "kind": str(e.get("kind") or "source"),
                    "source": str(e.get("source") or ""),
                    "chapter": str(e.get("chapter") or ""),
                    "char_offset": int(e.get("char_offset") or 0),
                    "doc_id": str(e.get("doc_id") or ""),
                    "keywords": str(e.get("keywords") or ""),
                }
                for e in (res or [])
            ]
        except Exception:  # noqa: BLE001
            return []

    def reset(self) -> None:
        self._client.drop_collection(self._collection)

    def search(self, query_vec: list[float], *, project_id: str, k: int = 4) -> list[dict[str, Any]]:
        res = self._client.search(
            collection_name=self._collection,
            data=[query_vec],
            limit=k,
            output_fields=["text", "project_id", "chapter_index", "kind", "source", "chapter", "char_offset", "doc_id", "keywords"],
            filter=f'project_id == "{project_id}"',
        )
        hits: list[dict[str, Any]] = []
        for item in res[0] if res else []:
            entity = item.get("entity") or item  # pymilvus 返回可能是 dict 或对象
            text = entity.get("text") if isinstance(entity, dict) else getattr(entity, "text", "")
            hits.append(
                {
                    "text": text,
                    "score": item.get("distance", 0.0),
                    "kind": entity.get("kind") if isinstance(entity, dict) else getattr(entity, "kind", "source"),
                    "source": entity.get("source") if isinstance(entity, dict) else getattr(entity, "source", ""),
                    "chapter": entity.get("chapter") if isinstance(entity, dict) else getattr(entity, "chapter", ""),
                    "char_offset": entity.get("char_offset") if isinstance(entity, dict) else getattr(entity, "char_offset", 0),
                    "doc_id": entity.get("doc_id") if isinstance(entity, dict) else getattr(entity, "doc_id", ""),
                    "keywords": entity.get("keywords") if isinstance(entity, dict) else getattr(entity, "keywords", ""),
                }
            )
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
        # 探测服务器可用性（零向量的 cosine 无定义，Milvus 会拒绝，必须用非零向量）。
        probe = [1.0] + [0.0] * (embedder.dim - 1)
        store.search(probe, project_id="__probe__", k=1)
        return store
    except Exception as e:  # noqa: BLE001
        # 降级必须可观测：否则用户以为在用 Milvus，实际数据只在内存里、重启即丢。
        log.warning(
            "Milvus 不可达（%s），RAG 已降级为内存向量后端：索引数据重启即丢，"
            "且 /api/status 会显示 rag.degraded=true",
            e,
        )
        return InMemoryVectorStore()


# ---------- RAG 工具 ----------
#
# 检索质量优化的核心：
#   1. 结构化切片：识别中文章节标题，按句子边界组装语义块（不切断句子），
#      并预计算关键词、章节名、原文偏移；
#   2. 干净嵌入：文档向量只用正文本身，不把标题反复拼进每个向量稀释语义；
#   3. 混合检索：向量召回 + 关键词重叠打分 + 来源加权；
#   4. 重排 + MMR 多样性 + 去重 + 阈值，保证返回「相关且彼此不重复」的片段。


# 中文章节标题模式（第一章 / 第1章 / 序章 / 楔子 / 尾声 / 番外 / Chapter 1 …）。
_CHAPTER_RE = re.compile(
    r"^\s*(第[零一二三四五六七八九十百千万0-9]+[章节卷回部集]|"
    r"Chapter\s*\d+|序章|楔子|尾声|番外|引子|后记|前言)[^\n]{0,30}$"
)

# 句子边界（中文标点 + 换行）。
_SENT_RE = re.compile(r"[^。！？!?；;…]+[。！？!?；;…]*")

# 常见虚字 / 停用字（用于关键词提取时过滤无意义 n-gram）。
_STOP_CHARS = set(
    "的了是在我你他她它们这那和与就都也不很把被对为从向到着过之其而或且但若如因所及"
    "吗呢啊哦吧呀么什怎怎什么要会能可有个没很"
    "一二三四五六七八九十百千万"
)


@dataclass
class Chunk:
    """一个结构化的原文切片（语义完整、可追溯）。"""

    text: str
    chapter: str = ""            # 所属章节标题
    chapter_index: int = 0       # 章节序号
    start: int = 0               # 原文字符偏移
    keywords: list[str] = field(default_factory=list)


def _char_ngrams(text: str, n: int = 2) -> set[str]:
    """字符 n-gram 特征（中文无空格，用字符 n-gram 近似关键词）。"""
    t = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", str(text or "").lower())
    grams: set[str] = set()
    for i in range(len(t) - n + 1):
        g = t[i : i + n]
        if all(c in _STOP_CHARS for c in g):
            continue
        grams.add(g)
    return grams


def _extract_keywords(text: str, top: int = 12) -> list[str]:
    """按频率提取字符 2-gram 关键词（离线、无需分词器）。"""
    t = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", str(text or ""))
    counts: Counter[str] = Counter()
    for i in range(len(t) - 1):
        g = t[i : i + 2]
        if all(c in _STOP_CHARS for c in g):
            continue
        counts[g] += 1
    return [g for g, _ in counts.most_common(top)]


def _split_sentences(line: str) -> list[str]:
    parts = [p.strip() for p in _SENT_RE.findall(line or "") if p.strip()]
    return parts or ([line.strip()] if line.strip() else [])


def _make_chunk(sents: list[str], chapter: str, chapter_index: int, start: int) -> Chunk:
    text = "".join(sents).strip()
    return Chunk(text=text, chapter=chapter, chapter_index=chapter_index, start=start, keywords=_extract_keywords(text))


def split_chunks(
    text: str,
    *,
    target_size: int = 500,
    max_size: int = 800,
    overlap_sentences: int = 1,
) -> list[Chunk]:
    """结构化切片：章节感知 + 句子边界 + 语义完整。

    推理：中文脚本/小说的自然语义单元是「章节 -> 段落 -> 句子」。
    固定字符数切片会切断句子、拆散一个场景，检索回来的片段残缺。
    这里先按章节标题分段，再按句子组装成 ~target_size 的块（不切断句子），
    相邻块重叠 overlap_sentences 句，保证跨块语义连贯。
    """
    if not text:
        return []
    # 1) 章节分段：识别标题行，把后续内容归到该章节。
    segments: list[tuple[str, int, list[str]]] = []
    cur_chapter, cur_ci, cur_sents = "", 0, []

    def _flush() -> None:
        nonlocal cur_sents
        if cur_sents:
            segments.append((cur_chapter, cur_ci, cur_sents))
            cur_sents = []

    for line in text.split("\n"):
        stripped = line.strip()
        if _CHAPTER_RE.match(stripped) and len(stripped) <= 40:
            _flush()
            cur_chapter = stripped
            cur_ci += 1
            continue
        cur_sents.extend(_split_sentences(line))
    _flush()

    # 2) 章节内按句子组装语义块。
    chunks: list[Chunk] = []
    offset = 0
    for chap, ci, sents in segments:
        buf: list[str] = []
        buf_len = 0
        for sent in sents:
            buf.append(sent)
            buf_len += len(sent)
            # 达到目标长度且不止一句时收口；单句超长才允许超出。
            if buf_len >= target_size and len(buf) >= 2:
                chunks.append(_make_chunk(buf, chap, ci, offset))
                offset += buf_len
                keep = buf[-overlap_sentences:] if overlap_sentences > 0 else []
                buf = keep[:]
                buf_len = sum(len(s) for s in buf)
            elif buf_len >= max_size:
                chunks.append(_make_chunk(buf, chap, ci, offset))
                offset += buf_len
                keep = buf[-overlap_sentences:] if overlap_sentences > 0 else []
                buf = keep[:]
                buf_len = sum(len(s) for s in buf)
        if buf:
            chunks.append(_make_chunk(buf, chap, ci, offset))
            offset += buf_len
    return chunks


def chunk_text(text: str, *, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    """兼容旧接口：返回纯文本块列表（内部走结构化切片）。"""
    target = max(200, chunk_size - overlap) if chunk_size > 200 else 400
    return [c.text for c in split_chunks(text, target_size=target, max_size=chunk_size, overlap_sentences=1)]


def _text_fingerprint(text: str) -> str:
    return hashlib.md5(str(text or "").encode("utf-8")).hexdigest()[:16]


def _text_sim(a: dict[str, Any], b: dict[str, Any]) -> float:
    """文本级相似度（字符 2-gram Jaccard），用于 MMR 多样性项。"""
    ga = _char_ngrams(str(a.get("text") or ""))
    gb = _char_ngrams(str(b.get("text") or ""))
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def _keyword_overlap(query_grams: set[str], hit: dict[str, Any]) -> float:
    """查询关键词与命中片段关键词的重叠比例（0~1）。"""
    kws = hit.get("keywords")
    if isinstance(kws, list):
        kg = set(kws)
    else:
        kg = {x for x in str(kws or "").split(",") if x}
    if not kg:
        kg = _char_ngrams(str(hit.get("text") or ""))
    if not query_grams or not kg:
        return 0.0
    return len(query_grams & kg) / len(query_grams)


def _query_coverage(query_grams: set[str], hit: dict[str, Any]) -> float:
    """查询字符 n-gram 在命中片段正文里的覆盖比例（0~1）。

    与 _keyword_overlap 的区别：后者只比较「预计算关键词」，当查询词不在
    文档关键词表里时 boost 为 0；这里直接对比查询 n-gram 与正文，作为更
    可靠的词汇信号，并与语义分互补，构成真正的「混合检索」。
    """
    if not query_grams:
        return 0.0
    text = str(hit.get("text") or "")
    hit_grams = _char_ngrams(text)
    if not hit_grams:
        return 0.0
    return len(query_grams & hit_grams) / len(query_grams)


def hybrid_retrieve(
    vector: VectorStore,
    embedder: Embedder,
    *,
    project_id: str,
    query: str,
    k: int = 4,
    kinds: list[str] | None = None,
    context: str | None = None,
    diversity: float = 0.3,
    candidate_mult: int = 5,
) -> list[dict[str, Any]]:
    """混合检索：向量召回 -> 关键词加权 -> 归一化重排 -> MMR 多样性 -> 去重。

    返回结构化命中（text/kind/source/chapter/char_offset/score/keywords）。
    """
    if not query:
        return []
    try:
        q_text = f"{query}\n{context}" if context else query
        vec = embedder.embed([q_text])[0]
        cand_k = max(k * candidate_mult, k + 8, 12)
        hits = vector.search(vec, project_id=project_id, k=cand_k)
    except Exception:  # noqa: BLE001
        return []

    if kinds:
        wanted = set(kinds)
        hits = [h for h in hits if str(h.get("kind") or "") in wanted]

    if not hits:
        return []

    # 语义分 min-max 归一化（hashing 等低分场景下用相对分更稳）。
    scores = [float(h.get("score") or 0.0) for h in hits]
    lo, hi = min(scores), max(scores)
    span = (hi - lo) or 1.0
    query_grams = _char_ngrams(query)

    for h in hits:
        raw = float(h.get("score") or 0.0)
        sem = (raw - lo) / span
        kw = _keyword_overlap(query_grams, h)
        cov = _query_coverage(query_grams, h)
        # 用户显式记忆（source=user）优先于种子知识。
        src_boost = 0.05 if str(h.get("source") or "").startswith("user") else 0.0
        h["_sem"] = sem
        h["_kw"] = kw
        h["_cov"] = cov
        # 混合检索：语义 0.6 + 预计算关键词 0.25 + 查询正文覆盖 0.15 + 来源加权。
        h["_final"] = 0.6 * sem + 0.25 * kw + 0.15 * cov + src_boost
        # 噪声门控只对「候选充足」的场景有意义；按 kind 过滤后的项目知识可能
        # 只剩一两条，属于定向取知识而非相关度竞争，召回优先，不做门控。
        # 阈值说明：哈希嵌入对完全无关文本也有 ~0.1 的碰撞底噪，取 0.15；
        # 关键词 / 覆盖任一非零即视为有词汇关联，不判噪声。
        h["_weak"] = raw < 0.15 and kw < 0.05 and cov < 0.05

    hits.sort(key=lambda h: h["_final"], reverse=True)

    # 去重（文本指纹）+ 低相关过滤。min-max 归一化后最高分的相对 sem 恒为 1.0，
    # 单看 _final 区分不了「矮子里拔将军」，所以候选充足时叠加绝对信号门控：
    # 三路绝对信号（原始语义分 / 预计算关键词 / 正文覆盖）全弱即视为噪声丢弃；
    # 全部候选都弱时宁可返回空，也不把不相关内容当作「高相关」喂给模型。
    few_candidates = len(hits) <= k
    seen: set[str] = set()
    dedup: list[dict[str, Any]] = []
    for h in hits:
        if not few_candidates and (h["_weak"] or h["_final"] < 0.08):
            continue
        fp = _text_fingerprint(str(h.get("text") or ""))
        if fp in seen:
            continue
        seen.add(fp)
        dedup.append(h)

    # MMR：在「相关度」与「多样性」之间折中，避免返回同一走向的重复表述。
    selected: list[dict[str, Any]] = []
    pool = dedup[:]
    while pool and len(selected) < k:
        best, best_val = None, -1.0
        for h in pool:
            div = max((_text_sim(h, s) for s in selected), default=0.0)
            val = (1.0 - diversity) * h["_final"] - diversity * div
            if val > best_val:
                best_val, best = val, h
        if best is None:
            break
        selected.append(best)
        pool.remove(best)

    out: list[dict[str, Any]] = []
    for h in selected:
        out.append(
            {
                "text": str(h.get("text") or ""),
                "kind": str(h.get("kind") or "source"),
                "source": str(h.get("source") or ""),
                "chapter": str(h.get("chapter") or ""),
                "char_offset": int(h.get("char_offset") or 0),
                "keywords": h.get("keywords") or [],
                "score": round(h["_final"], 4),
            }
        )
    return out


def index_project(
    vector: VectorStore,
    embedder: Embedder,
    *,
    project_id: str,
    raw_text: str,
    title: str,
    kind: str = "source",
) -> int:
    """把一个项目的原始文本结构化切块、干净嵌入并写入向量库。返回写入的块数。

    优化：向量只用正文本身（不再把标题拼进每个块稀释语义）；
    标题/章节/偏移/关键词作为元数据保存，供检索与前端定位。
    """
    chunks = split_chunks(raw_text or "")
    if not chunks:
        return 0
    # 干净嵌入：纯正文（标题等元数据不进向量）。
    vectors = embedder.embed([c.text for c in chunks])
    rows = [
        {
            "id": f"{project_id}_{i:04d}",
            "vector": vectors[i],
            "text": chunks[i].text,
            "project_id": project_id,
            "chapter_index": chunks[i].chapter_index,
            "chapter": chunks[i].chapter,
            "char_offset": chunks[i].start,
            "kind": kind,
            "source": "raw_text",
            "doc_id": f"{project_id}:{kind}:{i}",
            "keywords": chunks[i].keywords,
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
    """按查询检索最相关的原文片段（混合检索，返回纯文本）。"""
    hits = hybrid_retrieve(vector, embedder, project_id=project_id, query=query, k=k)
    return [str(h.get("text") or "") for h in hits if str(h.get("text") or "")]
