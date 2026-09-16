# =====================================================================
# test_crew_video.py —— 剧组链路与视频适配层测试
#
# 覆盖本次开发新增/修复的核心逻辑（这些坑都真实踩过，固化成回归测试）：
#   - 导演拆解：全局重编号、枚举容错、时长钳制、连续性校验；
#   - 摄影指导：语言推断、锚逐字复用、按镜过滤人物、无风格指南时的退化；
#   - 连续性解析：reference_group / chain_from → reference_videos；
#   - 视频 Provider：状态映射的子串陷阱、嵌套 task、结果字段名。
# =====================================================================

from __future__ import annotations

import asyncio

from app.crew.art_director import art_system
from app.crew.director import DirectorAgent
from app.crew.dp import DPAgent, _strip_spoken_quotes, dp_system, language_for
from app.domain import (
    CameraMovement,
    Character,
    Location,
    Scene,
    SceneBreakdown,
    Script,
    Shot,
    Source,
    StyleGuide,
)
from app.video.continuity import resolve_continuity, resolve_submission_references

# ---------- 测试夹具 ----------


def _script() -> Script:
    return Script(
        title="测试剧",
        logline="一行梗概",
        themes=["悬疑"],
        source=Source(chapter_count=1, chapter_ids=["ch_001"]),
        characters=[Character(id="char_a", name="齐夏"), Character(id="char_b", name="人羊")],
        locations=[Location(id="loc_room", name="密室")],
        scenes=[
            Scene(
                id="scene_001", title="第一场", chapter_refs=["ch_001"], location_id="loc_room",
                characters=["char_a", "char_b"], purpose="建立冲突", conflict="对峙",
            )
        ],
    )


def _director() -> DirectorAgent:
    # 这两个方法不依赖 LLM，直接构造实例即可。
    return DirectorAgent.__new__(DirectorAgent)


def _dp() -> DPAgent:
    return DPAgent.__new__(DPAgent)


# ---------- 导演：解析容错 ----------


def test_director_parse_renumbers_order_globally_and_remaps_chain():
    raw = [
        {"scene_id": "scene_001", "shots": [
            {"order": 0, "subject": "A", "duration_sec": 8, "reference_group": "room", "chain_from": None, "cut_reason": "起点"},
            {"order": 1, "subject": "B", "duration_sec": 8, "reference_group": "room", "chain_from": 0, "cut_reason": "切换"},
        ]},
        {"scene_id": "scene_002", "shots": [
            {"order": 0, "subject": "C", "duration_sec": 8, "reference_group": "room", "chain_from": None, "cut_reason": "新场起点"},
            {"order": 1, "subject": "D", "duration_sec": 8, "reference_group": "room", "chain_from": 0, "cut_reason": "切换"},
        ]},
    ]
    bds = _director()._parse_breakdowns(raw)
    orders = [(s.scene_id, s.order) for bd in bds for s in bd.shots]
    # order 必须是全片唯一且递增的（不是每场从 0 重来）
    assert orders == [("scene_001", 0), ("scene_001", 1), ("scene_002", 2), ("scene_002", 3)]
    # chain_from 从「场景内局部 order」映射到全局 order
    second_scene = bds[1].shots
    assert second_scene[0].chain_from is None
    assert second_scene[1].chain_from == 2


def test_director_parse_coerces_enum_and_clamps_duration():
    raw = [{"scene_id": "scene_001", "pacing": "fast-paced", "shots": [
        {"order": 0, "shot_type": "close-up", "camera_type": "push_in", "camera_speed": "slow",
         "subject": "A", "duration_sec": 0.8, "cut_reason": "x"},
        {"order": 1, "shot_type": "不存在的景别", "camera_type": "weird_cam", "camera_speed": "warp",
         "subject": "B", "duration_sec": 99, "cut_reason": "y"},
    ]}]
    bd = _director()._parse_breakdowns(raw)[0]
    assert bd.pacing == "medium"                    # 非法 pacing 兜底
    s0, s1 = bd.shots
    assert (s0.shot_type, s0.camera.type, s0.camera.speed) == ("close_up", "dolly", "slow")
    assert s0.duration_sec == 1.0                   # 0.8 被钳到下限
    assert (s1.shot_type, s1.camera.type, s1.camera.speed) == ("medium", "static", "medium")
    assert s1.duration_sec == 30.0                  # 99 被钳到上限


def test_director_parse_reads_scheduling_fields():
    """画面调度四件套（运镜轨迹/机位高度/空间关系/背景人物）必须落到 Shot 上。"""
    raw = [{"scene_id": "scene_001", "shots": [{
        "order": 0, "shot_type": "wide", "camera_type": "orbit", "camera_speed": "slow",
        "camera_path": "从人物正面起步，绕到背后约 180 度，半径保持两米",
        "camera_height": "与人物胸口齐平，随后升到过顶",
        "subject": "现场全景", "action": "围观者退开",
        "spatial": "齐夏1号在前景左侧，离镜头 1.5 米；人羊2号在后景，两人相隔约 3 米",
        "background_action": "两名警察维持边界，一人偶尔回头；居民在警戒带外探头低语",
        "lighting": "主光从左上方斜射，人物右侧落在阴影里",
        "duration_sec": 8, "cut_reason": "起点",
    }]}]
    shot = _director()._parse_breakdowns(raw)[0].shots[0]
    assert shot.camera.type == "orbit"          # 新增的环绕枚举
    assert "绕到背后" in shot.camera.path
    assert shot.camera.height.startswith("与人物胸口齐平")
    assert "齐夏1号" in shot.spatial
    assert "警察" in shot.background_action


# ---------- 导演：连续性校验 ----------


def test_director_validate_flags_bad_plan():
    bd = SceneBreakdown(scene_id="scene_001", shots=[
        Shot(id="shot_scene_001_000", scene_id="scene_001", order=0, duration_sec=8),
        # 无分组 + 时长越界 + 缺 cut_reason + 与上一镜同主体 + 悬空接力
        Shot(id="shot_scene_001_001", scene_id="scene_001", order=1, duration_sec=2,
             subject="齐夏面部", chain_from=99),
        Shot(id="shot_scene_001_002", scene_id="scene_001", order=2, duration_sec=6,
             subject="齐夏面部", chain_from=1),
    ])
    issues = " ".join(_director()._validate_continuity([bd]))
    assert "reference_group" in issues        # 多镜无分组
    assert "超出生成器可行区间" in issues       # 2s 越界
    assert "cut_reason" in issues              # 缺切镜理由
    assert "同一主体" in issues                 # 重复特写
    assert "指向不存在的镜头" in issues          # 接力悬空


def test_director_validate_requires_camera_path_for_moving_shots():
    """运动镜头没写轨迹 = 模型只能自己乱动，必须拦下来（固定机位不受约束）。"""
    bd = SceneBreakdown(scene_id="scene_001", shots=[
        Shot(id="shot_scene_001_000", scene_id="scene_001", order=0, duration_sec=8,
             reference_group="room", cut_reason="起点",
             camera=CameraMovement(type="dolly", speed="slow")),          # 缺 path
        Shot(id="shot_scene_001_001", scene_id="scene_001", order=1, duration_sec=8,
             subject="座钟", reference_group="room", cut_reason="视点转移",
             camera=CameraMovement(type="static")),                        # 固定机位，无需 path
    ])
    issues = " ".join(_director()._validate_continuity([bd]))
    assert "camera_path" in issues
    assert "shot_scene_001_001" not in issues       # 固定机位不报


def test_director_validate_accepts_good_plan():
    bd = SceneBreakdown(scene_id="scene_001", shots=[
        Shot(id="shot_scene_001_000", scene_id="scene_001", order=0, duration_sec=8,
             reference_group="room", cut_reason="起点"),
        Shot(id="shot_scene_001_001", scene_id="scene_001", order=1, duration_sec=8,
             subject="对话交锋", reference_group="room", chain_from=0, cut_reason="对话单元切换"),
    ])
    assert _director()._validate_continuity([bd]) == []


# ---------- 摄影指导 ----------


def test_language_for_follows_provider_dialect():
    assert language_for("cogvideo", "zh-CN") == "zh"
    assert language_for("kling", "en-US") == "zh"
    assert language_for("sora", "zh-CN") == "en"
    assert language_for("", "zh-CN") == "zh"
    assert language_for("", "en-US") == "en"


def test_dp_reuses_anchors_verbatim_and_filters_cast_per_shot():
    script = _script()
    guide = StyleGuide(
        character_appearances={"齐夏": "黑色短发、深灰卫衣的年轻男性。", "人羊": "戴山羊头面具的黑西服男人。"},
        environment_descriptions={"密室": "密闭的方形房间，钨丝灯昏黄。"},
    )
    shots = [
        Shot(id="shot_scene_001_000", scene_id="scene_001", order=0, camera=CameraMovement()),
        Shot(id="shot_scene_001_001", scene_id="scene_001", order=1, camera=CameraMovement()),
    ]
    # LLM 只回本镜动作 + 本镜出场人物
    llm_out = {"scenes": [{"scene_id": "scene_001", "shots": [
        {"shot_id": "shot_scene_001_000", "characters": ["人羊"], "prompt_body": "镜头缓慢推近。"},
        {"shot_id": "shot_scene_001_001", "characters": ["齐夏"], "prompt_body": "齐夏翻开卡片。"},
    ]}]}
    out = _dp()._apply(shots, llm_out, script, "写实质感。", guide)
    env = "密闭的方形房间，钨丝灯昏黄"
    assert all(s.video_prompt.startswith(env) for s in out)          # 环境锚逐字复用
    assert "人羊" in out[0].video_prompt and "齐夏" not in out[0].video_prompt   # 按镜过滤
    assert "齐夏" in out[1].video_prompt and "人羊" not in out[1].video_prompt
    assert "戴山羊头面具的黑西服男人" in out[0].video_prompt         # 人物锚来自风格指南（逐字）


def test_dp_system_carries_the_five_prompt_rules():
    """图里那套提示词逻辑要固化成系统提示词，漏掉任何一条都会让画面失控。"""
    zh = dp_system(language="zh", provider_label="MiniMax", max_duration=10, has_anchors=True)
    for kw in ["虚拟无人机", "呼吸感", "光从哪个方向来", "编上号", "背景人物", "只写画面里看得见的东西",
               "不越轴", "主事件", "禁止否定句", "台词不进提示词"]:
        assert kw in zh
    en = dp_system(language="en", provider_label="Runway", max_duration=10, has_anchors=True)
    for kw in ["virtual drone", "lens breathing", "light direction", "Number the main characters",
               "no axis crossing", "never negations", "Never put spoken lines"]:
        assert kw in en


def test_director_and_art_rules_lock_adherence_budget():
    """v2/v3 对比实测的四条教训要固化：越轴、动作节拍过载、视点摇摆、身份职业词。"""
    from app.crew.director import DIRECTOR_SYSTEM

    for kw in ["运镜三禁", "越轴", "结尾不改景别", "物理过程的预算只给主事件", "第二次互动", "正向描述"]:
        assert kw in DIRECTOR_SYSTEM
    art = art_system("zh")
    for kw in ["客观机位", "视点切换", "禁止出现身份与职业词"]:
        assert kw in art


def test_dp_build_prompt_surfaces_scheduling_fields():
    """运镜轨迹/空间关系必须进入 LLM 的输入，否则写 prompt_body 时无从下手。"""
    script = _script()
    bd = SceneBreakdown(scene_id="scene_001", shots=[
        Shot(id="shot_scene_001_000", scene_id="scene_001", order=0,
             camera=CameraMovement(type="dolly", path="沿中轴推进四米后停住", height="齐胸高度"),
             spatial="齐夏1号在前景，离镜头 1.5 米", background_action="记者压低声交谈"),
    ])
    prompt = _dp()._build_prompt(script, [bd], None, "zh", False)
    assert "沿中轴推进四米后停住" in prompt
    assert "齐胸高度" in prompt
    assert "齐夏1号" in prompt
    assert "记者压低声交谈" in prompt


def test_dp_apply_backfills_missing_camera_path_once():
    """LLM 漏写运镜时用导演方案兜底；已经写过（哪怕只是复述）就不能写第二遍。"""
    script = _script()

    def _run(body: str) -> str:
        shots = [Shot(id="shot_scene_001_000", scene_id="scene_001", order=0,
                      camera=CameraMovement(type="dolly", path="从门口推进到桌前"))]
        llm_out = {"scenes": [{"scene_id": "scene_001", "shots": [
            {"shot_id": "shot_scene_001_000", "characters": ["齐夏"], "prompt_body": body},
        ]}]}
        return _dp()._apply(shots, llm_out, script, "", None)[0].video_prompt

    assert "从门口推进到桌前" in _run("齐夏抬头。")                      # 整段漏写 → 补上
    assert _run("镜头从门口推进到桌前，齐夏抬头。").count("从门口推进到桌前") == 1
    # 模型用自己的话复述轨迹（真实模型就是这么干的）时不许再追加一遍
    assert _run("摄影机缓慢向前推进，齐夏抬头。").count("运镜轨迹") == 0


def test_dp_fallback_keeps_scheduling_fields():
    """无模型回退也要带上运镜/空间/背景，不能退化成一句话提示词。"""
    script = _script()
    shots = [Shot(id="shot_scene_001_000", scene_id="scene_001", order=0,
                  camera=CameraMovement(type="orbit", path="绕人物一圈"),
                  spatial="两人相隔三米", background_action="警察维持边界")]
    res = _dp()._fallback(shots, script, "写实质感。", "zh", None)
    prompt = res.data[0].video_prompt
    assert "绕人物一圈" in prompt and "两人相隔三米" in prompt and "警察维持边界" in prompt


def test_dp_style_text_does_not_double_punctuate():
    """风格各段自带的句末标点要去掉，否则提示词末尾会出现「呼吸感。，#3a4a5a」。"""
    guide = StyleGuide(
        lighting_style="低调暖光。",
        camera_style="手持纪实，保留呼吸感。",
        color_palette=["#3a4a5a", "#6b7b8b"],
    )
    text = _dp()._style_text(guide)
    assert "。，" not in text
    assert text == "低调暖光，手持纪实，保留呼吸感，主色调 #3a4a5a、#6b7b8b"


def test_dp_without_style_guide_falls_back_to_llm_anchors():
    script = _script()
    shots = [Shot(id="shot_scene_001_000", scene_id="scene_001", order=0, camera=CameraMovement())]
    llm_out = {"scenes": [{
        "scene_id": "scene_001",
        "environment": "昏暗房间。",
        "characters": {"齐夏": "年轻男性。"},
        "shots": [{"shot_id": "shot_scene_001_000", "characters": ["齐夏"], "prompt_body": "推近。"}],
    }]}
    out = _dp()._apply(shots, llm_out, script, "写实。", None)
    assert out[0].video_prompt.startswith("昏暗房间")


# ---------- 连续性解析 ----------


def test_resolve_continuity_builds_reference_videos():
    shots = [
        {"id": "s0", "order": 0, "scene_id": "scene_001", "reference_group": "room", "chain_from": None, "video_url": "u0"},
        {"id": "s1", "order": 1, "scene_id": "scene_001", "reference_group": "room", "chain_from": 0},
        {"id": "s2", "order": 2, "scene_id": "scene_002", "reference_group": "other", "chain_from": None, "video_url": "u2"},
    ]
    resolve_continuity(shots)
    assert shots[1]["reference_videos"] == ["u0"]     # 组内锚 + 接力（去重后一条）
    assert "reference_videos" not in shots[0]          # 锚镜不引用自己
    assert "reference_videos" not in shots[2]          # 新组首镜不引用自己


# ---------- 视频 Provider：状态映射（真实踩过的字段/子串坑） ----------


class _FakeResp:
    def __init__(self, data: dict):
        self._data = data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._data


def _monkeypatch_client(monkeypatch, module, data: dict) -> None:
    class _FakeClient:
        def __init__(self, *a, **k) -> None: ...
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a) -> bool:
            return False

        async def get(self, *a, **k) -> _FakeResp:
            return _FakeResp(data)

        async def post(self, *a, **k) -> _FakeResp:
            return _FakeResp(data)

    monkeypatch.setattr(module.httpx, "AsyncClient", _FakeClient)


def test_cogvideo_poll_maps_success_despite_uppercase_field(monkeypatch):
    """智谱：状态字段是 task_status、值为大写、结果字段是 video_result（单数）。"""
    import app.video.providers.cogvideo as cog
    _monkeypatch_client(monkeypatch, cog, {"task_status": "SUCCESS", "video_result": [{"url": "http://x/a.mp4"}]})
    st = asyncio.run(cog.CogVideoProvider(api_key="k").poll_job("t1"))
    assert st.status == "succeeded"
    assert st.video_url == "http://x/a.mp4"


def test_minimax_poll_unwraps_nested_task_and_success_substring(monkeypatch):
    """MiniMax：任务对象嵌在 task 下；'succeeded' 不含子串 'success'，必须能正确映射。"""
    import app.video.providers.minimax as mm
    _monkeypatch_client(monkeypatch, mm, {"task": {"status": "succeeded", "content": {"url": "http://x/b.mp4"}}})
    st = asyncio.run(mm.MiniMaxProvider(api_key="k").poll_job("t2"))
    assert st.status == "succeeded"
    assert st.video_url == "http://x/b.mp4"


def test_minimax_poll_maps_processing_to_generating(monkeypatch):
    import app.video.providers.minimax as mm
    _monkeypatch_client(monkeypatch, mm, {"task": {"status": "Processing"}})
    st = asyncio.run(mm.MiniMaxProvider(api_key="k").poll_job("t3"))
    assert st.status == "generating"
    assert st.video_url is None


# ---------- 提交时兜底：台词剥除 + 参考解析 ----------


def test_strip_spoken_quotes_removes_dialogue_but_keeps_signs():
    """说话动词后的引用是台词，必须剥掉（假说话问题）；招牌/字幕类引用不能误伤。"""
    body = "小赵快步迎上，开口报告：「死者从七楼摔下。」苏砚点头。"
    assert "死者从七楼摔下" not in _strip_spoken_quotes(body)
    assert "苏砚点头" in _strip_spoken_quotes(body)
    sign = "警戒带上写着「禁止入内」三个字，雨丝不断。"
    assert _strip_spoken_quotes(sign) == sign


def test_dp_apply_strips_quoted_dialogue_from_prompt_body():
    """DP 组装最终提示词时也要过一遍台词兜底，引用台词不能漏进成片提示词。"""
    script = _script()
    shots = [Shot(id="shot_scene_001_000", scene_id="scene_001", order=0,
                  camera=CameraMovement(type="static"))]
    llm_out = {"scenes": [{"scene_id": "scene_001", "shots": [
        {"shot_id": "shot_scene_001_000", "characters": ["齐夏"],
         "prompt_body": "齐夏站在门口，开口说道：「你终于来了。」然后抬头。"},
    ]}]}
    out = _dp()._apply(shots, llm_out, script, "", None)[0].video_prompt
    assert "你终于来了" not in out
    assert "然后抬头" in out


def test_resolve_submission_references_chains_videos_and_fills_images():
    """提交时解析：前镜成片接力（chain_from / reference_group）+ 定妆图回填。"""
    script = _script()
    plan = [
        {"id": "shot_scene_001_000", "scene_id": "scene_001", "order": 0,
         "reference_group": "ext_01", "chain_from": None},
        {"id": "shot_scene_001_001", "scene_id": "scene_001", "order": 1,
         "reference_group": "ext_01", "chain_from": 0},
    ]
    registry = {"密室": "http://img/env", "齐夏": "http://img/charA"}

    refs = resolve_submission_references(
        shot_id="shot_scene_001_001", shot_plan=plan,
        completed_urls={"shot_scene_001_000": "http://v/0.mp4"},
        image_registry=registry, script=script,
    )
    # 接力：镜 2 拿到镜 1 的成片；镜 1 自己（无更早成片）为空。
    assert refs["reference_videos"] == ["http://v/0.mp4"]
    # 定妆图：场景环境图在前、人物图按出场顺序在后。
    assert refs["reference_images"] == ["http://img/env", "http://img/charA"]

    first = resolve_submission_references(
        shot_id="shot_scene_001_000", shot_plan=plan,
        completed_urls={}, image_registry=registry, script=script,
    )
    assert first["reference_videos"] == []
    assert first["reference_images"] == ["http://img/env", "http://img/charA"]


# ---------- 成片质检 + 有界重 roll ----------


def test_qa_check_aggregates_fatal_frames_and_skips_without_frames(monkeypatch):
    """致命问题才 FAIL、逐帧聚合；抽帧失败降级为 skipped，绝不阻断任务。"""
    from app.video import qa

    class FakeVision:
        available = True

        def __init__(self, answers: list[str]) -> None:
            self.answers = list(answers)

        def ask(self, image_url: str, question: str) -> str:
            return self.answers.pop(0)

    monkeypatch.setattr(qa, "extract_frames", lambda url, count=5: ["data:a", "data:b", "data:c"])
    res = qa.qa_check("http://v", FakeVision([
        "VERDICT: PASS\nISSUE: none",
        "VERDICT: FAIL\nISSUE: 带子从肩膀穿过身体",
        "VERDICT: PASS\nISSUE: none",
    ]))
    assert res["verdict"] == "fail"
    assert res["frames"] == 3
    assert "带子从肩膀穿过身体" in res["issues"][0]

    monkeypatch.setattr(qa, "extract_frames", lambda url, count=5: [])
    assert qa.qa_check("http://v", FakeVision([]))["verdict"] == "skipped"

    # 解析不到判定时保守按通过（避免误判引发无意义的重 roll）
    assert qa._parse_answer("模型输出无法解析") == (True, "（未能解析判定，按通过处理）")


def test_reroll_if_needed_bounded_and_records_verdict(monkeypatch):
    """不合格且有预算 → 同参数重 roll（qa_attempt+1）；预算用尽 → 留备注不重 roll；合格 → 不动。"""
    from types import SimpleNamespace

    from app.video import qa

    def make_store(params: dict):
        created: list[dict] = []
        updates: list[dict] = []

        job = SimpleNamespace(
            id="j1", project_id="p", shot_id="s", provider="minimax", model="MiniMax-H3",
            prompt="P", params=params, version_id="v", cost_estimate=0.36,
            status="succeeded", video_url="http://v/0.mp4",
        )
        store = SimpleNamespace(
            get_video_job=lambda job_id: job,
            update_video_job=lambda job_id, **fields: updates.append(fields),
            create_video_job=lambda **kw: (created.append(kw), SimpleNamespace(id="j2"))[1],
        )
        return store, created, updates

    monkeypatch.setattr(qa, "qa_check", lambda url: {"verdict": "fail", "issues": ["第2帧：手穿模"], "frames": 5})
    submitted: list[str] = []
    submit = lambda job: submitted.append(job.id)  # noqa: E731

    # 第 0 次：不合格且有预算 → 重 roll
    store, created, updates = make_store({"duration_sec": 8})
    new_id = qa.reroll_if_needed("j1", {"status": "succeeded"}, store=store,
                                 submit=submit, max_reroll=1)
    assert new_id == "j2" and submitted == ["j2"]
    assert created[0]["params"]["qa_attempt"] == 1
    assert created[0]["prompt"] == "P" and created[0]["shot_id"] == "s"

    # 第 1 次（预算用尽）：不再重 roll，写 error_message 备注
    store, created, updates = make_store({"duration_sec": 8, "qa_attempt": 1})
    new_id = qa.reroll_if_needed("j1", {"status": "succeeded"}, store=store,
                                 submit=submit, max_reroll=1)
    assert new_id is None and not created
    assert "QA 未通过" in updates[-1]["error_message"]

    # 合格：什么都不做，但 verdict 已记录
    monkeypatch.setattr(qa, "qa_check", lambda url: {"verdict": "pass", "issues": [], "frames": 5})
    store, created, updates = make_store({"duration_sec": 8})
    assert qa.reroll_if_needed("j1", {"status": "succeeded"}, store=store,
                               submit=submit, max_reroll=1) is None
    assert not created and updates[0]["params"]["qa"]["verdict"] == "pass"
