# =====================================================================
# config.py —— 全局配置
#
# 用 pydantic-settings 从环境变量 / .env 读取运行参数，集中在一处，
# 便于 Docker 与本地保持一致。
#
# 支持的模型/服务接入（全部可选，缺 key 自动走本地回退）：
#   - 对话模型：OPENAI_*（OpenAI 兼容）或 DEEPSEEK_*（DeepSeek 原生）；
#   - 嵌入模型：EMBEDDING_*（OpenAI 兼容）或 ZHIPUAI_*（智谱 embedding-3）；
#   - 监控：LANGSMITH_*（启动时映射为 LangChain 的 LANGCHAIN_* 环境变量）；
#   - 检索：MILVUS_*（可选 RAG，不可达时退化为内存向量）。
# =====================================================================

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（仓库根），与 .env、docker-compose.yml 同级。
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
    checkpoint_dsn: str = Field(default="", alias="CHECKPOINT_DSN")

    # ---------- 对话模型（OpenAI 兼容 或 DeepSeek） ----------
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")
    deepseek_model: str = Field(default="deepseek-chat", alias="DEEPSEEK_MODEL_NAME")
    # DeepSeek V3.x/V4 深度思考开关：默认关闭（thinking disabled），
    # 单次调用可从 ~50s 降到 ~10s。需要更深度推理时可设 true。
    deepseek_thinking: bool = Field(default=False, alias="DEEPSEEK_THINKING")

    # ---------- 可选第三方服务 ----------
    zhipuai_api_key: str = Field(default="", alias="ZHIPUAI_API_KEY")
    zhipuai_base_url: str = Field(default="https://open.bigmodel.cn/api/paas/v4/", alias="ZHIPUAI_BASE_URL")
    zhipuai_model: str = Field(default="embedding-3", alias="ZHIPUAI_MODEL_NAME")
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    # LangSmith 监控：开启后 LangGraph / LLM 运行轨迹自动上报。
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")
    langsmith_endpoint: str = Field(default="https://api.smith.langchain.com", alias="LANGSMITH_ENDPOINT")
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="", alias="LANGSMITH_PROJECT")

    # ---------- 可选向量检索（RAG） ----------
    milvus_uri: str = Field(default="http://localhost:19530", alias="MILVUS_URI")
    milvus_collection: str = Field(default="script_chunks", alias="MILVUS_COLLECTION")
    milvus_user: str = Field(default="", alias="MILVUS_USER")
    milvus_password: str = Field(default="", alias="MILVUS_PASSWORD")
    enable_rag: bool = Field(default=False, alias="ENABLE_RAG")

    # ---------- 向量嵌入 ----------
    # openai | hashing。openai 需要 EMBEDDING_API_KEY（或 ZHIPUAI_API_KEY）。
    embedding_provider: str = Field(default="openai", alias="EMBEDDING_PROVIDER")
    embedding_api_key: str = Field(default="", alias="EMBEDDING_API_KEY")
    embedding_base_url: str = Field(default="https://api.openai.com/v1", alias="EMBEDDING_BASE_URL")
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    embedding_dim: int = Field(default=2048, alias="EMBEDDING_DIM")

    # ---------- 服务 ----------
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    output_language: str = Field(default="zh-CN", alias="OUTPUT_LANGUAGE")

    # 兼容性：.env 中值被引号包裹时自动去引号（常见手写失误）。
    @field_validator("*", mode="before")
    @classmethod
    def _strip_quotes(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in {'"', "'"}:
                v = v[1:-1].strip()
        return v

    @property
    def model_available(self) -> bool:
        """是否配置了有效的对话模型 key（OpenAI 或 DeepSeek）。"""
        return bool(self.openai_api_key.strip() or self.deepseek_api_key.strip())

    @property
    def effective_checkpoint_dsn(self) -> str:
        """checkpointer 用的 DSN：优先专用值，否则复用业务库。"""
        return self.checkpoint_dsn.strip() or self.database_url


def apply_langsmith_env(settings: Settings) -> None:
    """把 .env 里的 LANGSMITH_* 映射成 LangChain 识别的 LANGCHAIN_* 环境变量。

    LangSmith 监控由 LangChain 客户端读取环境变量；在应用启动时注入，
    之后所有 LangGraph / LLM 调用都会自动上报运行轨迹。
    """
    if settings.langsmith_tracing and settings.langsmith_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_TRACING"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_ENDPOINT"] = settings.langsmith_endpoint
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project or "script-agent"


@lru_cache
def get_settings() -> Settings:
    """缓存的配置单例。"""
    return Settings()
