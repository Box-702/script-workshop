# =====================================================================
# media —— 成片素材层：资产键解析（assets.py）/ 参考资产（refs.py）/ 配音混音（dubbing.py）
#
# assets.py：把「按名字索引」的老数据与「按实体 id 索引」的新数据统一起来——
# 名字会被用户改，id 不会；存储用 id，拼提示词时再转回名字（见 D-22）。
#
# refs.py：定妆 prompt → 文生图 → 视觉质检（不合格重生成）→ 注册为全局参考
# → 回填到每个镜头。图像能力本身来自 app/llm（image.py / vision.py）。
#
# dubbing.py：台词 TTS（app/llm/tts.py）→ 按镜头归属排时间轴 → ffmpeg 混音。
#
# 为什么独立成层：它既不是「生产线」（不产剧本），也不是「视频生成」
# （不提交视频任务），而是两者之间的视觉锚注册环节。
# =====================================================================

from .assets import (
    build_index,
    lookup,
    normalize_style,
    rekey,
)
from .refs import (
    MAX_REFERENCE_IMAGES,
    apply_reference_images,
    build_reference_assets,
    character_prompt,
    environment_prompt,
)
from .casting import CastMember, Casting, assign_voices, cast_script
from .dubbing import DubbingPlan, dub_video, plan_dubbing

__all__ = [
    "MAX_REFERENCE_IMAGES",
    "CastMember",
    "Casting",
    "DubbingPlan",
    "apply_reference_images",
    "assign_voices",
    "build_index",
    "build_reference_assets",
    "cast_script",
    "character_prompt",
    "dub_video",
    "environment_prompt",
    "lookup",
    "normalize_style",
    "plan_dubbing",
    "rekey",
]
