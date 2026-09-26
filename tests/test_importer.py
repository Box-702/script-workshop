# =====================================================================
# test_importer.py —— 原著文件导入解析（.txt / .md / .docx）
# =====================================================================

import zipfile
from io import BytesIO

import pytest

from app.pipeline.importer import SUPPORTED_EXTENSIONS, extension_of, is_supported, parse_file


def _make_docx(paragraphs: list[str]) -> bytes:
    """构造一个最小可用 .docx（zip + word/document.xml）。"""
    buf = BytesIO()
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml)
    return buf.getvalue()


def test_parse_txt_utf8():
    text = parse_file("原著.txt", "凌晨三点，雨夜。\n林然停下车。".encode("utf-8"))
    assert "凌晨三点" in text and "林然" in text


def test_parse_txt_gbk_fallback():
    text = parse_file("原著.txt", "雨夜旧楼，红雨衣男人。".encode("gb18030"))
    assert "红雨衣" in text


def test_parse_markdown():
    text = parse_file("原著.md", "# 第一章 雨夜\n\n**旧楼**里没有灯。".encode("utf-8"))
    assert "# 第一章" in text and "旧楼" in text


def test_parse_docx():
    docx = _make_docx(["第一章　雨夜", "凌晨三点，滨江路的路灯在雨里像一团化不开的黄。", "林然推开车门。"])
    text = parse_file("原著.docx", docx)
    assert "第一章" in text
    assert "凌晨三点" in text
    assert "林然推开车门" in text
    assert text.count("\n") >= 2  # 段落按行分隔


def test_parse_unsupported_raises():
    with pytest.raises(ValueError):
        parse_file("原著.epub", b"fake epub bytes")


def test_extension_helpers():
    assert extension_of("原著.txt") == ".txt"
    assert extension_of("a.MD") == ".md"
    assert is_supported("原著.docx")
    assert is_supported("原著.pdf")      # pdf 已支持（pypdf）
    assert not is_supported("原著.epub")


def test_parse_pdf_no_text_layer_gives_clear_error():
    """无文本层的 PDF（如 pypdf 写出的空白页）给出可读错误，扩展名已注册。"""
    from io import BytesIO

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)

    with pytest.raises(ValueError, match="没有可提取的文本层"):
        parse_file("scan.pdf", buf.getvalue())
    assert is_supported("a.pdf")
    assert ".pdf" in SUPPORTED_EXTENSIONS
