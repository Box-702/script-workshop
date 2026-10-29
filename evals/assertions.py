# =====================================================================
# assertions.py —— 提示词质量的确定性断言库
#
# 这些断言是 eval 的「硬层」：不依赖 LLM 判定，只跑规则，因此
# **每次都稳定、零成本、可进 CI**。它们检查的是「一定会导致出片失败」
# 的硬伤，而不是「写得好不好」——后者交给 LLM judge（见 judge_prompt.md）。
#
# 判定分两级：
#   critical —— 违反就是明确缺陷，必须修（CI 里直接失败）
#   warn     —— 违反是质量风险，不一定错（CI 里只报告）
#
# 复用 app/crew/dramaturgy.py 的检测器，不重复造词表：
# 审计规则改一次，这里自动跟着变。
# =====================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.crew.dramaturgy import (
    SHOT_FUNCTIONS,
    audit_breakdowns,
    find_camera_moves,
    find_negations,
    find_slop_words,
    find_spoken_quotes,
    strip_style_block,
    three_details,
)
from app.domain import Script, SceneBreakdown, Shot, StyleGuide

# 目标视频模型的可行时长区间（秒）。超出区间的镜头多半会被服务商忽略或失败。
MIN_SHOT_SEC = 4.0
MAX_SHOT_SEC = 15.0


@dataclass
class Failure:
    """一条断言失败记录。"""

    rule: str  # 规则 id，如 "DPT-02"
    severity: str  # critical / warn
    where: str  # 定位，如 "scene_001/shot_002"
    message: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.rule} @ {self.where}: {self.message}"


@dataclass
class AssertionResult:
    """一个被评对象的断言结果。"""

    target: str  # "director" / "dp"
    failures: list[Failure] = field(default_factory=list)

    @property
    def critical(self) -> list[Failure]:
        return [f for f in self.failures if f.severity == "critical"]

    @property
    def warns(self) -> list[Failure]:
        return [f for f in self.failures if f.severity == "warn"]

    @property
    def passed(self) -> bool:
        return not self.critical

    def add(self, rule: str, severity: str, where: str, message: str) -> None:
        self.failures.append(Failure(rule=rule, severity=severity, where=where, message=message))


# ---------------------------------------------------------------------
# 一、导演侧断言
# ---------------------------------------------------------------------


def assert_director(
    breakdowns: list[SceneBreakdown],
    *,
    script: Script | None = None,
) -> AssertionResult:
    """检查导演分镜产出。

    覆盖：每镜是否做功（三工作规则）、是否有最终画面、细节密度、
    切镜理由、时长可行性、接力链路自洽、场景锚点是否命名。
    """
    res = AssertionResult(target="director")
    if not breakdowns:
        res.add("DIR-00", "critical", "director", "导演没有产出任何分镜")
        return res

    # 五锚点 / function / final_frame / 细节 —— 复用生产代码里的审计器，
    # 保证 eval 与线上审计用的是同一套规则（否则 eval 通过了线上照样挂）。
    for issue in audit_breakdowns(breakdowns):
        res.add("DIR-01", "critical", "director", issue)

    seen_orders: set[int] = set()
    for bd in breakdowns:
        where_scene = bd.scene_id
        for s in bd.shots:
            where = f"{where_scene}/{s.id}"

            # function 必须合法（audit_breakdowns 已查，这里兜底防重复实现漂移）
            if s.function and s.function not in SHOT_FUNCTIONS:
                res.add(
                    "DIR-02", "critical", where,
                    f"function 取值非法：{s.function!r}（合法值：{'/'.join(SHOT_FUNCTIONS)}）",
                )

            # 时长可行性
            if not (MIN_SHOT_SEC <= s.duration_sec <= MAX_SHOT_SEC):
                res.add(
                    "DIR-03", "warn", where,
                    f"镜头时长 {s.duration_sec}s 超出目标模型可行区间 "
                    f"[{MIN_SHOT_SEC}, {MAX_SHOT_SEC}]s，多半会被忽略或失败",
                )

            # 接力链路自洽：chain_from 必须指向已存在的、更早的 order
            if s.chain_from is not None:
                if s.chain_from not in seen_orders:
                    res.add(
                        "DIR-04", "critical", where,
                        f"chain_from={s.chain_from} 指向一个不存在或更晚的镜头（接力会错位）",
                    )
                if s.chain_from >= s.order:
                    res.add(
                        "DIR-05", "critical", where,
                        f"chain_from={s.chain_from} 不小于自身 order={s.order}（不能接自己的未来）",
                    )

            # 主体不能为空——空主体的镜头渲染不出东西
            if not s.subject.strip():
                res.add("DIR-06", "critical", where, "镜头没有主体（subject 为空）")

            # 动作不能为空
            if not s.action.strip():
                res.add("DIR-07", "warn", where, "镜头没有写动作（action 为空）")

            seen_orders.add(s.order)

    # 镜头数：一场戏至少 1 镜；单场超过 12 镜多半是切碎
    for bd in breakdowns:
        n = len(bd.shots)
        if n == 0:
            res.add("DIR-08", "critical", bd.scene_id, "这场戏一个镜头都没有")
        elif n > 12:
            res.add(
                "DIR-09", "warn", bd.scene_id,
                f"这场戏切了 {n} 镜，过碎（切碎 = 不连贯 + 更贵），建议合并",
            )

    return res


# ---------------------------------------------------------------------
# 二、摄影指导侧断言
# ---------------------------------------------------------------------


def assert_dp(
    shots: list[Shot],
    *,
    script: Script | None = None,
    style_guide: StyleGuide | None = None,
) -> AssertionResult:
    """检查摄影指导产出的最终 video_prompt。

    覆盖：可渲染性（长度）、空洞词、否定句、引用台词、一镜多运镜、
    以及「视觉锚逐字复用」这条贯穿全链路的核心原则。
    """
    res = AssertionResult(target="dp")
    if not shots:
        res.add("DPT-00", "critical", "dp", "摄影指导没有产出任何镜头")
        return res

    env_by_scene: dict[str, str] = {}
    char_by_scene: dict[str, set[str]] = {}
    if script is not None:
        loc_name = {loc.id: loc.name for loc in script.locations}
        char_name = {c.id: c.name for c in script.characters}
        for sc in script.scenes:
            env_by_scene[sc.id] = loc_name.get(sc.location_id, "")
            char_by_scene[sc.id] = {char_name.get(cid, cid) for cid in sc.characters}

    canon_env: dict[str, str] = dict(style_guide.environment_descriptions) if style_guide else {}
    canon_char: dict[str, str] = dict(style_guide.character_appearances) if style_guide else {}

    for s in shots:
        where = f"{s.scene_id}/{s.id}"
        prompt = (s.video_prompt or "").strip()

        if not prompt:
            res.add("DPT-01", "critical", where, "镜头没有 video_prompt（无法提交出片）")
            continue

        # 过短：没有可渲染的物理事实，模型只能自由发挥
        if len(prompt) < 20:
            res.add("DPT-02", "critical", where, f"提示词过短（{len(prompt)} 字），模型只能自由发挥")

        slop = find_slop_words(prompt)
        if slop:
            res.add(
                "DPT-03", "critical", where,
                f"含渲染不出来的占位词：{'、'.join(sorted(set(slop)))}",
            )

        negs = find_negations(prompt)
        if negs:
            uniq = "、".join(dict.fromkeys(negs))
            res.add(
                "DPT-04", "critical", where,
                f"含否定式描述（{uniq[:30]}）：视频模型会把被否定的动作画出来",
            )

        quotes = find_spoken_quotes(prompt)
        if quotes:
            res.add(
                "DPT-05", "critical", where,
                f"含引用台词（「{quotes[0][:14]}」）：会渲染成含混的假说话，语音应交给后期配音",
            )

        # 一镜多运镜
        #
        # 与生产审计器同源：剥掉全片风格段（style_guide.camera_style），
        # 且只认「带镜头语境」的运镜动词——「拉出一道冷光带」不是 pull-out。
        # 这两条都是实测踩出来的：不剥风格段、不看语境，真实提示词会 4/4 全误报。
        own_text = strip_style_block(prompt, style_guide.camera_style if style_guide else "")
        moves = set(find_camera_moves(own_text))
        if s.camera.path:
            moves |= set(find_camera_moves(s.camera.path))
        if len(moves) >= 2:
            res.add(
                "DPT-06", "warn", where,
                f"疑似一镜多运镜（{'、'.join(sorted(moves)[:3])}）：一镜只保留一种主要运动",
            )

        # 三细节密度（用 prompt 全文兜底判定）
        count, missing = three_details(
            action=s.action,
            lighting=s.lighting or "",
            background_action=s.background_action,
            prompt=prompt,
        )
        if count == 0:
            res.add("DPT-07", "critical", where, "提示词里一个物理细节都没有（零细节 = 废镜头）")
        elif count == 1:
            res.add("DPT-08", "warn", where, f"只有「{missing[0]}」一类细节，画面会单薄")

        # 视觉锚逐字复用（贯穿全链路的第一原则）
        #
        # 判定用「整段锚是否原样出现」+ 相似度分级，而不是比对前几个字——
        # 只看开头几个字会把「锚被轻微改写」误判成「完全没复用」，
        # 而把轻微改写放过又看不出真实退化。实测 DP 偶尔会重写锚里的个别词。
        if style_guide is not None:
            env_name = env_by_scene.get(s.scene_id, "")
            canon_env_text = canon_env.get(env_name, "") if env_name else ""
            if canon_env_text:
                ratio = _anchor_similarity(canon_env_text, prompt)
                if canon_env_text not in prompt and ratio < 0.85:
                    res.add(
                        "DPT-09", "critical", where,
                        f"没有逐字复用环境锚「{env_name}」（相似度 {ratio:.0%}）："
                        "下游必须复用美术指导产出的锚，每镜重写会导致跨镜漂移",
                    )
                elif canon_env_text not in prompt:
                    res.add(
                        "DPT-11", "warn", where,
                        f"环境锚「{env_name}」被轻微改写（相似度 {ratio:.0%}）："
                        "锚应原样复用，改写会让同一地点在不同镜头里长得不一样",
                    )
            for cid in sorted(char_by_scene.get(s.scene_id, set())):
                appear = canon_char.get(cid, "")
                if not appear:
                    continue
                # 只查**真的出现在这一镜里**的角色：场景人物表里的人在某一镜可能根本不出场，
                # 没出场自然不该有锚。判据是「提示词里点了他的名」。
                if cid not in prompt:
                    continue
                ratio = _anchor_similarity(appear, prompt)
                if appear not in prompt and ratio < 0.85:
                    res.add(
                        "DPT-10", "critical", where,
                        f"没有复用人物锚「{cid}」的造型（相似度 {ratio:.0%}）："
                        "逐字复用可避免跨镜长相漂移",
                    )
                elif appear not in prompt:
                    res.add(
                        "DPT-12", "warn", where,
                        f"人物锚「{cid}」被轻微改写（相似度 {ratio:.0%}）：锚应原样复用",
                    )

    return res


def _anchor_similarity(anchor: str, prompt: str) -> float:
    """锚在提示词里的保留程度：0-1。

    用最长公共子序列比值衡量「锚被改写了多少」——锚原样出现时为 1.0。
    """
    from difflib import SequenceMatcher

    if not anchor or not prompt:
        return 0.0
    if anchor in prompt:
        return 1.0
    matcher = SequenceMatcher(None, anchor, prompt)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return matched / len(anchor)


# ---------------------------------------------------------------------
# 三、跨链路断言
# ---------------------------------------------------------------------


def assert_pipeline(
    breakdowns: list[SceneBreakdown],
    shots: list[Shot],
    *,
    script: Script | None = None,
    style_guide: StyleGuide | None = None,
) -> AssertionResult:
    """检查导演 → 摄影指导这条链路的一致性。"""
    res = AssertionResult(target="pipeline")

    bd_ids = {s.id for bd in breakdowns for s in bd.shots}
    for s in shots:
        where = f"{s.scene_id}/{s.id}"
        if s.id not in bd_ids:
            res.add(
                "LNG-01", "critical", where,
                "摄影指导产出了导演没拆过的镜头（镜头集合对不上）",
            )
        if not (s.video_prompt or "").strip():
            res.add("LNG-02", "critical", where, "该镜头最终没有提示词，无法提交出片")

    # 剧本里的场景都应该被拆到
    if script is not None:
        covered = {bd.scene_id for bd in breakdowns}
        for sc in script.scenes:
            if sc.id not in covered:
                res.add("LNG-03", "critical", sc.id, "剧本里这场戏没有被导演拆解")

    return res


# ---------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------


def summarize(results: list[AssertionResult]) -> dict[str, Any]:
    """把多个断言结果压成可比较的统计（用于跨版本对比）。"""
    total_fail = sum(len(r.failures) for r in results)
    total_crit = sum(len(r.critical) for r in results)
    return {
        "targets": len(results),
        "failures": total_fail,
        "critical": total_crit,
        "warn": total_fail - total_crit,
        "by_rule": _count_by_rule(results),
        "all_passed": all(r.passed for r in results),
    }


def _count_by_rule(results: list[AssertionResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in results:
        for f in r.failures:
            counts[f.rule] = counts.get(f.rule, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def format_failures(results: list[AssertionResult], *, limit: int = 40) -> str:
    """把失败列表渲染成可读报告。"""
    lines: list[str] = []
    shown = 0
    for r in results:
        if not r.failures:
            continue
        lines.append(f"── {r.target} ──")
        for f in r.failures:
            if shown >= limit:
                lines.append(f"  … 另有 {sum(len(x.failures) for x in results) - shown} 条未显示")
                return "\n".join(lines)
            lines.append(f"  {f}")
            shown += 1
    return "\n".join(lines) or "（无失败）"
