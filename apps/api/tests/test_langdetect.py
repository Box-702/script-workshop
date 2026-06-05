"""Tests for the lightweight language detector."""
from __future__ import annotations

from app.langdetect import detect_language


def test_chinese_simplified():
    text = "林屿关上诊所的灯。雨水顺着门缝渗进来。她盯着天花板。"
    assert detect_language(text) == "zh-CN"


def test_chinese_traditional_uses_traditional_only_chars():
    text = "臺灣的舊書攤在週末總是擠滿了人，書與舊鐘並排陳列。"
    assert detect_language(text) == "zh-TW"


def test_english():
    text = (
        "The doctor was alone in the clinic. The woman was bleeding on the floor "
        "and could not remember her own name. The rain hammered the roof."
    )
    assert detect_language(text) == "en-US"


def test_japanese_kana_disambiguates_from_chinese():
    # Pure CJK without kana → Chinese. Add kana → Japanese.
    assert detect_language("雨が降り始めた。東京の街は静かだった。") == "ja-JP"


def test_korean():
    text = "서울의 비가 내리기 시작했다. 한 남자가 진료소 문을 두드렸다."
    assert detect_language(text) == "ko-KR"


def test_russian():
    assert detect_language("Врач открыл дверь клиники. Дождь стучал по крыше.") == "ru-RU"


def test_arabic():
    assert detect_language("الطبيب فتح باب العيادة. كانت السماء تمطر.") == "ar-SA"


def test_empty_string_falls_back_to_default():
    assert detect_language("") == "en-US"
    assert detect_language("   \n\t  ") == "en-US"


def test_mixed_text_does_not_crash():
    # Latin-heavy mixed text should not raise and should return a sane tag.
    result = detect_language("Lin Yu was a doctor. He opened the door. 林医生走进房间。")
    assert result in {"en-US", "zh-CN"}
