# =====================================================================
# review.py —— 改编审阅 / 一致性保障 / 评审打分
#
# 这是「guard 自纠错」之上的一层 LLM 审阅：Agent 先产出结构化提议，
# 再由本模块对「应用提议后的剧本」做一次多维度评审，回答两个问题：
#   1. 改得怎么样？（评审打分：overall_score + 分维度得分）
#   2. 有没有破坏一致性与结构？（一致性保障：角色 / 情节 / 设定 / 时间线 / 风格）
#
# 我们刻意把这一层做成一等公民，而不是塞在 guard 里：
#   - 结构化输出（PatchReview）可被前端直接渲染成「评审卡片」；
#   - 与 deterministic 的 validate_script（引用 / id）互补：
#     validate_script 管「硬约束」，review 管「软质量 + 语义一致性」；
#   - 只有当配置了模型时才运行（llm.available），无模型时走纯规则校验，
#     保证离线 / 测试链路依然闭环。
#
# 一致性保障的维度（参考同类创作 Agent 的「世界观 / 角色 / 大纲一致性」思路）：
#   - 角色一致性：人物言行是否符合其 goal / personality / speech_style；
#   - 设定一致性：不引入剧本设定之外的地点 / 全新元素（系统提示已禁止新增）；
#   - 时间线一致性：场景 time / 叙事先后是否自洽；
#   - 情节一致性：是否推翻既有主线 / 伏笔，或制造断点；
#   - 风格一致性：是否偏离作者语言风格与改编类型 tone。
# =====================================================================

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from .domain import Script
    from .llm import LLM

log = logging.getLogger(__name__)


# ---------- 审阅结构化模型 ----------


class ReviewDimension(BaseModel):
    """单个评审维度得分（0-100）。"""

    name: Literal["fidelity", "consistency", "conflict", "style", "structure"]
    score: int = Field(ge=0, le=100)
    note: str | None = None

    @field_validator("score", mode="before")
    @classmethod
    def _clamp_score(cls, v: object) -> object:
        # 模型偶尔给出 0-100 之外的分数：收紧而不是让整次评审解析失败。
        try:
            return max(0, min(100, int(v)))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return v


class ReviewIssue(BaseModel):
    """一条审阅问题。error 级会阻塞落版（触发回炉）。"""

    severity: Literal["error", "warning"] = "error"
    category: Literal["consistency", "fidelity", "structure", "style", "conflict"] = "consistency"
    path: str | None = None
    message: str


class PatchReview(BaseModel):
    """一次改编提议的整体评审结果。"""

    overall_score: int = Field(ge=0, le=100)
    passed: bool = True
    summary: str | None = None
    dimensions: list[ReviewDimension] = Field(default_factory=list)
    issues: list[ReviewIssue] = Field(default_factory=list)

    @field_validator("overall_score", mode="before")
    @classmethod
    def _clamp_overall(cls, v: object) -> object:
        try:
            return max(0, min(100, int(v)))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return v


# 维度中文名（用于展示与提示词）。
DIMENSION_LABELS: dict[str, str] = {
    "fidelity": "忠实度",
    "consistency": "一致性",
    "conflict": "冲突",
    "style": "风格",
    "structure": "结构",
}


def _compact_scene(scene: Any, chars: dict[str, str]) -> str:
    """把单个场景压成紧凑可读的文本（人物名 + 节拍流）。"""
    char_map = chars
    beats: list[str] = []
    for b in scene.beats:
        if b.type == "dialogue":
            name = char_map.get(b.speaker, b.speaker)
            emo = f"（{b.emotion}）" if b.emotion else ""
            beats.append(f"  {name}：{b.line}{emo}")
        else:
            beats.append(f"  [动作] {b.text}")
    return (
        f"## 场景《{scene.title}》({scene.id})  地点:{scene.location_id} 时间:{scene.time or '未定'}\n"
        f"目的：{scene.purpose}\n冲突：{scene.conflict}\n节拍：\n" + "\n".join(beats)
    )


def _build_review_context(
    base: Script,
    applied: Script,
    instruction: str,
    context: dict[str, Any] | None,
    language: str,
) -> str:
    """组装评审输入：人物设定 + 被改动场景 + 上下文知识，尽量精简避免超长。"""
    lines: list[str] = []
    lines.append(f"【改编需求】{instruction.strip()}")
    lines.append(f"【人物设定】")
    for c in base.characters:
        bits = [c.name, f"role={c.role or 'other'}"]
        if c.goal:
            bits.append(f"目标: {c.goal}")
        if c.motivation:
            bits.append(f"动机: {c.motivation}")
        if c.personality:
            bits.append(f"性格: {c.personality}")
        if c.arc:
            bits.append(f"成长线: {c.arc}")
        if c.speech_style:
            bits.append(f"语言风格: {c.speech_style}")
        lines.append("  " + " | ".join(bits))
    char_map = {c.id: c.name for c in base.characters}

    # 找出被改动的场景：对比 base 与 applied 的每个场景，或直接取全部被应用场景。
    base_by_id = {s.id: s for s in base.scenes}
    changed: list[Any] = []
    for s in applied.scenes:
        b = base_by_id.get(s.id)
        if b is None or b.model_dump(exclude_none=True) != s.model_dump(exclude_none=True):
            changed.append(s)
    # 最多展示 6 个改动场景，避免撑爆上下文。
    for s in changed[:6]:
        lines.append(_compact_scene(s, char_map))
    if len(changed) > 6:
        lines.append(f"（另有 {len(changed) - 6} 个场景被改动，未展开）")

    ctx = context or {}
    knowledge = ctx.get("knowledge") or {}
    if knowledge:
        lines.append("【项目知识 / 一致性约束】")
        for kind, docs in knowledge.items():
            label = {"plot_direction": "同类走向", "technique": "写作手法", "author_style": "作者风格"}.get(kind, kind)
            for d in docs:
                lines.append(f"  - [{label}] {d}")
    lines.append(f"【输出语言】{language}")
    return "\n".join(lines)


_REVIEW_SYSTEM = (
    "你是专业的剧本审阅编辑。请对「改编后的场景改动」做一次严格评审：既要看它是否忠实于原著、"
    "是否达成改编需求，更要检查它是否破坏了一致性。\n"
    "评审要求：\n"
    "1. 只评审『被改动的场景』与相关人物，不要通读全文；\n"
    "2. 一致性检查要具体：人物言行是否符合其目标 / 性格 / 语言风格；"
    "是否引用了剧本设定之外的地点或全新元素；时间线与情节先后是否自洽；"
    "是否推翻既有主线或伏笔；是否偏离作者语言风格；\n"
    "3. 结构检查：是否保持节拍 id 稳定、不整段覆盖、不在目标场景外新增内容；\n"
    "4. 打分维度五个：fidelity(忠实度)、consistency(一致性)、conflict(冲突)、"
    "style(风格)、structure(结构)，各 0-100；\n"
    "5. overall_score 为综合分（0-100）。只有当一致性、结构、风格都没有 error 级问题、"
    "且整体分数达标时 passed=true；否则 passed=false。\n"
    "6. issues 列出问题，error 级必须是『必须改才能接受』的问题（如人物 OOC、设定冲突、"
    "时间线矛盾、结构断裂）；warning 级是可优化项（如节奏、对白再打磨）。\n"
    "只输出符合 JSON Schema 的对象，不要输出额外说明。"
)


def review_patch(
    llm: LLM,
    *,
    base: Script,
    applied: Script,
    instruction: str,
    context: dict[str, Any] | None = None,
    threshold: int = 75,
    language: str = "zh-CN",
) -> PatchReview | None:
    """对应用提议后的剧本做一次多维度评审（一致性 + 打分）。

    无可用模型时返回 None（上层走纯规则校验）。
    ``passed`` 由确定性逻辑兜底：总分 >= threshold 且无 error 级问题。
    """
    if not llm.available:
        return None
    from langchain_core.messages import HumanMessage, SystemMessage

    prompt = _build_review_context(base, applied, instruction, context, language)
    prompt = (
        "请评审下面这次剧本改编：\n\n" + prompt + "\n\n"
        "请严格按照 JSON Schema 输出 {overall_score, passed, summary, dimensions[], issues[]}。"
    )
    try:
        review = llm.structured(PatchReview).invoke(
            [
                SystemMessage(content=_REVIEW_SYSTEM),
                HumanMessage(content=prompt),
            ]
        )
    except Exception as e:  # noqa: BLE001
        log.warning("LLM 评审解析失败，本次评审跳过（guard 仅用规则校验）：%s", e)
        return None
    if review is None:
        return None
    has_error = any(i.severity == "error" for i in review.issues)
    review.passed = bool(review.overall_score >= threshold and not has_error)
    return review
