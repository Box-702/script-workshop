# =====================================================================
# test_llm_registry.py —— 模型接入层的配置解析
#
# 只测「配置 → ModelConfig」这一步（纯逻辑，不触网、不构造真实模型）。
# =====================================================================

from __future__ import annotations

from app.config import Settings
from app.llm import describe_providers, resolve_chat, resolve_image, resolve_vision
from app.llm.providers import build_chat_model, get_provider_spec


def _settings(**overrides: str) -> Settings:
    base = {
        "DATABASE_URL": "sqlite:///./data/_unused.db",
        "CHECKPOINTER": "memory",
        "OPENAI_API_KEY": "",
        "ZHIPUAI_API_KEY": "",
        "DEEPSEEK_API_KEY": "",
        "CHECKPOINT_DSN": "",
        "CHAT_PROVIDER": "",
        "VISION_PROVIDER": "",
        "VISION_API_KEY": "",
        "VISION_MODEL": "",
        "IMAGE_PROVIDER": "",
        "IMAGE_API_KEY": "",
    }
    base.update(overrides)
    return Settings(**base)


def test_no_keys_means_no_chat_config():
    cfg = resolve_chat(_settings())
    assert cfg is None


def test_env_priority_chain_openai_beats_deepseek():
    cfg = resolve_chat(_settings(OPENAI_API_KEY="oa", DEEPSEEK_API_KEY="ds"))
    assert cfg is not None
    assert cfg.provider == "openai"
    assert cfg.source == "env"


def test_deepseek_thinking_becomes_extra_body():
    cfg = resolve_chat(_settings(DEEPSEEK_API_KEY="ds", DEEPSEEK_THINKING="false"))
    assert cfg is not None
    assert cfg.provider == "deepseek"
    assert cfg.extra_body == {"_thinking": False}

    model = build_chat_model(cfg)
    # 关闭思考链必须落到请求体上，否则推理模型会把内容写进 reasoning_content。
    assert model.extra_body == {"thinking": {"type": "disabled"}}


def test_chat_provider_forces_vendor_and_skips_chain():
    # 显式指定 deepseek 时，即使配了 openai key 也应选 deepseek。
    cfg = resolve_chat(_settings(CHAT_PROVIDER="deepseek", OPENAI_API_KEY="oa", DEEPSEEK_API_KEY="ds"))
    assert cfg is not None
    assert cfg.provider == "deepseek"


def test_vision_falls_back_to_a_vision_capable_vendor():
    cfg = resolve_vision(_settings(DEEPSEEK_API_KEY="ds"))
    assert cfg is not None
    assert cfg.provider == "deepseek"
    # 应换成该厂商的视觉模型，而不是复用对话模型
    assert cfg.model == "deepseek-v4-flash-vision-exp"


def test_vision_explicit_key_wins():
    cfg = resolve_vision(_settings(VISION_PROVIDER="zhipu", VISION_API_KEY="vk", VISION_MODEL="glm-4v-flash"))
    assert cfg is not None
    assert cfg.provider == "zhipu"
    assert cfg.model == "glm-4v-flash"
    assert cfg.api_key == "vk"


def test_image_defaults_to_cogview_with_zhipu_key():
    cfg = resolve_image(_settings(ZHIPUAI_API_KEY="zp"))
    assert cfg is not None
    assert cfg.provider == "cogview"
    assert cfg.model == "cogview-3-flash"


def test_image_returns_none_without_capable_key():
    assert resolve_image(_settings(DEEPSEEK_API_KEY="ds")) is None


def test_provider_table_exposes_modalities():
    providers = {p["name"]: p for p in describe_providers()}
    assert "chat" in providers["deepseek"]["modalities"]
    assert "vision" in providers["deepseek"]["modalities"]
    assert "image" in providers["zhipu"]["modalities"]
    # 本地模型不需要 key
    assert get_provider_spec("ollama").requires_key is False
