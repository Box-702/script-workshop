# =====================================================================
# importer.py —— 原著文件导入（.txt / .md / .docx / .pdf）
#
# 新建剧本时支持直接上传文件：
#   - .txt / .md：按文本读取（优先 UTF-8，回退 GBK）；
#   - .docx：用标准库 zipfile + xml 解析 word/document.xml 的段落文本
#     （不引入 python-docx 依赖）；
#   - .pdf：用 pypdf 逐页提取文本（纯 Python，无系统依赖）。
# 解析出的纯文本交给项目创建流程（切片 + 建知识库）。
# =====================================================================

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO

# docx 的命名空间。
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# 允许导入的扩展名 -> 说明。
SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".txt": "纯文本",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".docx": "Word 文档",
    ".pdf": "PDF 文档",
}


def extension_of(filename: str) -> str:
    """返回小写扩展名（含点）。"""
    name = (filename or "").strip()
    idx = name.rfind(".")
    return name[idx:].lower() if idx >= 0 else ""


def is_supported(filename: str) -> bool:
    return extension_of(filename) in SUPPORTED_EXTENSIONS


def parse_file(filename: str, data: bytes) -> str:
    """按扩展名把文件内容解析为纯文本；不支持的类型抛 ValueError。"""
    ext = extension_of(filename)
    if ext == ".docx":
        return _parse_docx(data)
    if ext == ".pdf":
        return _parse_pdf(data)
    if ext in {".txt", ".md", ".markdown"}:
        return _decode_text(data)
    raise ValueError(
        f"不支持的文件类型 {ext or '(无扩展名)'}，支持：{', '.join(SUPPORTED_EXTENSIONS)}"
    )


def _parse_pdf(data: bytes) -> str:
    """用 pypdf 逐页提取 PDF 文本；扫描版（无文本层）给出明确错误。"""
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover - 依赖已随包安装
        raise ValueError("PDF 解析依赖 pypdf 未安装，请先 uv sync") from e
    try:
        reader = PdfReader(BytesIO(data))
        pages = [(page.extract_text() or "") for page in reader.pages]
    except Exception as e:  # noqa: BLE001 - 损坏/加密的 PDF 给出可读错误
        raise ValueError(f"无法解析 PDF 文件：{e}") from e
    text = "\n".join(p.strip() for p in pages if p and p.strip())
    if not text.strip():
        raise ValueError("这份 PDF 没有可提取的文本层（可能是扫描版），请先用 OCR 转成文字再导入")
    return text


def _decode_text(data: bytes) -> str:
    """UTF-8 优先，回退 GBK（常见中文 txt）。"""
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _parse_docx(data: bytes) -> str:
    """解析 .docx 正文：按段落（w:p）提取文本，段落间用换行分隔。"""
    with zipfile.ZipFile(BytesIO(data)) as zf:
        try:
            xml_bytes = zf.read("word/document.xml")
        except KeyError as e:
            raise ValueError("不是有效的 .docx 文件（缺少 document.xml）") from e
    root = ET.fromstring(xml_bytes)
    paragraphs: list[str] = []
    for para in root.iter(_W_NS + "p"):
        # 段落内所有 w:t 的文本按顺序拼接。
        text = "".join(t.text or "" for t in para.iter(_W_NS + "t"))
        # 表格单元格（w:tc）可能以独立段落出现，这里统一并入正文流。
        text = text.strip()
        if text:
            paragraphs.append(text)
    if not paragraphs:
        raise ValueError("文档里没有提取到正文内容")
    # 清洗：合并多余空行、去掉连续制表符。
    raw = "\n".join(paragraphs)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw
