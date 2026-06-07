from __future__ import annotations

from collections import Counter
from typing import Any

from .. import db as dbm

IDENTIFIED_LISTS = {
    "characters": "id",
    "locations": "id",
    "scenes": "id",
    "beats": "id",
}

FIELD_LABELS = {
    "title": "标题",
    "version": "版本",
    "language": "语言",
    "adaptation": "改编设置",
    "source": "来源",
    "chapter_count": "章节数",
    "chapter_ids": "来源章节",
    "logline": "一句话梗概",
    "themes": "主题",
    "characters": "角色",
    "locations": "地点",
    "scenes": "场景",
    "id": "ID",
    "name": "名称",
    "role": "类型",
    "goal": "目标",
    "motivation": "动机",
    "personality": "性格",
    "relationship": "关系",
    "arc": "人物弧光",
    "speech_style": "说话风格",
    "description": "描述",
    "chapter_refs": "来源章节",
    "location_id": "地点",
    "time": "时间",
    "purpose": "目的",
    "conflict": "冲突",
    "entry_state": "入场状态",
    "exit_state": "离场状态",
    "action": "动作",
    "dialogue": "对白",
    "beats": "剧本流",
    "type": "节拍类型",
    "text": "内容",
    "speaker": "说话人",
    "line": "台词",
    "emotion": "情绪",
    "subtext": "潜台词",
    "adaptation_notes": "改编说明",
    "reason": "原因",
    "fidelity": "忠实度",
}


def compare_script_versions(
    from_version: dbm.ScriptVersion,
    to_version: dbm.ScriptVersion,
) -> dict[str, Any]:
    before = from_version.json_content
    after = to_version.json_content
    items: list[dict[str, Any]] = []
    before_script = before.get("script") if isinstance(before, dict) else before
    after_script = after.get("script") if isinstance(after, dict) else after
    _diff_value(before_script, after_script, ["script"], items, before, after)
    summary = dict(Counter(item["section"] for item in items))
    return {
        "project_id": from_version.project_id,
        "from_version_id": from_version.id,
        "to_version_id": to_version.id,
        "items": items,
        "summary": summary,
    }


def _diff_value(
    before: Any,
    after: Any,
    path: list[str],
    items: list[dict[str, Any]],
    before_root: dict[str, Any],
    after_root: dict[str, Any],
) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            next_path = [*path, str(key)]
            if key not in before:
                _append_item(items, next_path, "added", None, after[key], before_root, after_root)
            elif key not in after:
                _append_item(
                    items,
                    next_path,
                    "removed",
                    before[key],
                    None,
                    before_root,
                    after_root,
                )
            else:
                _diff_value(before[key], after[key], next_path, items, before_root, after_root)
        return

    identity_key = _identity_key_for_path(path)
    if isinstance(before, list) and isinstance(after, list) and identity_key:
        _diff_identified_list(before, after, identity_key, path, items, before_root, after_root)
        return

    if before != after:
        _append_item(items, path, "changed", before, after, before_root, after_root)


def _diff_identified_list(
    before: list[Any],
    after: list[Any],
    identity_key: str,
    path: list[str],
    items: list[dict[str, Any]],
    before_root: dict[str, Any],
    after_root: dict[str, Any],
) -> None:
    before_map = _map_by_id(before, identity_key)
    after_map = _map_by_id(after, identity_key)
    for item_id in sorted(set(before_map) | set(after_map)):
        next_path = [*path, item_id]
        if item_id not in before_map:
            _append_item(
                items,
                next_path,
                "added",
                None,
                after_map[item_id],
                before_root,
                after_root,
            )
        elif item_id not in after_map:
            _append_item(
                items,
                next_path,
                "removed",
                before_map[item_id],
                None,
                before_root,
                after_root,
            )
        else:
            _diff_value(
                before_map[item_id],
                after_map[item_id],
                next_path,
                items,
                before_root,
                after_root,
            )


def _map_by_id(items: list[Any], key: str) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        item_id = str(item.get(key) or "").strip() or f"index_{index}"
        mapped[item_id] = item
    return mapped


def _identity_key_for_path(path: list[str]) -> str | None:
    if not path:
        return None
    return IDENTIFIED_LISTS.get(path[-1])


def _append_item(
    items: list[dict[str, Any]],
    path: list[str],
    change_type: str,
    before: Any,
    after: Any,
    before_root: dict[str, Any],
    after_root: dict[str, Any],
) -> None:
    section, label = _label_for_path(path, before, after, before_root, after_root)
    items.append(
        {
            "path": _format_path(path),
            "section": section,
            "label": label,
            "change_type": change_type,
            "before": before,
            "after": after,
        }
    )


def _label_for_path(
    path: list[str],
    before: Any,
    after: Any,
    before_root: dict[str, Any],
    after_root: dict[str, Any],
) -> tuple[str, str]:
    for collection, section in (
        ("characters", "角色"),
        ("locations", "地点"),
        ("scenes", "场景"),
    ):
        if collection not in path:
            continue
        idx = path.index(collection)
        item_id = path[idx + 1] if len(path) > idx + 1 else ""
        item = after if isinstance(after, dict) else before if isinstance(before, dict) else None
        item_label = _entity_label(collection, item_id, item, before_root, after_root)
        field = _field_label(path[idx + 2 :])
        return section, f"{item_label}{f' · {field}' if field else ''}"

    field = _field_label(path[1:] if path and path[0] == "script" else path)
    return "剧本", field or "剧本"


def _entity_label(
    collection: str,
    item_id: str,
    item: Any,
    before_root: dict[str, Any],
    after_root: dict[str, Any],
) -> str:
    if collection == "characters":
        name = _entity_name(item, item_id) or _find_entity_name(after_root, collection, item_id)
        name = name or _find_entity_name(before_root, collection, item_id) or item_id
        return f"角色：{name}"
    if collection == "locations":
        name = _entity_name(item, item_id) or _find_entity_name(after_root, collection, item_id)
        name = name or _find_entity_name(before_root, collection, item_id) or item_id
        return f"地点：{name}"
    if collection == "scenes":
        scene = _find_entity(after_root, collection, item_id) or _find_entity(
            before_root,
            collection,
            item_id,
        )
        title = _entity_name(item, item_id) or _entity_name(scene, item_id) or item_id
        index = _scene_index(after_root, item_id) or _scene_index(before_root, item_id)
        prefix = f"第 {index} 场" if index else "场景"
        return f"{prefix}：{title}" if title and title != item_id else prefix
    return item_id


def _entity_name(item: Any, fallback: str) -> str:
    if not isinstance(item, dict):
        return ""
    value = item.get("name") or item.get("title") or fallback
    return str(value or "").strip()


def _find_entity(root: dict[str, Any], collection: str, item_id: str) -> dict[str, Any] | None:
    script = root.get("script") if isinstance(root, dict) else None
    if not isinstance(script, dict):
        return None
    for item in script.get(collection) or []:
        if isinstance(item, dict) and item.get("id") == item_id:
            return item
    return None


def _find_entity_name(root: dict[str, Any], collection: str, item_id: str) -> str:
    item = _find_entity(root, collection, item_id)
    return _entity_name(item, item_id) if item else ""


def _scene_index(root: dict[str, Any], scene_id: str) -> int | None:
    script = root.get("script") if isinstance(root, dict) else None
    if not isinstance(script, dict):
        return None
    for index, scene in enumerate(script.get("scenes") or [], start=1):
        if isinstance(scene, dict) and scene.get("id") == scene_id:
            return index
    return None


def _field_label(path: list[str]) -> str:
    if not path:
        return ""
    labels = [FIELD_LABELS.get(part, part) for part in path if not part.startswith("index_")]
    return " / ".join(labels)


def _format_path(path: list[str]) -> str:
    return "/" + "/".join(path)
