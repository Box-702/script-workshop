# =====================================================================
# test_export.py —— 剧本导出渲染（.txt / .md / .docx）
# =====================================================================

import zipfile
from io import BytesIO

import pytest

from app.domain import (
    Character,
    Location,
    Scene,
    Script,
    ScriptBeat,
    Source,
)
from app.export import (
    export_script,
    script_to_markdown,
    script_to_screenplay,
)


def _sample_script() -> Script:
    chars = [
        Character(id="char_001", name="林然", role="protagonist"),
        Character(id="char_002", name="阿姐", role="supporting"),
    ]
    locs = [Location(id="loc_001", name="旧货市场"), Location(id="loc_002", name="出租屋")]
    scenes = [
        Scene(
            id="scene_001",
            title="外景 旧货市场",
            chapter_refs=["ch_001"],
            location_id="loc_001",
            time="夜",
            characters=["char_001", "char_002"],
            purpose="林然在雨夜寻找线索。",
            conflict="红雨衣男人挡在面前。",
            beats=[
                ScriptBeat(id="beat_001", type="action", text="雨夜。林然走进废旧市场。"),
                ScriptBeat(id="beat_002", type="dialogue", speaker="char_002", line="你终于来了。", emotion="低沉"),
                ScriptBeat(id="beat_003", type="cue", text="阿姐把一张照片按在桌上。"),
            ],
        ),
        Scene(
            id="scene_002",
            title="内景 出租屋",
            chapter_refs=["ch_001"],
            location_id="loc_002",
            time="凌晨",
            characters=["char_001"],
            purpose="对峙后的深夜对话。",
            conflict="林然追问真相。",
            beats=[ScriptBeat(id="beat_001", type="dialogue", speaker="char_001", line="那张照片里的人是谁？")],
        ),
    ]
    return Script(
        title="雨夜",
        version="1.0",
        language="zh-CN",
        source=Source(chapter_count=1, chapter_ids=["ch_001"]),
        logline="一对旧情人，一场未熄灭的火。",
        characters=chars,
        locations=locs,
        scenes=scenes,
    )


def test_screenplay_has_int_ext_from_title():
    text = script_to_screenplay(_sample_script())
    assert "EXT. 旧货市场 - 夜" in text
    assert "INT. 出租屋 - 凌晨" in text


def test_screenplay_has_centered_speaker_and_indented_dialogue():
    text = script_to_screenplay(_sample_script())
    # 角色名大写 + 对白缩进。
    assert "阿姐" in text
    assert "你终于来了。" in text
    assert "CUT TO:" in text


def test_markdown_uses_heading_and_quote():
    md = script_to_markdown(_sample_script())
    assert md.startswith("# 《雨夜》")
    assert "> 一对旧情人，一场未熄灭的火。" in md
    assert "## EXT. 旧货市场 - 夜" in md


@pytest.mark.parametrize("fmt", ["txt", "md", "docx"])
def test_export_script_valid_format(fmt):
    data, ext = export_script(_sample_script(), fmt)
    assert isinstance(data, bytes) and len(data) > 0
    assert ext == "." + fmt


def test_export_unknown_format_raises():
    with pytest.raises(ValueError):
        export_script(_sample_script(), "pdf")


def test_docx_is_valid_zip_with_document():
    data, _ = export_script(_sample_script(), "docx")
    zf = zipfile.ZipFile(BytesIO(data))
    names = zf.namelist()
    assert "word/document.xml" in names
    xml = zf.read("word/document.xml").decode("utf-8")
    assert "旧货市场" in xml
    assert "你终于来了。" in xml
