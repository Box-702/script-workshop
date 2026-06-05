from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")

    llm_model_summary: str = Field(default="", alias="LLM_MODEL_SUMMARY")
    llm_model_bible: str = Field(default="", alias="LLM_MODEL_BIBLE")
    llm_model_scene: str = Field(default="", alias="LLM_MODEL_SCENE")
    llm_model_dialogue: str = Field(default="", alias="LLM_MODEL_DIALOGUE")
    llm_model_repair: str = Field(default="", alias="LLM_MODEL_REPAIR")

    # Storage
    database_url: str = Field(default="sqlite:///./data/scriptforge.db", alias="DATABASE_URL")
    storage_dir: str = Field(default="./storage", alias="STORAGE_DIR")

    # Server
    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_reload: bool = Field(default=True, alias="API_RELOAD")


@lru_cache
def get_settings() -> Settings:
    return Settings()
