# =====================================================================
# media —— 参考资产流水线（视觉一致性的图像级锚点）
#
# refs.py：定妆 prompt → 文生图 → 视觉质检（不合格重生成）→ 注册为全局参考
# → 回填到每个镜头。图像能力本身来自 app/llm（image.py / vision.py）。
#
# 为什么独立成层：它既不是「生产线」（不产剧本），也不是「视频生成」
# （不提交视频任务），而是两者之间的视觉锚注册环节。
# =====================================================================

from .refs import (
    MAX_REFERENCE_IMAGES,
    apply_reference_images,
    build_reference_assets,
    character_prompt,
    environment_prompt,
)

__all__ = [
    "MAX_REFERENCE_IMAGES",
    "apply_reference_images",
    "build_reference_assets",
    "character_prompt",
    "environment_prompt",
]
