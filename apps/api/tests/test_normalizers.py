"""Normalizer tests: free-form LLM values should never raise."""
from __future__ import annotations

import pytest

from app.schemas import (
    Adaptation,
    AdaptationNotes,
    Character,
    Location,
    Script,
    Source,
    normalize_adaptation_type,
    normalize_fidelity,
    normalize_id,
    normalize_role,
)


def test_normalize_role_aliases():
    assert normalize_role("主角") == "protagonist"
    assert normalize_role("反派") == "antagonist"
    assert normalize_role("hero") == "protagonist"
    assert normalize_role("villain") == "antagonist"
    assert normalize_role("导师") == "mentor"
    assert normalize_role("配角") == "supporting"


def test_normalize_role_real_llm_outputs():
    """These are the exact shapes that crashed the user's pipeline."""
    assert normalize_role("护士") == "supporting"
    assert normalize_role("护士角色") == "supporting"
    assert normalize_role("医院护士") == "supporting"
    assert normalize_role("医生") == "supporting"
    assert normalize_role("警察") == "supporting"
    assert normalize_role("旁白") == "other"
    assert normalize_role("narrator") == "other"


def test_normalize_role_unknown_falls_back_to_other():
    assert normalize_role("雨夜的访客") == "other"
    assert normalize_role("???") == "other"


def test_normalize_role_none_and_empty():
    assert normalize_role(None) is None
    assert normalize_role("") is None
    assert normalize_role("   ") is None


def test_normalize_role_passes_through_known_enums():
    assert normalize_role("protagonist") == "protagonist"
    assert normalize_role("antagonist") == "antagonist"
    assert normalize_role("supporting") == "supporting"
    assert normalize_role("mentor") == "mentor"
    assert normalize_role("foil") == "foil"
    assert normalize_role("other") == "other"


def test_character_accepts_free_form_role():
    """The real failure path: an LLM returns role='护士'."""
    c = Character(
        id="char_nurse",
        name="护士",
        role="护士",  # type: ignore[arg-type]
    )
    assert c.role == "supporting"


def test_adaptation_notes_accepts_free_form_fidelity():
    n = AdaptationNotes(reason="压缩叙事", fidelity="忠实改编")
    assert n.fidelity == "faithful"

    n2 = AdaptationNotes(reason="新加桥段", fidelity="原创")
    assert n2.fidelity == "invented"


def test_adaptation_accepts_free_form_type():
    a = Adaptation(type="短剧")
    assert a.type == "short_drama"

    a2 = Adaptation(type="电影")
    assert a2.type == "film"

    a3 = Adaptation(type="舞台剧")
    assert a3.type == "stage"


def test_normalize_fidelity_known_and_unknown():
    assert normalize_fidelity("faithful") == "faithful"
    assert normalize_fidelity("compressed") == "compressed"
    assert normalize_fidelity("reordered") == "reordered"
    assert normalize_fidelity("merged") == "merged"
    assert normalize_fidelity("invented") == "invented"
    assert normalize_fidelity("忠实") == "faithful"
    assert normalize_fidelity("压缩") == "compressed"
    # unknown → safe default
    assert normalize_fidelity("???") == "compressed"
    assert normalize_fidelity(None) is None
    assert normalize_fidelity("") is None


def test_normalize_adaptation_type_known_and_unknown():
    assert normalize_adaptation_type("series") == "series"
    assert normalize_adaptation_type("短剧") == "short_drama"
    assert normalize_adaptation_type("电视剧") == "series"
    assert normalize_adaptation_type("电影") == "film"
    assert normalize_adaptation_type("话剧") == "stage"
    assert normalize_adaptation_type("???") == "other"
    assert normalize_adaptation_type(None) == "other"


def test_full_script_assembly_does_not_raise_on_free_form_inputs():
    """End-to-end: assemble a Script with LLM-shaped values everywhere."""
    from app.schemas import Scene

    s = Script(
        title="t",
        version="1.0",
        language="zh-CN",
        adaptation=Adaptation(type="短剧", target_format="3 分钟", tone="suspense"),
        source=Source(chapter_count=3, chapter_ids=["chapter_001", "chapter_002", "chapter_003"]),
        logline="一句话故事，足够长以满足校验。",
        characters=[
            Character(id="char_a", name="林屿", role="protagonist"),
            Character(id="char_b", name="来客", role="antagonist"),
            Character(id="char_c", name="护士", role="护士"),
        ],
        locations=[],
        scenes=[
            Scene(
                id="scene_001",
                title="t",
                chapter_refs=["chapter_001"],
                location_id="loc_x",
                characters=["char_a"],
                purpose="p",
                conflict="c",
            )
        ],
    )
    assert s.adaptation.type == "short_drama"
    roles = {c.role for c in s.characters}
    assert "protagonist" in roles
    assert "supporting" in roles


def test_normalize_id_examples():
    assert normalize_id("white_tower", "loc") == "loc_white_tower"
    assert normalize_id("loc_clinic", "loc") == "loc_clinic"
    assert normalize_id("Lin-Yu", "char") == "char_lin_yu"
    assert normalize_id("Char-Lin-Yu", "char") == "char_lin_yu"
    assert normalize_id("Scene 1", "scene") == "scene_001"
    assert normalize_id("scene 42", "scene") == "scene_042"
    assert normalize_id("scene_5", "scene") == "scene_005"
    assert normalize_id("scene 1234", "scene") == "scene_1234"
    assert normalize_id("", "loc", fallback="main") == "loc_main"
    assert normalize_id(None, "char", fallback="protagonist") == "char_protagonist"


def test_location_id_from_llm_shaped_value():
    loc = Location(id="white_tower", name="白塔")
    assert loc.id == "loc_white_tower"


def test_character_id_from_llm_shaped_value():
    ch = Character(id="Char-Lin-Yu", name="林屿", role="protagonist")
    assert ch.id == "char_lin_yu"


def test_dialogue_speaker_normalised():
    from app.schemas import DialogueLine

    line = DialogueLine(speaker="Lin-Yu", line="台词")
    assert line.speaker == "char_lin_yu"


def test_scene_normalises_everything():
    from app.schemas import Scene

    s = Scene(
        id="Scene 1",
        title="t",
        chapter_refs=["chapter_001"],
        location_id="white_tower",
        characters=["Lin-Yu"],
        purpose="p",
        conflict="c",
    )
    assert s.id == "scene_001"
    assert s.location_id == "loc_white_tower"
    assert s.characters == ["char_lin_yu"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
