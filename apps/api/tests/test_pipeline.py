"""Sanity tests: pipeline + validation + repair + yaml roundtrip.

Pipeline tests use a fake provider that mimics OpenAI's structured output.
The real OpenAI key is NOT required — `_provider_from_options` requires one,
but `run_pipeline` itself accepts any LLMProvider implementation.
"""
from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.chunking import split_chapters
from app.db import Base, Chapter, Project
from app.pipeline import run_pipeline, to_yaml_text
from app.providers.base import LLMProvider, Stage
from app.repair import repair_yaml
from app.routers.projects import LLMRunOptions, _provider_from_options
from app.validation import validate_script
from app.yaml_io import from_yaml
from fastapi import HTTPException

NOVEL = """第一章 雨夜敲门

林屿关上诊所的灯，刚想熄掉门廊的最后一盏台灯，卷帘门外传来一阵急促的敲击声。

他犹豫了三秒，雨水正顺着门缝渗进来。

"今天已经停诊了。"他隔着门说。

门外的人没有回答，只是又敲了三下。林屿叹了口气，拉起卷帘门。

站在门外的女人浑身湿透，黑色大衣下渗出暗红色的液体。她什么也没说，径直倒进林屿怀里。

## 第二章 失忆的来客

女人醒来时，已经是第二天下午。

"你是谁？"林屿问。

"我不记得。"她盯着天花板，眼神发空。

林屿翻了翻她身上的物件——一张没写姓名的名片、一枚旧式钥匙、还有一张被水泡得模糊的合照。

"你身上有刀伤，但伤口包扎得很专业，"林屿说，"你来自一个有医疗条件的地方。"

女人闭上眼："也许吧。"

## 第三章 旧城诊所的夜晚

那一夜，诊所门外又响起雨声。

女人坐在窗边，第一次开口讲了一段话：

"我来找一个人，他三个月前从这座城市消失。"

林屿抬起头："谁？"

"我自己。"
"""


class FakeProvider(LLMProvider):
    """Deterministic fake that returns schema-valid output. No API key needed."""

    def __init__(self) -> None:
        self.calls: list[Stage] = []

    def generate_structured(
        self, prompt: str, schema: dict, *, stage: Stage
    ) -> dict[str, Any]:
        self.calls.append(stage)
        if stage == Stage.SUMMARY:
            cid = self._extract_chapter_id(prompt) or "chapter_001"
            return {
                "chapter_id": cid,
                "summary": "本章叙述核心冲突。",
                "major_events": ["事件 A", "事件 B"],
                "characters": ["林屿", "来客"],
                "locations": ["旧城诊所"],
                "conflicts": ["主角面对压力"],
                "turning_points": ["关键决定"],
            }
        if stage == Stage.BIBLE:
            return {
                "title": "雨夜来客",
                "logline": "医生雨夜救下神秘来客，被卷入身份与记忆的阴谋。",
                "genre": "suspense",
                "themes": ["信任", "身份"],
                "setting": "当代城市",
                "central_conflict": "保护自己与揭示真相之间的抉择。",
                "characters": [
                    {"id": "char_linyu", "name": "林屿", "role": "protagonist"},
                    {"id": "char_woman", "name": "来客", "role": "antagonist"},
                ],
                "locations": [{"id": "loc_clinic", "name": "旧城诊所"}],
                "timeline": ["开端", "中段", "结尾"],
            }
        if stage == Stage.CHARACTERS:
            return {
                "characters": [
                    {
                        "id": "char_linyu",
                        "name": "林屿",
                        "role": "protagonist",
                        "goal": "查明来客身份",
                        "motivation": "弥补过去误诊",
                        "personality": "克制、敏锐",
                        "arc": "从逃避到面对",
                        "speech_style": "简短、理性",
                    },
                    {
                        "id": "char_woman",
                        "name": "来客",
                        "role": "antagonist",
                        "goal": "找回自己",
                        "motivation": "被清空的记忆",
                        "personality": "警觉、寡言",
                        "arc": "逐渐拼回真相",
                        "speech_style": "句短、字字斟酌",
                    },
                ]
            }
        if stage == Stage.SCENE_PLAN:
            import re

            chaps = sorted(set(re.findall(r"chapter_\d{3,}", prompt))) or ["chapter_001"]
            return {
                "scenes": [
                    {
                        "id": f"scene_{i + 1:03d}",
                        "chapter_refs": [c],
                        "location": "旧城诊所",
                        "time": "深夜",
                        "characters": ["char_linyu", "char_woman"],
                        "purpose": f"推进 {c} 的核心情节。",
                        "conflict": "角色面对外部压力。",
                        "entry_state": "进入场景。",
                        "exit_state": "离开场景。",
                    }
                    for i, c in enumerate(chaps)
                ]
            }
        if stage == Stage.DIALOGUE:
            return {
                "action": ["雨水敲打卷帘门。"],
                "dialogue": [
                    {
                        "speaker": "char_linyu",
                        "line": "今天已经停诊了。",
                        "emotion": "疲惫",
                        "subtext": "不想再卷入麻烦。",
                    }
                ],
            }
        return {}

    @staticmethod
    def _extract_chapter_id(prompt: str) -> str | None:
        import re

        m = re.search(r"chapter_\d{3,}", prompt)
        return m.group(0) if m else None


def test_split_chapters():
    chapters = split_chapters(NOVEL)
    assert len(chapters) == 3
    assert all(c.chapter_id.startswith("chapter_") for c in chapters)


def test_split_chapters_rejects_too_few_explicit_headings():
    text = """## 第一章 开端

正文一。

## 第二章 转折

正文二。
"""
    with pytest.raises(ValueError, match="need at least 3 chapters"):
        split_chapters(text)


def test_split_chapters_rejects_empty_explicit_chapter():
    text = """## 第一章 开端

正文一。

## 第二章 空章

## 第三章 结尾

正文三。
"""
    with pytest.raises(ValueError, match="has no content"):
        split_chapters(text)


def test_pipeline_e2e_fake():
    chapters = split_chapters(NOVEL)
    fake = FakeProvider()
    doc, artifacts = run_pipeline(
        chapters,
        title="雨夜来客",
        adaptation_type="short_drama",
        provider=fake,
    )
    assert doc.script.title
    assert doc.script.source.chapter_count == 3
    assert doc.script.scenes, "scenes should not be empty"
    chapter_ids = {c.chapter_id for c in chapters}
    for s in doc.script.scenes:
        assert set(s.chapter_refs) & chapter_ids
    # all pipeline stages were invoked
    assert set(fake.calls) >= {
        Stage.SUMMARY,
        Stage.BIBLE,
        Stage.CHARACTERS,
        Stage.SCENE_PLAN,
        Stage.DIALOGUE,
    }
    errors = validate_script(doc.model_dump(exclude_none=True))
    assert not errors, f"unexpected errors: {errors}"


def test_yaml_roundtrip():
    chapters = split_chapters(NOVEL)
    doc, _ = run_pipeline(
        chapters, title="雨夜来客", adaptation_type="short_drama", provider=FakeProvider()
    )
    y = to_yaml_text(doc)
    parsed = from_yaml(y)
    assert parsed["script"]["title"] == doc.script.title
    assert len(parsed["script"]["scenes"]) == len(doc.script.scenes)


def test_repair_recovers_unknown_speaker():
    chapters = split_chapters(NOVEL)
    doc, _ = run_pipeline(
        chapters, title="雨夜来客", adaptation_type="short_drama", provider=FakeProvider()
    )
    y = to_yaml_text(doc)
    if not doc.script.scenes or not doc.script.scenes[0].dialogue:
        pytest.skip("no dialogue generated")
    real_speaker = doc.script.scenes[0].dialogue[0].speaker
    bad = y.replace(real_speaker, "char_typo_xxx", 1)
    fixed, changes = repair_yaml(bad)
    assert any("snapped" in c for c in changes), changes
    parsed = from_yaml(fixed)
    errs = validate_script(parsed)
    assert not errs, errs


def test_validation_catches_duplicate_reference_ids():
    chapters = split_chapters(NOVEL)
    doc, _ = run_pipeline(
        chapters, title="雨夜来客", adaptation_type="short_drama", provider=FakeProvider()
    )
    data = doc.model_dump(exclude_none=True)
    data["script"]["characters"].append(dict(data["script"]["characters"][0]))
    data["script"]["locations"].append(dict(data["script"]["locations"][0]))
    data["script"]["source"]["chapter_ids"].append(data["script"]["source"]["chapter_ids"][0])

    errors = validate_script(data)
    messages = {e.message for e in errors}
    assert "character ids must be unique" in messages
    assert "location ids must be unique" in messages
    assert "chapter ids must be unique" in messages


def test_repair_handles_invalid_yaml_without_raising():
    fixed, changes = repair_yaml("script:\n  title: [broken")
    assert fixed == "script:\n  title: [broken"
    assert any("YAML parse error" in change for change in changes)


def test_chapter_ids_are_unique_per_project_not_global():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as db:
        db.add_all(
            [
                Project(id="proj_a", title="A", adaptation_type="short_drama"),
                Project(id="proj_b", title="B", adaptation_type="short_drama"),
                Chapter(
                    id="chapter_001",
                    project_id="proj_a",
                    title="第一章",
                    content="A",
                    order_index=0,
                ),
                Chapter(
                    id="chapter_001",
                    project_id="proj_b",
                    title="第一章",
                    content="B",
                    order_index=0,
                ),
            ]
        )
        db.commit()

        assert db.query(Chapter).count() == 2


def test_provider_requires_openai_api_key():
    with pytest.raises(HTTPException) as exc:
        _provider_from_options(LLMRunOptions(provider="openai", openai_api_key=""))
    assert exc.value.status_code == 400
    assert "API key" in exc.value.detail


def test_provider_rejects_mock_provider():
    with pytest.raises(HTTPException) as exc:
        _provider_from_options(LLMRunOptions(provider="mock", openai_api_key="sk-x"))
    assert exc.value.status_code == 400
    assert "unsupported" in exc.value.detail


def test_provider_builds_with_key():
    from app.providers.openai_provider import OpenAIProvider

    p = _provider_from_options(
        LLMRunOptions(
            provider="openai",
            openai_api_key="sk-test",
            openai_base_url="https://api.openai.com/v1",
            openai_model="gpt-4o-mini",
        )
    )
    assert isinstance(p, OpenAIProvider)
