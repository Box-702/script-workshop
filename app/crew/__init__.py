# =====================================================================
# crew —— 剧组 Agent 系统
#
# 模仿真实剧组分工，提供以下 Agent 角色：
#   - 导演 (Director)：创意总控、场景拆解为镜头
#   - 摄影指导 (DP)：镜头设计、运镜、生成视频 Prompt
#   - 美术指导 (ArtDirector)：视觉风格、角色造型指南
#   - 剪辑师 (Editor)：视频片段拼接、成片
#   - 制片人 (Producer)：全局协调、质量把控
#
# 每个 Agent 接收 LLM + 领域数据，输出结构化的领域对象。
# =====================================================================

from .art_director import run_art_director
from .base import CrewAgent, CrewTaskResult
from .director import run_director
from .dp import run_dp
from .editor import run_editor
from .producer import run_producer

__all__ = [
    "CrewAgent",
    "CrewTaskResult",
    "run_director",
    "run_dp",
    "run_art_director",
    "run_editor",
    "run_producer",
]
