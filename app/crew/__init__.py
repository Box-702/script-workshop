# =====================================================================
# crew —— 剧组 Agent 系统
#
# 模仿真实剧组分工，当前在用的三个 Agent 角色：
#   - 导演 (Director)：场景拆解为镜头（分镜 = 连贯动作单元 / 连贯对话单元）
#   - 美术指导 (ArtDirector)：视觉风格指南 —— 角色造型与环境描述的唯一来源
#   - 摄影指导 (DP)：把剧本 + 镜头方案 + 风格锚构建成模型感知的视频提示词
#
# 每个 Agent 接收 LLM + 领域数据，输出结构化的领域对象。
# 成片拼接由 app/video/assemble.py（FFmpeg）负责，不属于 Agent。
# =====================================================================

from .art_director import run_art_director
from .base import CrewAgent, CrewTaskResult
from .director import run_director
from .dp import run_dp

__all__ = [
    "CrewAgent",
    "CrewTaskResult",
    "run_director",
    "run_dp",
    "run_art_director",
]
