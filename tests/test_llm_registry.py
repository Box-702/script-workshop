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


def test_minimax_chat_uses_same_key_as_video_and_tts():
    """MiniMax：一个 key 同时打通对话 / 视频（H3）/ 配音（T2A）。"""
    cfg = resolve_chat(_settings(CHAT_PROVIDER="minimax", MINIMAX_API_KEY="mm"))
    assert cfg is not None
    assert cfg.provider == "minimax"
    assert cfg.model == "MiniMax-Text-01"
    assert cfg.api_key == "mm"
    assert cfg.base_url.startswith("https://api.minimax.cn")


def test_minimax_declares_no_json_mode():
    """MiniMax 的 /chat/completions 不支持 response_format=json_object。

    实测报 2013 unknown response_format type——所以结构化输出必须走降级路径。
    """
    spec = get_provider_spec("minimax")
    assert spec is not None
    assert spec.supports_json_mode is False
    # 其他厂商不受影响
    assert get_provider_spec("deepseek").supports_json_mode is True
    assert get_provider_spec("zhipu").supports_json_mode is True


def test_structured_falls_back_when_provider_has_no_json_mode():
    """不支持 json_mode 的厂商，structured() 要降级成「提示词 + 容错解析」。"""
    from pydantic import BaseModel

    from app.llm.client import LLM

    class Tiny(BaseModel):
        title: str

    llm = LLM(_settings(CHAT_PROVIDER="minimax", MINIMAX_API_KEY="mm"))
    assert llm.config is not None
    llm.config.provider = "minimax"
    calls: list[list] = []

    class FakeModel:
        def invoke(self, messages, **kwargs):
            calls.append(messages)
            return type("R", (), {"content": '{"title": "夜街"}'})()

    llm._model = FakeModel()  # type: ignore[assignment]
    out = llm.structured(Tiny).invoke([{"role": "user", "content": "给个标题"}])
    assert isinstance(out, Tiny)
    assert out.title == "夜街"
    # 降级路径必须把 JSON 要求追加到消息里
    assert calls, "降级路径应该真的调了一次模型"

    def _text(m) -> str:
        return str(m.get("content", "")) if isinstance(m, dict) else str(getattr(m, "content", ""))

    assert any("JSON" in _text(m) for m in calls[-1])


def test_structured_uses_json_mode_for_normal_providers():
    """普通厂商仍走 json_mode（行为不变）。"""
    from app.llm.client import LLM

    llm = LLM(_settings(CHAT_PROVIDER="deepseek", DEEPSEEK_API_KEY="ds"))
    assert llm._supports_json_mode() is True
