# =====================================================================
# api —— REST 路由包
#
# 拆分原则：按业务域分文件，全部挂在同一个 `/api` 前缀下，路由声明
# 与拆分前完全一致（顺序无关，路径无冲突）。
#
#   system.py      运行状态 / 子代理任务 / 工作目录
#   projects.py    项目生命周期、初稿生成、导入、落盘、笔记、文件浏览
#   versions.py    剧本版本（含导出）
#   agent_runs.py  改编智能体的运行与审阅
#   chat.py        对话式 Agent 与会话管理
#   video.py       Provider / 模型偏好 / 视频版本 / 生成任务
#   plugins.py     插件管理
#
#   common.py      共享的序列化与落盘辅助
#   schemas.py     请求模型
#   deps.py        依赖入口（测试可整体替换）
# =====================================================================

from __future__ import annotations

from fastapi import APIRouter

from . import agent_runs, chat, plugins, projects, system, versions, video

router = APIRouter(prefix="/api")

for _sub in (system, projects, versions, agent_runs, chat, video, plugins):
    router.include_router(_sub.router)

__all__ = ["router"]
