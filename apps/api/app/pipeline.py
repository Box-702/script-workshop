"""8-stage AI pipeline that produces a ScriptDocument from raw chapter text."""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .adaptation_profiles import adaptation_profile_for, adaptation_profile_prompt
from .chunking import ChapterSplit
from .providers.base import LLMProvider, Stage, get_provider
from .runlog import StageTimer
from .schemas import (
    Adaptation,
    AdaptationNotes,
    Character,
    DialogueLine,
    Location,
    Scene,
    Script,
    ScriptBeat,
    ScriptDocument,
    Source,
)
from .validation import validate_script
from .yaml_io import to_yaml

log = logging.getLogger(__name__)


STAGE_ORDER: tuple[Stage, ...] = (
    Stage.SUMMARY,
    Stage.BIBLE,
    Stage.CHARACTERS,
    Stage.SCENE_PLAN,
    Stage.DIALOGUE,
    Stage.REPAIR,
)

class PipelineCallbacks:
    def __init__(self) -> None:
        self.current_step: str = ""
        self.progress: int = 0

    def update(self, step: str, progress: int) -> None:
        self.current_step = step
        self.progress = progress


# ---------- per-stage helpers ----------


def _stage_summary(provider: LLMProvider, chapter: ChapterSplit) -> dict[str, Any]:
    prompt = (
        f"CHAPTER ID: {chapter.chapter_id}\n"
        f"CHAPTER TITLE: {chapter.title}\n\n"
        f"CHAPTER CONTENT:\n{chapter.content}"
    )
    schema = {
        "type": "object",
        "properties": {
            "chapter_id": {"type": "string"},
            "summary": {"type": "string"},
            "major_events": {"type": "array", "items": {"type": "string"}},
            "characters": {"type": "array", "items": {"type": "string"}},
            "locations": {"type": "array", "items": {"type": "string"}},
            "conflicts": {"type": "array", "items": {"type": "string"}},
            "turning_points": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["chapter_id", "summary"],
    }
    return provider.generate_structured(prompt, schema, stage=Stage.SUMMARY)


def _stage_bible(
    provider: LLMProvider, summaries: list[dict], profile: dict[str, Any], language: str
) -> dict[str, Any]:
    text = json.dumps(summaries, ensure_ascii=False)
    prompt = (
        "Synthesize a Story Bible from these chapter summaries. Provide title, logline, "
        "genre, themes, setting, central conflict, characters, locations, timeline. "
        "Follow the adaptation profile and write user-facing fields in the output language.\n\n"
        f"ADAPTATION PROFILE:\n{adaptation_profile_prompt(profile, language=language)}\n\n"
        f"CHAPTER SUMMARIES:\n{text}"
    )
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "logline": {"type": "string"},
            "genre": {"type": "string"},
            "themes": {"type": "array", "items": {"type": "string"}},
            "setting": {"type": "string"},
            "central_conflict": {"type": "string"},
            "characters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "role": {"type": "string"},
                    },
                    "required": ["id", "name"],
                },
            },
            "locations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                    },
                    "required": ["id", "name"],
                },
            },
            "timeline": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "logline"],
    }
    return provider.generate_structured(prompt, schema, stage=Stage.BIBLE)


def _stage_characters(provider: LLMProvider, bible: dict, summaries: list[dict]) -> dict[str, Any]:
    prompt = (
        "Refine the character roster from the Story Bible and chapter summaries. "
        "Each character MUST have an id like char_xxx and a name.\n\n"
        f"BIBLE:\n{json.dumps(bible, ensure_ascii=False)}\n\n"
        f"SUMMARIES:\n{json.dumps(summaries, ensure_ascii=False)}"
    )
    schema = {
        "type": "object",
        "properties": {
            "characters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "role": {"type": "string"},
                        "goal": {"type": "string"},
                        "motivation": {"type": "string"},
                        "personality": {"type": "string"},
                        "arc": {"type": "string"},
                        "speech_style": {"type": "string"},
                    },
                    "required": ["id", "name"],
                },
            }
        },
        "required": ["characters"],
    }
    return provider.generate_structured(prompt, schema, stage=Stage.CHARACTERS)


def _stage_scene_plan(
    provider: LLMProvider,
    bible: dict,
    characters: list[dict],
    chapters: list[ChapterSplit],
    profile: dict[str, Any],
    language: str,
) -> dict[str, Any]:
    chapter_ids = [c.chapter_id for c in chapters]
    prompt = (
        "Plan scenes for the script. Each scene must reference at least one chapter id "
        "from CHAPTERS, must reference at least one character id from CHARACTERS, and "
        "must define a purpose and a conflict. Follow the adaptation profile instead "
        "of using a generic screenplay structure. Write user-facing fields in the "
        "output language.\n\n"
        f"ADAPTATION PROFILE:\n{adaptation_profile_prompt(profile, language=language)}\n\n"
        f"CHAPTERS:\n{json.dumps(chapter_ids)}\n"
        f"CHARACTERS:\n{json.dumps(characters, ensure_ascii=False)}\n"
        f"BIBLE:\n{json.dumps(bible, ensure_ascii=False)}"
    )
    schema = {
        "type": "object",
        "properties": {
            "scenes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "chapter_refs": {"type": "array", "items": {"type": "string"}},
                        "location": {"type": "string"},
                        "time": {"type": "string"},
                        "characters": {"type": "array", "items": {"type": "string"}},
                        "purpose": {"type": "string"},
                        "conflict": {"type": "string"},
                        "entry_state": {"type": "string"},
                        "exit_state": {"type": "string"},
                    },
                    "required": [
                        "id",
                        "chapter_refs",
                        "characters",
                        "purpose",
                        "conflict",
                    ],
                },
            }
        },
        "required": ["scenes"],
    }
    return provider.generate_structured(prompt, schema, stage=Stage.SCENE_PLAN)


def _stage_dialogue(
    provider: LLMProvider,
    scene_plan_entry: dict,
    chapter_summaries: list[dict],
    characters: list[dict],
    chapter_texts: dict[str, str],
    profile: dict[str, Any],
    language: str,
) -> dict[str, Any]:
    chap_refs = scene_plan_entry.get("chapter_refs", [])
    relevant = [s for s in chapter_summaries if s.get("chapter_id") in chap_refs]
    src = "\n\n".join(chapter_texts.get(cid, "") for cid in chap_refs)
    prompt = (
        "Generate ordered script beats, action list, and dialogue list for the following "
        "scene. Use ONLY the listed character ids as speakers. Provide emotion and "
        "subtext for each dialogue line. The beats array is the human-readable script "
        "flow: mix action, dialogue, and cue items in the order an editor should read "
        "them. Also keep action and dialogue arrays for compatibility. Write user-facing "
        "fields in the output language.\n\n"
        f"ADAPTATION PROFILE:\n{adaptation_profile_prompt(profile, language=language)}\n\n"
        f"SCENE PLAN:\n{json.dumps(scene_plan_entry, ensure_ascii=False)}\n\n"
        f"CHAPTER SUMMARIES:\n{json.dumps(relevant, ensure_ascii=False)}\n\n"
        f"CHARACTER CARDS:\n{json.dumps(characters, ensure_ascii=False)}\n\n"
        f"SOURCE TEXT (excerpt):\n{src[:3000]}"
    )
    schema = {
        "type": "object",
        "properties": {
            "action": {"type": "array", "items": {"type": "string"}},
            "dialogue": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "speaker": {"type": "string"},
                        "line": {"type": "string"},
                        "emotion": {"type": "string"},
                        "subtext": {"type": "string"},
                    },
                    "required": ["speaker", "line"],
                },
            },
            "beats": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "type": {"type": "string", "enum": ["action", "dialogue", "cue"]},
                        "text": {"type": "string"},
                        "speaker": {"type": "string"},
                        "line": {"type": "string"},
                        "emotion": {"type": "string"},
                        "subtext": {"type": "string"},
                    },
                    "required": ["type"],
                },
            },
        },
    }
    return provider.generate_structured(prompt, schema, stage=Stage.DIALOGUE)


def _clean_action(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _clean_dialogue(value: object, allowed_speakers: list[str]) -> list[DialogueLine]:
    if not isinstance(value, list):
        return []
    allowed = set(allowed_speakers)
    fallback = allowed_speakers[0] if allowed_speakers else ""
    dialogue: list[DialogueLine] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        speaker = str(item.get("speaker") or "").strip()
        if speaker not in allowed:
            speaker = fallback
        if not speaker:
            continue
        dialogue.append(
            DialogueLine(
                speaker=speaker,
                line=line,
                emotion=str(item.get("emotion") or "").strip() or None,
                subtext=str(item.get("subtext") or "").strip() or None,
            )
        )
    return dialogue


def _build_beats(
    raw_beats: object,
    *,
    action: list[str],
    dialogue: list[DialogueLine],
    allowed_speakers: list[str],
) -> list[ScriptBeat]:
    allowed = set(allowed_speakers)
    fallback = allowed_speakers[0] if allowed_speakers else ""
    beats: list[ScriptBeat] = []

    if isinstance(raw_beats, list):
        for item in raw_beats:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type") or "").strip()
            if kind not in {"action", "dialogue", "cue"}:
                kind = "dialogue" if item.get("speaker") or item.get("line") else "action"
            beat_id = f"beat_{len(beats) + 1:03d}"
            if kind == "dialogue":
                line = str(item.get("line") or item.get("text") or "").strip()
                speaker = str(item.get("speaker") or "").strip()
                if speaker not in allowed:
                    speaker = fallback
                if not line or not speaker:
                    continue
                beats.append(
                    ScriptBeat(
                        id=beat_id,
                        type="dialogue",
                        speaker=speaker,
                        line=line,
                        emotion=str(item.get("emotion") or "").strip() or None,
                        subtext=str(item.get("subtext") or "").strip() or None,
                    )
                )
                continue

            text = str(item.get("text") or item.get("line") or "").strip()
            if not text:
                continue
            beats.append(ScriptBeat(id=beat_id, type=kind, text=text))  # type: ignore[arg-type]

    if beats:
        return beats

    for text in action:
        beats.append(ScriptBeat(id=f"beat_{len(beats) + 1:03d}", type="action", text=text))
    for line in dialogue:
        beats.append(
            ScriptBeat(
                id=f"beat_{len(beats) + 1:03d}",
                type="dialogue",
                speaker=line.speaker,
                line=line.line,
                emotion=line.emotion,
                subtext=line.subtext,
            )
        )
    return beats


# ---------- public entry point ----------


def run_pipeline(
    chapters: list[ChapterSplit],
    *,
    title: str,
    adaptation_type: str,
    on_progress: PipelineCallbacks | None = None,
    provider: LLMProvider | None = None,
    language: str = "zh-CN",
    run_id: str = "",
) -> tuple[ScriptDocument, dict[str, Any]]:
    provider = provider or get_provider()
    cb = on_progress or PipelineCallbacks()
    artifacts: dict[str, Any] = {}
    profile = adaptation_profile_for(adaptation_type)
    artifacts["adaptation_profile"] = profile

    # Stage 1: chapter summaries (parallel; one OpenAI call per chapter)
    cb.update("chapter_summary", 10)
    with StageTimer(run_id, "chapter_summary"):
        max_workers = min(4, max(1, len(chapters)))
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            summary_results = list(ex.map(lambda c: _stage_summary(provider, c), chapters))
    summaries: list[dict] = []
    for ch, s in zip(chapters, summary_results, strict=True):
        s.setdefault("chapter_id", ch.chapter_id)
        s.setdefault("summary", ch.title)
        summaries.append(s)
    artifacts["summaries"] = summaries

    # Stage 2: story bible
    cb.update("story_bible", 25)
    with StageTimer(run_id, "story_bible"):
        bible = _stage_bible(provider, summaries, profile, language)
    artifacts["bible"] = bible

    # Stage 3: characters
    cb.update("character_extraction", 40)
    with StageTimer(run_id, "character_extraction"):
        chars_data = _stage_characters(provider, bible, summaries)
    characters_raw = chars_data.get("characters") or bible.get("characters") or []
    characters: list[Character] = []
    seen_ids: set[str] = set()
    for i, c in enumerate(characters_raw):
        cid = c.get("id") or f"char_unknown_{i + 1:03d}"
        if cid in seen_ids:
            cid = f"{cid}_{i + 1}"
        seen_ids.add(cid)
        characters.append(
            Character(
                id=cid,
                name=c.get("name") or f"人物{i + 1}",
                role=c.get("role"),
                goal=c.get("goal"),
                motivation=c.get("motivation"),
                personality=c.get("personality"),
                arc=c.get("arc"),
                speech_style=c.get("speech_style"),
            )
        )
    if not characters:
        # hard fallback so the script remains valid
        characters = [Character(id="char_protagonist", name="主角", role="protagonist")]
    artifacts["characters"] = [c.model_dump() for c in characters]

    # Locations: derive from bible or build a single default
    locations: list[Location] = []
    seen_locs: set[str] = set()
    for i, loc in enumerate(bible.get("locations") or []):
        lid = loc.get("id") or f"loc_loc_{i + 1:03d}"
        if lid in seen_locs:
            lid = f"{lid}_{i + 1}"
        seen_locs.add(lid)
        locations.append(Location(id=lid, name=loc.get("name") or f"地点{i + 1}"))
    if not locations:
        locations = [Location(id="loc_main", name="主要场景")]
    artifacts["locations"] = [loc.model_dump() for loc in locations]

    # Stage 4: scene plan
    cb.update("scene_planning", 55)
    with StageTimer(run_id, "scene_planning"):
        plan = _stage_scene_plan(
            provider,
            bible,
            [c.model_dump() for c in characters],
            chapters,
            profile,
            language,
        )
        scene_entries = plan.get("scenes") or []
    artifacts["scene_plan"] = scene_entries

    # Stage 5: per-scene dialogue generation (parallel; one OpenAI call per scene)
    chapter_texts = {c.chapter_id: c.content for c in chapters}
    char_id_set = {c.id for c in characters}
    loc_id_set = {loc.id for loc in locations}
    scene_count = max(1, len(scene_entries))
    cb.update("script_generation", 60)

    def _gen_one(entry: dict) -> Scene:
        out = _stage_dialogue(
            provider,
            entry,
            summaries,
            [c.model_dump() for c in characters],
            chapter_texts,
            profile,
            language,
        )
        char_list = entry.get("characters") or []
        char_list = [c for c in char_list if c in char_id_set] or [c.id for c in characters[:1]]
        loc_id = entry.get("location_id") or (
            locations[0].id if locations else "loc_main"
        )
        if loc_id not in loc_id_set:
            loc_id = locations[0].id if locations else "loc_main"

        action = _clean_action(out.get("action"))
        dialogue = _clean_dialogue(out.get("dialogue"), char_list)
        beats = _build_beats(
            out.get("beats"),
            action=action,
            dialogue=dialogue,
            allowed_speakers=char_list,
        )

        return Scene(
            id=entry.get("id") or f"scene_{len(scenes_to_results) + 1:03d}",
            title=entry.get("title") or f"第 {len(scenes_to_results) + 1} 场",
            chapter_refs=entry.get("chapter_refs") or [chapters[0].chapter_id],
            location_id=loc_id,
            time=entry.get("time"),
            characters=char_list,
            purpose=entry.get("purpose") or "推进情节。",
            conflict=entry.get("conflict") or "角色面对压力。",
            entry_state=entry.get("entry_state"),
            exit_state=entry.get("exit_state"),
            action=action,
            dialogue=dialogue,
            beats=beats,
            adaptation_notes=AdaptationNotes(
                reason="AI 自动生成", fidelity="compressed"
            ),
        )

    scenes_to_results: list[Scene] = []
    # Cap concurrency to avoid hammering the rate limit (typical OpenAI: 3-5 in flight).
    dialogue_workers = min(4, max(1, len(scene_entries)))
    with ThreadPoolExecutor(max_workers=dialogue_workers) as ex:
        futures = [ex.submit(_gen_one, entry) for entry in scene_entries]
        for done_idx, fut in enumerate(futures):
            scenes_to_results.append(fut.result())
            # Persist progress after each scene completes (best-effort granularity)
            progress = 60 + int(((done_idx + 1) / scene_count) * 30)
            cb.update(
                f"script_generation ({done_idx + 1}/{scene_count})", progress
            )
    scenes = scenes_to_results
    if not scenes:
        raise RuntimeError("scene plan produced zero scenes")
    artifacts["scenes"] = [s.model_dump() for s in scenes]

    # Stage 6: assemble + validate
    cb.update("validation", 90)
    with StageTimer(run_id, "assembly"):
        script = Script(
            title=title or bible.get("title") or "未命名故事",
            version="1.0",
            language=language or "zh-CN",
            adaptation=Adaptation(
                type=adaptation_type,  # type: ignore[arg-type]
                target_format=profile["target_format"],
                tone=profile["tone"],
            ),
            source=Source(
                chapter_count=len(chapters),
                chapter_ids=[c.chapter_id for c in chapters],
            ),
            logline=bible.get("logline") or "主角面对核心冲突。",
            themes=bible.get("themes") or [],
            characters=characters,
            locations=locations,
            scenes=scenes,
        )
        doc = ScriptDocument(script=script)

        errors = validate_script(doc.model_dump(exclude_none=True))
        artifacts["validation_errors"] = [e.model_dump() for e in errors]
    cb.update("done", 100)
    return doc, artifacts


def to_yaml_text(doc: ScriptDocument) -> str:
    return to_yaml(doc.model_dump(exclude_none=True))
