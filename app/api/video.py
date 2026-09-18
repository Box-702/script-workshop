# =====================================================================
# video.py —— 视频制作（Provider / 模型偏好 / 视频版本 / 生成任务）
#
# 覆盖三块：
#   - Provider 配置（LLM / 视频 / 图片的 key 与端点，存 DB）
#   - 模型偏好（为某类任务指定默认 provider + model）
#   - 视频版本快照与生成任务（提交 → 轮询 → 状态回调写回 DB）
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..video.base import default_resolution

from . import common, deps
from .schemas import (
    ModelPreferenceSet,
    ProviderCreate,
    ProviderUpdate,
    VideoJobCreate,
    VideoVersionCreate,
)

log = logging.getLogger(__name__)

router = APIRouter()


# ---------- Provider 管理 ----------


@router.post("/providers")
def create_provider(payload: ProviderCreate) -> dict[str, Any]:
    """添加一个新的 API Provider。"""
    p = deps.store().create_api_provider(
        kind=payload.kind,
        name=payload.name,
        label=payload.label,
        base_url=payload.base_url,
        api_key=payload.api_key,
        config=payload.config,
        enabled=payload.enabled,
    )
    return {"id": p.id, "name": p.name, "label": p.label, "kind": p.kind}


@router.get("/providers")
def list_providers(kind: str | None = None) -> list[dict[str, Any]]:
    """列出所有 API Providers（不返回 key，只给 configured 标记）。"""
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "name": r.name,
            "label": r.label,
            "base_url": r.base_url,
            "configured": bool(r.api_key),
            "enabled": r.enabled,
            "config": r.config,
            "created_at": r.created_at.isoformat(),
        }
        for r in deps.store().list_api_providers(kind=kind)
    ]


@router.get("/providers/{provider_id}")
def get_provider(provider_id: str) -> dict[str, Any]:
    """获取 Provider 详情。"""
    p = deps.store().get_api_provider(provider_id)
    if not p:
        raise HTTPException(404, "Provider 不存在")
    return {
        "id": p.id,
        "kind": p.kind,
        "name": p.name,
        "label": p.label,
        "base_url": p.base_url,
        "configured": bool(p.api_key),
        "enabled": p.enabled,
        "config": p.config,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


@router.patch("/providers/{provider_id}")
def update_provider(provider_id: str, payload: ProviderUpdate) -> dict[str, Any]:
    """更新 Provider 配置。"""
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    p = deps.store().update_api_provider(provider_id, **fields)
    if not p:
        raise HTTPException(404, "Provider 不存在")
    return {"id": p.id, "ok": True}


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: str) -> dict[str, Any]:
    """删除 Provider。"""
    if not deps.store().delete_api_provider(provider_id):
        raise HTTPException(404, "Provider 不存在")
    return {"ok": True}


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: str) -> dict[str, Any]:
    """测试 Provider 连接（校验 key 是否已配置、Provider 名是否可解析）。"""
    p = deps.store().get_api_provider(provider_id)
    if not p:
        raise HTTPException(404, "Provider 不存在")
    if p.kind == "video":
        from ..video import get_registry

        provider = get_registry().get_provider(p.name, api_key=p.api_key, base_url=p.base_url)
        if not provider:
            return {"ok": False, "error": f"未找到视频 Provider: {p.name}"}
        return {"ok": bool(p.api_key), "provider": p.name, "label": provider.label}
    if not p.api_key:
        return {"ok": False, "error": "未配置 API Key"}
    return {"ok": True, "provider": p.name, "label": p.label}


# ---------- 模型偏好 ----------


@router.get("/models/preferences")
def list_preferences() -> list[dict[str, Any]]:
    """列出所有模型偏好设置。"""
    return [
        {
            "id": p.id,
            "task_type": p.task_type,
            "provider_id": p.provider_id,
            "model_name": p.model_name,
            "params": p.params,
            "is_default": p.is_default,
        }
        for p in deps.store().list_model_preferences()
    ]


@router.put("/models/preferences")
def set_preference(payload: ModelPreferenceSet) -> dict[str, Any]:
    """设置模型偏好。"""
    pref = deps.store().set_model_preference(
        task_type=payload.task_type,
        provider_id=payload.provider_id,
        model_name=payload.model_name,
        params=payload.params,
        is_default=payload.is_default,
    )
    return {"id": pref.id, "task_type": pref.task_type, "ok": True}


@router.get("/models/available")
def available_models() -> dict[str, Any]:
    """列出所有可用的模型 Provider（按 kind 分组）。"""
    llm_providers: list[dict[str, Any]] = []
    video_providers: list[dict[str, Any]] = []
    for p in deps.store().list_api_providers():
        info = {
            "id": p.id,
            "name": p.name,
            "label": p.label,
            "configured": bool(p.api_key),
            "enabled": p.enabled,
        }
        if p.kind == "llm":
            llm_providers.append(info)
        elif p.kind == "video":
            video_providers.append(info)
    return {"llm": llm_providers, "video": video_providers}


# ---------- 视频版本 ----------


@router.post("/projects/{project_id}/video-versions")
def create_video_version(project_id: str, payload: VideoVersionCreate) -> dict[str, Any]:
    """创建视频版本快照。"""
    common.get_project(project_id)
    v = deps.store().create_video_version(
        project_id=project_id,
        shots=payload.shots,
        style_guide=payload.style_guide,
        source_type=payload.source_type,
        label=payload.label,
        notes=payload.notes,
        parent_version_id=payload.parent_version_id,
    )
    return {"id": v.id, "project_id": project_id, "created_at": v.created_at.isoformat()}


@router.get("/projects/{project_id}/video-versions")
def list_video_versions(project_id: str) -> list[dict[str, Any]]:
    """列出项目的所有视频版本。"""
    common.get_project(project_id)
    return [
        {
            "id": v.id,
            "parent_version_id": v.parent_version_id,
            "source_type": v.source_type,
            "label": v.label,
            "notes": v.notes,
            "milestone": v.milestone,
            "shot_count": len(v.shots),
            "created_at": v.created_at.isoformat(),
        }
        for v in deps.store().list_video_versions(project_id)
    ]


@router.get("/video-versions/{version_id}")
def get_video_version(version_id: str) -> dict[str, Any]:
    """获取视频版本详情（含完整镜头数据）。"""
    v = deps.store().get_video_version(version_id)
    if not v:
        raise HTTPException(404, "视频版本不存在")
    return {
        "id": v.id,
        "project_id": v.project_id,
        "parent_version_id": v.parent_version_id,
        "source_type": v.source_type,
        "label": v.label,
        "notes": v.notes,
        "milestone": v.milestone,
        "shots": v.shots,
        "style_guide": v.style_guide,
        "created_at": v.created_at.isoformat(),
    }


@router.post("/video-versions/{version_id}/milestone")
def set_video_milestone(version_id: str, milestone: str | None = None) -> dict[str, Any]:
    """设置视频版本里程碑。"""
    v = deps.store().set_video_version_milestone(version_id, milestone)
    if not v:
        raise HTTPException(404, "视频版本不存在")
    return {"id": v.id, "milestone": v.milestone}


# ---------- 视频生成任务 ----------


def _job_params(payload: dict[str, Any]) -> Any:
    """把落库的 params 映射成 Provider 统一入参（多余键进 extra）。"""
    from ..video.base import VideoJobParams

    # 这些键有专门的归处：既不要重复塞进 extra，也不要当作未知字段透传给 provider。
    handled_keys = {
        "duration_sec", "resolution", "ratio", "aspect_ratio", "fps", "seed", "negative_prompt",
        "first_frame_image", "last_frame_image",
        "reference_images", "reference_videos", "reference_audios", "content",
    }
    return VideoJobParams(
        duration_sec=int(payload.get("duration_sec") or 6),
        resolution=str(payload.get("resolution") or "1280x720"),
        aspect_ratio=str(payload.get("ratio") or payload.get("aspect_ratio") or "16:9"),
        fps=int(payload.get("fps") or 24),
        seed=payload.get("seed"),
        negative_prompt=payload.get("negative_prompt"),
        image_url=payload.get("first_frame_image"),
        last_frame_image=payload.get("last_frame_image"),
        reference_images=payload.get("reference_images") or [],
        reference_videos=payload.get("reference_videos") or [],
        reference_audios=payload.get("reference_audios") or [],
        content=payload.get("content"),
        extra={k: v for k, v in payload.items() if k not in handled_keys},
    )


def _resolve_video_provider(name: str) -> Any:
    """按 DB 配置解析视频 Provider 实例（缺省回落到环境变量）。"""
    from ..video import get_registry

    row = next(
        (r for r in deps.store().list_api_providers(kind="video") if r.name == name),
        None,
    )
    kwargs = {"api_key": row.api_key, "base_url": row.base_url} if row else {}
    return get_registry().get_provider(name, **kwargs)


def _submit_video_job(job: Any) -> None:
    """把数据库里的视频任务真正投递到异步生成队列（提交 → 轮询 → 回调写回）。"""
    provider = _resolve_video_provider(job.provider)
    if provider is None:
        raise HTTPException(400, f"未找到视频 Provider: {job.provider}")

    deps.video_manager().submit(job.id, provider, job.prompt, _job_params(dict(job.params or {})))


def _create_and_submit_job(project_id: str, payload: VideoJobCreate) -> Any:
    """创建视频任务并投递（单镜提交与批量批次共用的入口）。

    含提交时自动锚回填（定妆图 + 前镜成片接力）与默认分辨率策略：
    payload.params 未显式带 resolution 时落全局默认（VIDEO_DEFAULT_RESOLUTION）。
    """
    from ..video import get_registry

    provider = get_registry().get_provider(payload.provider)
    duration = int(payload.params.get("duration_sec") or 6)
    cost = provider.estimate_cost(float(duration)) if provider else None

    stored_params = dict(payload.params)
    stored_params.setdefault("resolution", default_resolution())
    for key in ("first_frame_image", "last_frame_image", "reference_images",
                "reference_videos", "reference_audios", "content"):
        value = getattr(payload, key)
        if value:
            stored_params[key] = value

    # 提交时自动补齐一致性锚（定妆图 + 前镜成片接力）；调用方显式给的优先。
    _auto_references(project_id, payload.shot_id, payload.version_id, stored_params)

    job = deps.store().create_video_job(
        project_id=project_id,
        shot_id=payload.shot_id,
        provider=payload.provider,
        model=payload.model,
        prompt=payload.prompt,
        params=stored_params,
        version_id=payload.version_id,
        cost_estimate=cost,
    )
    _submit_video_job(job)
    return job


def _job_dict(j: Any) -> dict[str, Any]:
    return {
        "id": j.id,
        "shot_id": j.shot_id,
        "provider": j.provider,
        "model": j.model,
        "prompt": j.prompt,
        "status": j.status,
        "video_url": j.video_url,
        "error_message": j.error_message,
        "cost_estimate": j.cost_estimate,
        "created_at": j.created_at.isoformat(),
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
    }


def _auto_references(project_id: str, shot_id: str | None, version_id: str | None, stored_params: dict[str, Any]) -> None:
    """提交时自动补齐多模态一致性输入（调用方显式提供的键优先，不覆盖）。

    - reference_videos：连续性接力——按镜头计划（reference_group / chain_from）
      解析「已完成前镜」的成片 URL，锁跨镜风格/光影/人物；
    - reference_images：风格指南注册表里的定妆图（场景→环境图、人物→角色图），
      图像级锚比纯文字锚约束力强一个量级。
    """
    if not shot_id:
        return
    store = deps.store()

    versions = store.list_video_versions(project_id)
    version = next((v for v in versions if v.id == version_id), None)
    if version is None:
        ordered = sorted(versions, key=lambda v: v.created_at)
        version = ordered[-1] if ordered else None
    if version is None or not version.shots:
        return
    if not any(s.get("id") == shot_id for s in version.shots if isinstance(s, dict)):
        return

    completed_urls = {
        j.shot_id: j.video_url
        for j in store.list_video_jobs(project_id)
        if j.status == "succeeded" and j.video_url and j.shot_id
    }
    registry = dict((store.get_video_style(project_id) or {}).get("reference_images") or {})

    script = None
    try:
        script = store.latest_version(common.get_project(project_id)).script
    except Exception:  # noqa: BLE001
        log.warning("自动参考回填：取剧本版本失败，跳过定妆图回填")

    from ..video.continuity import resolve_submission_references

    refs = resolve_submission_references(
        shot_id=shot_id,
        shot_plan=[s for s in version.shots if isinstance(s, dict)],
        completed_urls=completed_urls,
        image_registry=registry,
        script=script,
    )
    for key in ("reference_images", "reference_videos"):
        if refs.get(key) and not stored_params.get(key):
            stored_params[key] = refs[key]


@router.post("/projects/{project_id}/video/generate")
def create_video_job(project_id: str, payload: VideoJobCreate) -> dict[str, Any]:
    """提交视频生成任务：落库后立刻投递到异步队列（提交 → 轮询 → 回调写回状态）。"""
    common.get_project(project_id)
    job = _create_and_submit_job(project_id, payload)
    return {
        "id": job.id,
        "status": "submitted",
        "provider": job.provider,
        "model": job.model,
        "cost_estimate": job.cost_estimate,
    }


@router.get("/projects/{project_id}/video/jobs")
def list_video_jobs(project_id: str) -> list[dict[str, Any]]:
    """列出项目的所有视频生成任务。"""
    common.get_project(project_id)
    return [_job_dict(j) for j in deps.store().list_video_jobs(project_id)]
@router.get("/video/jobs/{job_id}")
def get_video_job(job_id: str) -> dict[str, Any]:
    """查询视频生成任务状态。"""
    j = deps.store().get_video_job(job_id)
    if not j:
        raise HTTPException(404, "任务不存在")
    return {"project_id": j.project_id, **_job_dict(j)}


@router.post("/video/jobs/{job_id}/cancel")
def cancel_video_job(job_id: str) -> dict[str, Any]:
    """取消视频生成任务：先请服务商侧停止，再收尾本地状态。"""
    j = deps.store().get_video_job(job_id)
    if not j:
        raise HTTPException(404, "任务不存在")
    # 服务商侧取消是尽力而为：任务已不在内存队列（如进程重启过）或 provider
    # 不支持取消时，不影响本地状态收尾——本地状态才是前端看到的那份。
    try:
        provider = _resolve_video_provider(j.provider)
        if provider is not None:
            deps.video_manager().cancel(job_id, provider)
    except Exception as e:  # noqa: BLE001
        log.warning("通知 provider 取消任务 %s 失败：%s", job_id, e)
    deps.store().update_video_job(job_id, status="cancelled", finished_at=common.now())
    return {"id": job_id, "status": "cancelled"}


@router.post("/video/jobs/{job_id}/retry")
def retry_video_job(job_id: str) -> dict[str, Any]:
    """重试失败的视频生成任务：重置状态并重新投递到异步队列。"""
    j = deps.store().get_video_job(job_id)
    if not j:
        raise HTTPException(404, "任务不存在")
    if j.status not in ("failed", "cancelled"):
        raise HTTPException(400, f"任务状态为 {j.status}，只能重试失败或已取消的任务")
    deps.store().update_video_job(
        job_id, status="pending", error_message=None, video_url=None, finished_at=None
    )
    _submit_video_job(deps.store().get_video_job(job_id))
    return {"id": job_id, "status": "pending"}


# ---------- 批量生成（自动 / 审批模式） ----------


def _pick_video_provider() -> tuple[str, str]:
    """选第一个已配置且启用的视频 provider（与前端 submitVideoJob 的兜底一致）。"""
    for row in deps.store().list_api_providers(kind="video"):
        if getattr(row, "enabled", True):
            return row.name, "default"
    return "minimax", "default"


def _batch_submit(
    project_id: str,
    provider: str,
    model: str,
    version_id: str | None,
    resolution: str | None = None,
) -> Any:
    """构造批次用的 submit 回调：为指定镜头创建并投递任务，返回 job_id。"""
    store = deps.store()

    def _submit(shot_id: str) -> str | None:
        shots = []
        if version_id:
            version = store.get_video_version(version_id)
            shots = version.shots if version else []
        else:
            versions = sorted(store.list_video_versions(project_id), key=lambda v: v.created_at)
            shots = versions[-1].shots if versions else []
        shot = next((s for s in shots if isinstance(s, dict) and s.get("id") == shot_id), None)
        if shot is None or not shot.get("video_prompt"):
            return None
        try:
            job = _create_and_submit_job(project_id, VideoJobCreate(
                shot_id=shot_id, provider=provider, model=model,
                prompt=shot.get("video_prompt") or "", version_id=version_id,
                params=({"resolution": resolution} if resolution else {}),
            ))
            return job.id
        except Exception as e:  # noqa: BLE001
            log.warning("批次提交镜头 %s 失败：%s", shot_id, e)
            return None

    return _submit


class BatchCreateRequest(BaseModel):
    """批量生成请求。mode=auto 一次跑完；mode=approval 每镜等用户预览放行。

    resolution 不传时用全局默认（VIDEO_DEFAULT_RESOLUTION）；显式传入则覆盖。
    """

    mode: str = Field(default="auto", pattern=r"^(auto|approval)$")
    provider: str | None = None
    model: str | None = None
    version_id: str | None = None
    resolution: str | None = Field(default=None, max_length=20)


@router.post("/projects/{project_id}/video/generate-batch")
def generate_batch(project_id: str, payload: BatchCreateRequest) -> dict[str, Any]:
    """按最新视频版本的镜头计划批量生成。串行推进，前镜成片自动作为后镜接力参考。"""
    common.get_project(project_id)
    store = deps.store()
    if payload.version_id:
        version = store.get_video_version(payload.version_id)
        if version is None:
            raise HTTPException(404, "视频版本不存在")
    else:
        versions = sorted(store.list_video_versions(project_id), key=lambda v: v.created_at)
        version = versions[-1] if versions else None
    if version is None or not version.shots:
        raise HTTPException(400, "还没有镜头方案：请先完成导演与摄影指导阶段")

    shot_ids = [
        s["id"] for s in version.shots
        if isinstance(s, dict) and s.get("id") and s.get("video_prompt")
    ]
    if not shot_ids:
        raise HTTPException(400, "镜头方案里没有任何带视频提示词的镜头")

    provider = payload.provider or _pick_video_provider()[0]
    model = payload.model or "default"
    batch = deps.batch_manager().start(
        project_id, shot_ids, payload.mode,
        _batch_submit(project_id, provider, model, version.id, payload.resolution),
    )
    if batch.status == "failed":
        raise HTTPException(500, batch.error or "批次启动失败")
    return batch.to_dict()


@router.get("/projects/{project_id}/video/batch")
def get_latest_batch(project_id: str) -> dict[str, Any]:
    """查询项目最新批次的进度（前端轮询用）。"""
    common.get_project(project_id)
    batch = deps.batch_manager().latest_for_project(project_id)
    if batch is None:
        return {"id": None, "status": "none"}
    return batch.to_dict()


class BatchCommandRequest(BaseModel):
    command: str = Field(pattern=r"^(approve|reroll|abort)$")


@router.post("/video/batches/{batch_id}/command")
def batch_command(batch_id: str, payload: BatchCommandRequest) -> dict[str, Any]:
    """向批次下达命令：approve 放行下一镜 / reroll 重跑当前镜 / abort 终止。"""
    mgr = deps.batch_manager()
    batch = mgr.get(batch_id)
    if batch is None:
        raise HTTPException(404, "批次不存在")

    # 在状态变更前捕获当前任务与最新版本：approve/reroll 沿用原 provider/model。
    prev = deps.store().get_video_job(batch.job_id) if batch.job_id else None
    provider = prev.provider if prev else "minimax"
    model = prev.model if prev else "default"
    prev_resolution = ((prev.params or {}).get("resolution") if prev else None) or None
    versions = sorted(deps.store().list_video_versions(batch.project_id), key=lambda v: v.created_at)
    version_id = versions[-1].id if versions else None

    def _resubmit(shot_id: str) -> str | None:
        return _batch_submit(batch.project_id, provider, model, version_id, prev_resolution)(shot_id)

    try:
        if payload.command == "approve":
            batch = mgr.approve(batch_id, _resubmit)
        elif payload.command == "reroll":
            batch = mgr.reroll(batch_id, _resubmit)
        else:
            batch = mgr.abort(batch_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return batch.to_dict()
