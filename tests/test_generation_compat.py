# =====================================================================
# test_generation_compat.py —— ScenePlan 容错回归：deepseek 实测输出形态
#
# 样本来自《骆驼祥子》第 3–4 章实测中真实失败的一次生成：
# action / dialogue 是字符串（schema 要求数组）、动作节拍用 description 键。
# 当时的结果是 10 个校验错误 → 整体回退兜底模板。
# =====================================================================

from __future__ import annotations

from app.pipeline.generation import ScenePlan

_SAMPLE = {
    "scenes": [
        {
            "id": "scene_01",
            "title": "黑夜抉择",
            "purpose": "祥子决定不放弃骆驼，迈出逃亡第一步。",
            "conflict": "逃命要求轻装，但骆驼是他仅剩的财产。",
            "action": "祥子跑出二三十步，突然停住，回头望向黑暗中的骆驼；他弯腰捡起地上的一根麻绳，攥紧；转身走向骆驼，抓住驼鼻绳，用力拉起。",
            "dialogue": "",
            "beats": [
                {"type": "action", "description": "黑夜旷野，祥子跑出二三十步，突然刹住脚，喘着粗气回头。"},
                {"type": "action", "description": "他低头看见地上有一根麻绳，弯腰拾起，在手里攥了攥。"},
            ],
        },
        {
            "id": "scene_04",
            "title": "鸡鸣惊醒",
            "purpose": "一声鸡鸣把祥子惊醒，他数清骆驼，想起卖驼买车的主意。",
            "conflict": "他极度疲惫，但鸡鸣意味着机会。",
            "action": "祥子猛地睁眼，听见鸡鸣；他摸骆驼，数清三匹；然后猛地站起，扯起骆驼就走。",
            "dialogue": "祥子（低声，咬牙）：「凭什么？」",
            "beats": [
                {"type": "action", "description": "黑暗中，祥子猛地睁眼，一声清晰的鸡鸣划破寂静。"},
                {"type": "dialogue", "speaker": "祥子", "line": "凭什么？", "emotion": "愤怒、不甘"},
            ],
        },
    ]
}


def test_sceneplan_tolerates_string_action_and_dialogue():
    plan = ScenePlan.model_validate(_SAMPLE)
    s1 = plan.scenes[0]
    # 字符串 action 按分号规整为数组
    assert isinstance(s1.action, list) and len(s1.action) == 3
    assert s1.action[0].startswith("祥子跑出二三十步")
    # 空字符串 dialogue → 空数组
    assert s1.dialogue == []
    s4 = plan.scenes[1]
    # 「角色（情绪）：『台词』」字符串解析成对白对象
    d = s4.dialogue[0]
    assert d["speaker"] == "祥子" and d["emotion"] == "低声，咬牙" and "凭什么" in d["line"]


def test_beat_description_alias_not_silently_empty():
    """description 键的节拍必须映射到 text，否则节拍流会静默变空。"""
    plan = ScenePlan.model_validate(_SAMPLE)
    beats = plan.scenes[0].beats
    assert len(beats) == 2
    assert beats[0].type == "action" and beats[0].text.startswith("黑夜旷野")
