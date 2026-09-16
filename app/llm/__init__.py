# =====================================================================
# llm —— 统一大模型接入包
#
# 一个门面 + 一张厂商表，覆盖全部模型能力：
#   client.py   LLM 门面（chat / structured / vision / image）
#   base.py     ModelConfig / ProviderSpec / Modality 数据契约
#   providers.py 各厂商声明（OpenAI 兼容 / DeepSeek / 智谱 / Kimi / Qwen / Ollama）
#   registry.py 配置解析（.env 优先级链 + DB 偏好 → ModelConfig）
#   vision.py   多模态视觉客户端（定妆图质检）
#   image.py    文生图客户端（参考资产）
#
# 上层只写 `from ..llm import LLM`，不感知任何厂商细节。
# =====================================================================

from .base import Modality, ModelConfig, ProviderSpec
from .client import LLM, build_llm
from .image import ImageClient, build_image_client
from .providers import (
    all_provider_specs,
    get_provider_spec,
    register_provider,
)
from .registry import (
    describe_providers,
    resolve_chat,
    resolve_image,
    resolve_vision,
)
from .vision import VisionClient

__all__ = [
    "LLM",
    "build_llm",
    "Modality",
    "ModelConfig",
    "ProviderSpec",
    "ImageClient",
    "VisionClient",
    "build_image_client",
    "get_provider_spec",
    "all_provider_specs",
    "register_provider",
    "resolve_chat",
    "resolve_vision",
    "resolve_image",
    "describe_providers",
]
