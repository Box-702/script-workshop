# =====================================================================
# config.py —— 全局配置
#
# 用 pydantic-settings 从环境变量 / .env 读取运行参数，集中在一处，
# 便于 Docker 与本地保持一致。
#
# 技术选型说明：
#   - DATABASE_URL：业务数据（项目 / 版本 / Agent 运行记录）默认用 Postgres，
#     这是生产级选择；本地开发 / 测试也可换成 SQLite（见 store.py）。
#   - CHECKPOINTER：LangGraph 图执行状态的 checkpointer。postgres 用
#     langgraph-checkpoint-postgres（跨请求 / 跨重启恢复审阅中的图）；
#     memory 用进程内 InMemorySaver（无需额外服务，便于离线调试）。
#   - MILVUS_* / EMBEDDING_*：可选的向量检索（RAG）。Milvus 可达时给 Agent
#     "检索原文"能力；不可达或未配置模型时自动退化为内存/明文回退。
# =====================================================================

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录：langgraph-rebuild/，与 .env、docker-compose.yml 同级。
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """运行配置。所有字段均可被环境变量覆盖（大小写不敏感）。"""

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env") if (_PROJECT_ROOT / ".env").exists() else ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- 业务数据库（Postgres，可回退 SQLite） ----------
    database_url: str = Field(
        default="postgresql+psycopg://script:script@localhost:5432/script_agent",
        alias="DATABASE_URL",
    )

    # ---------- LangGraph checkpointer ----------
    checkpointer: str = Field(default="memory", alias="CHECKPOINTER")  # memory | postgres
    # checkpoint 专用 DSN；留空则复用 DATABASE_URL。
    checkpoint_dsn: str = Field(default="", alias="CHECKPOINT_DSN")

    # ---------- 可选向量检索（RAG） ----------
    # Milvus 服务地址。不可达时会自动退化为内存向量搜索。
    milvus_uri: str = Field(default="http://localhost:19530", alias="MILVUS_URI")
    milvus_collection: str = Field(default="script_chunks", alias="MILVUS_COLLECTION")
    milvus_user: str = Field(default="", alias="MILVUS_USER")
    milvus_password: str = Field(default="", alias="MILVUS_PASSWORD")
    # 是否启用向量检索；false 时 retrieve_source 工具走明文/最近片段回退。
    enable_rag: bool = Field(default=False, alias="ENABLE_RAG")

    # ---------- 向量嵌入 ----------
    # openai | hashing。openai 需要 EMBEDDING_API_KEY；hashing 离线确定性向量。
    embedding_provider: str = Field(default="hashing", alias="EMBEDDING_PROVIDER")
    embedding_api_key: str = Field(default="", alias="EMBEDDING_API_KEY")
    embedding_base_url: str = Field(default="https://api.openai.com/v1", alias="EMBEDDING_BASE_URL")
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    embedding_dim: int = Field(default=768, alias="EMBEDDING_DIM")

    # ---------- 模型服务（OpenAI 兼容） ----------
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    output_language: str = Field(default="zh-CN", alias="OUTPUT_LANGUAGE")

    # ---------- 服务 ----------
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    @property
    def model_available(self) -> bool:
        """是否配置了有效的对话模型 key。没有 key 时走本地规则回退。"""
        return bool(self.openai_api_key.strip())

    @property
    def effective_checkpoint_dsn(self) -> str:
        """checkpointer 用的 DSN：优先专用值，否则复用业务库。"""
        return self.checkpoint_dsn.strip() or self.database_url


@lru_cache
def get_settings() -> Settings:
    """缓存的配置单例。"""
    return Settings()
