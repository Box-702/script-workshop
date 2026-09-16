# =====================================================================
# main.py —— FastAPI 应用入口
#
# 职责：
#   - 挂载 REST 路由（/api/*）；
#   - 在根路径托管 Vue 前端构建产物（frontend/dist），用于演示「导入->生成->Agent->审阅」；
#   - 允许跨域（供前端调试）。
# =====================================================================

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .api import router as api_router
from .config import apply_langsmith_env, get_settings

# 站点目录：前端由 frontend/ 的 Vue 工程构建（frontend/dist），
# FastAPI 直接托管构建产物（API 与 Web 页面同源）。
_ROOT_DIR = Path(__file__).resolve().parent.parent
_DIST_DIR = _ROOT_DIR / "frontend" / "dist"


def _wire_video_job_writeback() -> None:
    """把视频队列的状态变化写回数据库。

    队列（VideoJobManager）只维护内存状态，而前端轮询的是 DB 里的
    video_jobs 表；启动时挂上这个回调，任务进度才能被 API 看到。
    """
    from datetime import UTC, datetime

    from .deps import store as get_store
    from .deps import video_manager

    status_map = {
        "pending": "pending",
        "submitting": "pending",
        "queued": "queued",
        "generating": "generating",
        "succeeded": "succeeded",
        "failed": "failed",
        "timeout": "failed",
        "cancelled": "cancelled",
    }

    def _writeback(job_id: str, info: dict[str, Any]) -> None:
        fields: dict[str, Any] = {"status": status_map.get(str(info.get("status")), "pending")}
        if info.get("external_task_id"):
            fields["external_task_id"] = info["external_task_id"]
        if info.get("video_url"):
            fields["video_url"] = info["video_url"]
        if info.get("error"):
            fields["error_message"] = str(info["error"])
        if info.get("finished_at"):
            fields["finished_at"] = datetime.now(UTC)
        try:
            get_store().update_video_job(job_id, **fields)
        except Exception:  # noqa: BLE001
            pass

    video_manager().on_complete(_writeback)


def create_app() -> FastAPI:
    settings = get_settings()
    # 启动时注入 LangSmith 监控环境变量（LANGSMITH_* -> LANGCHAIN_*）。
    apply_langsmith_env(settings)
    _wire_video_job_writeback()
    app = FastAPI(
        title="剧本工坊（Script Workshop）",
        version="0.3.0",
        description="小说 → 剧本 → AI 短剧 全链路 Agent 工作台",
    )

    # 开发环境 CORS（前端可能用不同端口）。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    # Vue 构建产物里的静态资源（js/css 等），存在才挂载。
    if (_DIST_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=_DIST_DIR / "assets"), name="assets")

    @app.get("/", response_class=HTMLResponse)
    def home() -> HTMLResponse:
        # 托管 Vue 构建产物（frontend/dist）；未构建时给出提示。
        index = _DIST_DIR / "index.html"
        if index.exists():
            return HTMLResponse(index.read_text(encoding="utf-8"))
        return HTMLResponse(
            "<h1>剧本智能体</h1>"
            "<p>前端未构建。请先在 <code>frontend/</code> 目录运行 "
            "<code>npm run build</code>，或访问 <a href=\"/docs\">/docs</a> 查看 API。</p>"
        )

    return app


app = create_app()
