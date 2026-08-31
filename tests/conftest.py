# =====================================================================
# conftest.py —— 测试公共夹具
#
# 为了让测试在「没有模型 key、没有 Postgres、没有 Milvus」的机器上也能跑，
# 这里统一用：
#   - SQLite（临时文件）做业务存储；
#   - InMemorySaver 做 LangGraph checkpointer（进程内，支持中断/恢复）；
#   - InMemory 向量后端 + 哈希嵌入（无 Milvus 时的兜底）。
# Docker / 生产路径（Postgres + Milvus）由 docker-compose 与集成说明覆盖。
# =====================================================================

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

# 保证默认走内存 checkpoint，避免测试污染全局单例。
os.environ.setdefault("CHECKPOINTER", "memory")
os.environ.setdefault("ENABLE_RAG", "false")
os.environ.setdefault("EMBEDDING_PROVIDER", "hashing")
os.environ.setdefault("OPENAI_API_KEY", "")

from app.config import Settings  # noqa: E402
from app.llm import LLM  # noqa: E402
from app.store import Store  # noqa: E402
from app.vector import HashingEmbedder, build_vector_store  # noqa: E402


@pytest.fixture()
def tmp_db_path(tmp_path_factory: pytest.TempPathFactory) -> str:
    # 用项目内的 data 目录建临时库，避免沙箱对系统临时目录的写入限制。
    d = Path(__file__).resolve().parent.parent / "data"
    d.mkdir(parents=True, exist_ok=True)
    return (d / f"test_{os.getpid()}_{time.time_ns()}.db").as_posix()


@pytest.fixture()
def settings() -> Settings:
    # 显式控制：内存 checkpoint、无 RAG、无模型 key。
    # 注意：必须用构造函数参数置空（空字符串环境变量会被 pydantic 视为未设置，
    # 无法覆盖 .env 里真实配置的 DEEPSEEK_API_KEY）。
    return Settings(
        DATABASE_URL="sqlite:///./data/_unused.db",
        CHECKPOINTER="memory",
        ENABLE_RAG=False,
        EMBEDDING_PROVIDER="hashing",
        OPENAI_API_KEY="",
        DEEPSEEK_API_KEY="",
        ZHIPUAI_API_KEY="",
        CHECKPOINT_DSN="",
    )


@pytest.fixture()
def store(tmp_db_path) -> Store:
    db_url = f"sqlite:///{tmp_db_path}"
    return Store(db_url)


@pytest.fixture()
def llm(settings) -> LLM:
    return LLM(settings)


@pytest.fixture()
def vector_store(settings):
    embedder = HashingEmbedder(dim=settings.embedding_dim)
    return build_vector_store(settings, embedder)


@pytest.fixture()
def sample_text() -> str:
    return (
        "凌晨三点，滨江路的路灯在雨里像一团化不开的黄。林然把车停在旧楼前，"
        "熄了火，雨水顺着挡风玻璃往下淌。\n"
        "阿姐坐在里头的一把折叠椅上，说：“你终于来了。”林然没答话。\n"
        "角落里站着一个穿红雨衣的男人，把一张照片按在桌上，照片上是失火前夜的"
        "旧货市场。"
    )
