# =====================================================================
# refs.py —— 参考资产流水线（视觉一致性的图像级锚点）
#
# 工业级思路的落地：先产「角色定妆图 / 场景定妆图」，用视觉模型质检，
# 通过的图注册为全局参考，再回填到每个镜头的 reference_images。
#
# 为什么这样做：文生视频每个镜头独立采样，纯文字锚只能「减少」漂移；
# 把同一个角色的图作为参考喂进去，模型是「看见」同一个人，强度高一个量级。
#
# 流程：定妆 prompt → 文生图 → 视觉质检 →（不合格重生成，最多 N 次）→ 注册
#
# 模型能力本身不在这里实现：文生图与视觉质检都由 app/llm 提供
# （ImageClient / VisionClient），本模块只负责 prompt 组装、质检判定与回填。
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

from ..domain import Script, Shot, StyleGuide
from ..llm import ImageClient, VisionClient

log = logging.getLogger(__name__)

# provider 侧参考图上限（MiniMax 参考图 ≤9）
MAX_REFERENCE_IMAGES = 9


# ---------- 定妆 prompt ----------


def character_prompt(name: str, appearance: str) -> str:
    """角色定妆图 prompt：用风格指南里的固定外貌描述 + 定妆照约束。"""
    desc = (appearance or "").strip() or name
    return (
        f"角色定妆照。{desc}。正面半身像，纯灰色背景，光线均匀柔和，写实电影质感，"
        "五官清晰、服装细节清楚；人物必须是中国人（东亚面孔）。画面里不要出现任何文字。"
    )


def environment_prompt(name: str, description: str) -> str:
    """场景定妆图 prompt：固定环境描述 + 空镜约束（不放具体人物，避免把某个人锁进场景）。"""
    desc = (description or "").strip() or name
    return (
        f"场景定妆图。{desc}。广角固定机位空镜，画面里没有任何人物；"
        "写实电影质感，光线氛围与描述一致，空间关系清楚。画面里不要出现任何文字。"
    )


# ---------- 视觉质检 ----------

_QA_CHARACTER = (
    "你在给 AI 短剧做角色定妆图质检。\n"
    "只有以下两种情况判 FAIL（任一不满足即 FAIL）：\n"
    "A) 画面不是「单人 + 正面 + 半身」的定妆照（例如多人合影、全身远景、纯风景）；\n"
    "B) 人物不是中国人 / 东亚面孔。\n"
    "　（例外：若该角色按设定本就戴面具 / 头盔 / 看不到人脸，B 条不适用，不要因此判 FAIL。）\n"
    "注意：平台水印、背景颜色、服装细节的细微出入都**不算** FAIL，不要因此判不合格。\n"
    "参考描述（用于确认没画错角色，不要求逐条吻合）：\n{expect}\n\n"
    "最后一行只输出一个词：PASS 或 FAIL。"
)

_QA_ENVIRONMENT = (
    "你在给 AI 短剧做场景定妆图质检。\n"
    "只有以下两种情况判 FAIL（任一不满足即 FAIL）：\n"
    "A) 画面主体不是一个「空间环境」（例如是人物特写 / 肖像）；\n"
    "B) 画面里有明显的人物。\n"
    "注意：平台水印、家具数量、灯光位置等细节出入都**不算** FAIL，只要整体空间类型与气质对得上即可。\n"
    "参考描述：\n{expect}\n\n"
    "最后一行只输出一个词：PASS 或 FAIL。"
)


def _verdict(text: str) -> tuple[bool, str]:
    """从质检回答里解析 PASS/FAIL；解析不到时保守判为通过（避免无限重生）。"""
    tail = text.strip().upper()
    if "FAIL" in tail:
        return False, text.strip()[-200:]
    if "PASS" in tail:
        return True, text.strip()[-200:]
    return True, "（未能解析判定，按通过处理）"


# ---------- 生成 + 注册 ----------


def build_reference_assets(
    script: Script,
    style_guide: StyleGuide | None,
    *,
    image_client: ImageClient | None = None,
    vision_client: VisionClient | None = None,
    max_retry: int = 2,
    on_progress: Any = None,
) -> dict[str, str]:
    """为角色与场景生成定妆图并质检，返回 {名称: 图片URL}。

    - 角色名 / 地点名与 StyleGuide 的键保持一致，方便回填时查表；
    - 质检不合格就重生成，最多 max_retry 次；仍不合格则保留最后一张（带警告）；
    - 不传客户端时从 app/llm 解析当前配置（.env / DB 里的 provider）。
    """
    provider = image_client
    vision = vision_client
    if provider is None or vision is None:
        from ..deps import llm as get_llm

        facade = get_llm()
        provider = provider or facade.image()
        vision = vision or facade.vision()
    if provider is None or not provider.available:
        raise RuntimeError(
            "未配置文生图 key（IMAGE_PROVIDER=zhipu/cogview 或 OPENAI_API_KEY），"
            "无法生成参考资产"
        )

    def _emit(msg: str) -> None:
        log.info(msg)
        if on_progress:
            on_progress(msg)

    refs: dict[str, str] = {}
    appearances = dict(getattr(style_guide, "character_appearances", {}) or {}) if style_guide else {}
    environments = dict(getattr(style_guide, "environment_descriptions", {}) or {}) if style_guide else {}

    # 角色：优先用风格指南的固定外貌；缺失则退化为人物名
    names = list(appearances.keys()) or [c.name for c in script.characters]
    for name in names:
        appearance = appearances.get(name, "")
        prompt = character_prompt(name, appearance)
        refs[name] = _generate_with_qa(
            provider, prompt, _QA_CHARACTER.format(expect=appearance or name),
            kind=f"角色·{name}", vision=vision, max_retry=max_retry, emit=_emit,
        )

    # 场景：优先用风格指南的环境描述；缺失则退化为地点名
    loc_names = list(environments.keys()) or [loc.name for loc in script.locations]
    for name in loc_names:
        desc = environments.get(name, "")
        prompt = environment_prompt(name, desc)
        refs[name] = _generate_with_qa(
            provider, prompt, _QA_ENVIRONMENT.format(expect=desc or name),
            kind=f"场景·{name}", vision=vision, max_retry=max_retry, emit=_emit,
        )

    return refs


def _generate_with_qa(
    provider: ImageClient,
    prompt: str,
    qa_question: str,
    *,
    kind: str,
    vision: VisionClient,
    max_retry: int,
    emit: Any,
) -> str:
    """生成 → 质检 → 不合格重试；返回最终采用的图片 URL。"""
    url = ""
    for attempt in range(max_retry + 1):
        url = provider.generate(prompt)
        if not vision.available:
            emit(f"[{kind}] 已生成（未配置视觉模型，跳过质检）")
            return url
        try:
            text = vision.ask(url, qa_question)
            ok, reason = _verdict(text)
        except Exception as e:  # noqa: BLE001
            emit(f"[{kind}] 质检调用失败，保留该图：{e}")
            return url
        if ok:
            emit(f"[{kind}] 质检通过（第 {attempt + 1} 次）")
            return url
        emit(f"[{kind}] 质检不合格，重生成（第 {attempt + 1} 次）：{reason}")
    emit(f"[{kind}] 重试 {max_retry} 次仍不合格，保留最后一张")
    return url


# ---------- 回填到镜头 ----------


def apply_reference_images(
    shots: list[Shot],
    refs: dict[str, str],
    script: Script,
) -> int:
    """把注册好的参考图按「场景 → 环境图」「人物 → 角色图」回填到每个镜头。

    返回被填充的镜头数。
    """
    if not refs:
        return 0
    loc_map = {loc.id: loc.name for loc in script.locations}
    char_map = {c.id: c.name for c in script.characters}
    scene_map = {sc.id: sc for sc in script.scenes}

    filled = 0
    for shot in shots:
        sc = scene_map.get(shot.scene_id)
        if sc is None:
            continue
        urls: list[str] = []
        env_url = refs.get(loc_map.get(sc.location_id, ""))
        if env_url:
            urls.append(env_url)
        for cid in sc.characters:
            url = refs.get(char_map.get(cid, ""))
            if url and url not in urls:
                urls.append(url)
        if urls:
            shot.reference_images = urls[:MAX_REFERENCE_IMAGES]
            filled += 1
    return filled
