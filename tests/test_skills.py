# =====================================================================
# test_skills.py —— 技能加载器
#
# 覆盖：frontmatter 解析、渐进披露（目录 vs 正文）、模板渲染（变量/条件块）、
# 缺变量必须报错（防漂移），以及现有技能是否都能正常解析。
# =====================================================================

from __future__ import annotations

import pytest

from app.skills import (
    SKILLS_DIR,
    load_skill,
    list_skills,
    render,
    render_skill,
    skill_index,
)
from app.skills.loader import SkillNotFound


# ---------- 现有技能 ----------


def test_all_bundled_skills_parse():
    """仓库里的每个 SKILL.md 都要能解析；坏一个会让对应角色直接拿不到提示词。"""
    skills = list_skills()
    names = {s.name for s in skills}
    assert {"director-breakdown", "video-prompt-zh", "video-prompt-en", "style-guide"} <= names
    for s in skills:
        assert s.description.strip(), f"{s.name} 缺少 description"
        assert load_skill(s.name).body.strip(), f"{s.name} 正文为空"


def test_skill_index_is_metadata_only():
    """渐进披露第一级：目录只给 name + description，不含正文。"""
    idx = skill_index()
    assert "director-breakdown" in idx
    # 正文里的细节不该出现在目录里
    assert "先戏剧，后语法" not in idx


def test_director_skill_keeps_the_drama_rules():
    """导演技能搬到文件后，那套方法论一条都不能丢。"""
    body = render_skill("director-breakdown")
    for kw in ["先戏剧，后语法", "三工作规则", "细节律", "最终画面", "五锚点",
               "运镜必须有动机", "节奏阶梯", "不豁免", "越轴", "正向描述"]:
        assert kw in body, f"导演技能缺了「{kw}」"


def test_video_prompt_skills_keep_the_eleven_rules():
    zh = render_skill(
        "video-prompt-zh", provider_label="MiniMax", duration_note="6 秒",
        lang_rule="中文", json_note="中文", has_anchors=True,
    )
    for kw in ["虚拟无人机", "呼吸感", "光从哪个方向来", "编上号", "背景人物",
               "只写画面里看得见的东西", "不越轴", "主事件", "禁止否定句",
               "台词不进提示词", "最终画面收尾", "情绪只写身体", "占位词"]:
        assert kw in zh, f"中文摄影技能缺了「{kw}」"

    en = render_skill(
        "video-prompt-en", provider_label="Runway", duration_note="10s",
        lang_rule="English", json_note="English", has_anchors=True,
    )
    assert "prompt_body" in en
    assert len(en) > len(zh)  # 英文正文更长


def test_style_guide_skill_keeps_the_anchor_rules():
    body = render_skill("style-guide", lang_note="中文")
    for kw in ["写实人物公式", "环境会表演", "环境压力", "客观机位", "禁止出现身份与职业词",
               "绝对不要列举具体运镜方式"]:
        assert kw in body, f"美术技能缺了「{kw}」"


# ---------- 模板渲染 ----------


def test_render_replaces_variables():
    out = render("目标：{{provider}}，时长 {{sec}} 秒", {"provider": "MiniMax", "sec": 6})
    assert out == "目标：MiniMax，时长 6 秒"


def test_render_handles_json_single_braces():
    """提示词里全是 JSON 示例——单花括号必须原样保留，不能被当占位符。"""
    text = '输出：{"scenes": [{"scene_id": "scene_001"}]}，模型 {{label}}'
    out = render(text, {"label": "X"})
    assert '{"scenes": [{"scene_id": "scene_001"}]}' in out
    assert "模型 X" in out


def test_render_if_block_true_and_false():
    text = "前{% if has_anchors %}有锚{% else %}无锚{% endif %}后"
    assert render(text, {"has_anchors": True}) == "前有锚后"
    assert render(text, {"has_anchors": False}) == "前无锚后"


def test_render_if_block_without_else():
    text = "前{% if flag %}可见{% endif %}后"
    assert render(text, {"flag": True}) == "前可见后"
    assert render(text, {"flag": False}) == "前后"


def test_render_treats_empty_string_as_false():
    assert render("{% if x %}有{% else %}无{% endif %}", {"x": "  "}) == "无"


def test_render_raises_on_missing_variable():
    """缺变量必须报错，不能静默留一个 {{x}} 在提示词里——那是漂移。"""
    with pytest.raises(KeyError) as exc:
        render("值：{{missing}}", {})
    assert "missing" in str(exc.value)


def test_render_raises_on_missing_condition_variable():
    with pytest.raises(KeyError):
        render("{% if nope %}x{% endif %}", {})


# ---------- 加载器边界 ----------


def test_unknown_skill_raises():
    with pytest.raises(SkillNotFound):
        load_skill("no-such-skill")


def test_path_traversal_is_rejected():
    with pytest.raises(SkillNotFound):
        load_skill("../../etc/passwd")


def test_skill_dir_is_inside_app():
    assert SKILLS_DIR.name == "skills"
    assert SKILLS_DIR.parent.name == "app"
