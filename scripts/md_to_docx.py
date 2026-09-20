"""Minimal Markdown -> DOCX converter (standard library only).

Why this exists
---------------
The school delivery requires real Word documents, but the project virtual
environment has no DOCX library available offline (python-docx is absent, pip
installation depends on network access).  A .docx is a ZIP archive of OOXML
parts, so this script writes those parts directly and therefore adds **zero**
runtime dependencies to the project.

Supported Markdown subset (enough for the delivered documents)
--------------------------------------------------------------
* ATX headings (``#`` .. ``####``) with a Word ``TOC`` field for the outline
* paragraphs with inline ``**bold**``, ``` `code` ``` and ``[text](target)``
* bullet lists (``-``/``*``) and ordered lists (``1.``)
* GFM tables with a bold header row and borders
* fenced code blocks (```` ``` ````) including ```mermaid`` as a captioned listing
* blockquotes (``>``)
* images (``![alt](path)``) centred, scaled to the text width, when the file exists
* horizontal rules (``---``)

Usage
-----
    python scripts/md_to_docx.py <input.md> <output.docx> [--title "..."] [--subtitle "..."]
"""

from __future__ import annotations

import argparse
import os
import re
import struct
import zipfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

# A4 page in twips (1 inch = 1440 twips, 1 cm = 567 twips)
PAGE_W, PAGE_H = 11906, 16838
MARGIN = 1134  # 2 cm
CONTENT_W_TWIPS = PAGE_W - 2 * MARGIN
CONTENT_W_EMU = int(CONTENT_W_TWIPS / 1440 * 914400)  # 1 inch = 914400 EMU

BODY_FONT = "宋体"
HEAD_FONT = "微软雅黑"
MONO_FONT = "Consolas"
BODY_SIZE = 21  # half-points -> 10.5pt (五号)


# --------------------------------------------------------------------------- #
# XML helpers
# --------------------------------------------------------------------------- #
def run_props(*, bold=False, italic=False, mono=False, size=None, color=None,
              east_asia=None, ascii_font=None) -> str:
    parts = []
    font = MONO_FONT if mono else (ascii_font or (HEAD_FONT if east_asia else BODY_FONT))
    parts.append(
        f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:eastAsia="{east_asia or font}" w:cs="{font}"/>'
    )
    if bold:
        parts.append("<w:b/><w:bCs/>")
    if italic:
        parts.append("<w:i/><w:iCs/>")
    if color:
        parts.append(f'<w:color w:val="{color}"/>')
    parts.append(f'<w:sz w:val="{size or BODY_SIZE}"/><w:szCs w:val="{size or BODY_SIZE}"/>')
    return "<w:rPr>" + "".join(parts) + "</w:rPr>"


def text_run(text: str, **kwargs) -> str:
    return (
        f"<w:r>{run_props(**kwargs)}"
        f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'
    )


def para(content: str = "", *, style: str | None = None, align: str | None = None,
         spacing_before: int = 0, spacing_after: int = 120, indent: int = 0,
         line: int = 320, keep_next: bool = False) -> str:
    props = []
    if style:
        props.append(f'<w:pStyle w:val="{style}"/>')
    if keep_next:
        props.append("<w:keepNext/>")
    if align:
        props.append(f'<w:jc w:val="{align}"/>')
    if indent:
        props.append(f'<w:ind w:left="{indent}" w:hanging="360"/>')
    props.append(
        f'<w:spacing w:before="{spacing_before}" w:after="{spacing_after}" w:line="{line}" w:lineRule="auto"/>'
    )
    return f"<w:p><w:pPr>{''.join(props)}</w:pPr>{content}</w:p>"


def image_paragraph(rel_id: str, name: str, *, cx: int, cy: int, doc_id: int) -> str:
    drawing = (
        "<w:drawing><wp:inline distT=\"0\" distB=\"0\" distL=\"0\" distR=\"0\">"
        f'<wp:extent cx="{cx}" cy="{cy}"/>'
        f'<wp:effectExtent l="0" t="0" r="0" b="0"/>'
        f'<wp:docPr id="{doc_id}" name="{escape(name)}"/>'
        "<a:graphic xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\">"
        "<a:graphicData uri=\"http://schemas.openxmlformats.org/drawingml/2006/picture\">"
        "<pic:pic xmlns:pic=\"http://schemas.openxmlformats.org/drawingml/2006/picture\">"
        f'<pic:nvPicPr><pic:cNvPr id="{doc_id}" name="{escape(name)}"/><pic:cNvPicPr/></pic:nvPicPr>'
        f'<pic:blipFill><a:blip r:embed="{rel_id}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        "<pic:spPr><a:xfrm><a:off x=\"0\" y=\"0\"/>"
        f'<a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        "<a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></pic:spPr>"
        "</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing>"
    )
    return para(f"<w:r>{drawing}</w:r>", align="center", spacing_before=120, spacing_after=60)


def table_xml(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    cols = max(len(r) for r in rows)
    width = CONTENT_W_TWIPS // cols
    borders = (
        "<w:tblBorders>"
        '<w:top w:val="single" w:sz="6" w:color="808080"/>'
        '<w:left w:val="single" w:sz="6" w:color="808080"/>'
        '<w:bottom w:val="single" w:sz="6" w:color="808080"/>'
        '<w:right w:val="single" w:sz="6" w:color="808080"/>'
        '<w:insideH w:val="single" w:sz="4" w:color="BFBFBF"/>'
        '<w:insideV w:val="single" w:sz="4" w:color="BFBFBF"/>'
        "</w:tblBorders>"
    )
    grid = "".join(f'<w:gridCol w:w="{width}"/>' for _ in range(cols))
    out = [
        "<w:tbl><w:tblPr>",
        f'<w:tblW w:w="{CONTENT_W_TWIPS}" w:type="dxa"/>',
        borders,
        '<w:tblLayout w:type="fixed"/>',
        "</w:tblPr>",
        f"<w:tblGrid>{grid}</w:tblGrid>",
    ]
    for r_index, row in enumerate(rows):
        header = r_index == 0
        out.append("<w:tr>")
        if header:
            out.append("<w:trPr><w:tblHeader/></w:trPr>")
        for c_index in range(cols):
            cell = row[c_index] if c_index < len(row) else ""
            shade = '<w:shd w:val="clear" w:color="auto" w:fill="F2F2F2"/>' if header else ""
            out.append(
                f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{shade}'
                '<w:vAlign w:val="center"/></w:tcPr>'
            )
            out.append(para(inline_runs(cell, bold=header), spacing_after=40, line=260))
            out.append("</w:tc>")
        out.append("</w:tr>")
    out.append("</w:tbl>")
    out.append(para("", spacing_after=80))
    return "".join(out)


def code_block_xml(code: str, lang: str) -> str:
    lines = code.rstrip("\n").split("\n")
    content = []
    for index, line in enumerate(lines):
        content.append(text_run(line if line else " ", mono=True, size=18))
        if index != len(lines) - 1:
            content.append("<w:r><w:br/></w:r>")
    shading = '<w:shd w:val="clear" w:color="auto" w:fill="F7F7F7"/>'
    border = '<w:pBdr><w:left w:val="single" w:sz="12" w:color="D0D0D0" w:space="6"/></w:pBdr>'
    return (
        f'<w:p><w:pPr><w:pStyle w:val="CodeBlock"/>{border}{shading}'
        '<w:spacing w:before="80" w:after="160" w:line="240" w:lineRule="auto"/>'
        f'<w:ind w:left="170"/></w:pPr>{"".join(content)}</w:p>'
    )


LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
CODE_RE = re.compile(r"`([^`]+)`")
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def inline_runs(text: str, *, bold: bool = False) -> str:
    """Escape-safe inline formatting: **bold**, `code`, [text](link)."""
    tokens: list[tuple[str, str]] = []
    pattern = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]*\]\([^)]+\))")
    position = 0
    for match in pattern.finditer(text):
        if match.start() > position:
            tokens.append(("text", text[position:match.start()]))
        token = match.group(0)
        if token.startswith("**"):
            tokens.append(("bold", token[2:-2]))
        elif token.startswith("`"):
            tokens.append(("code", token[1:-1]))
        else:
            link = LINK_RE.match(token)
            assert link is not None
            tokens.append(("link", f"{link.group(1)} ({link.group(2)})"))
        position = match.end()
    if position < len(text):
        tokens.append(("text", text[position:]))

    runs = []
    for kind, value in tokens:
        if not value and kind != "text":
            continue
        if kind == "bold":
            runs.append(text_run(value, bold=True))
        elif kind == "code":
            runs.append(text_run(value, mono=True, size=18))
        elif kind == "link":
            runs.append(text_run(value, color="1F4E79"))
        else:
            runs.append(text_run(value, bold=bold))
    return "".join(runs) or text_run("")


# --------------------------------------------------------------------------- #
# Markdown parsing
# --------------------------------------------------------------------------- #
class Document:
    def __init__(self) -> None:
        self.body: list[str] = []
        self.images: list[tuple[str, Path]] = []
        self.toc_entries: list[tuple[int, str]] = []
        self.doc_id = 100

    def add_image(self, source: Path, alt: str) -> None:
        rel_id = f"rIdImg{len(self.images) + 10}"
        # Two images can share a basename (external/confusion_matrix.png vs
        # internal/confusion_matrix.png); prefix with the parent folder so the
        # OOXML package never contains duplicate media parts.
        media_name = f"{source.parent.name}_{source.name}" if source.parent.name else source.name
        self.images.append((rel_id, source, media_name))
        width, height = image_size(source)
        cx = min(CONTENT_W_EMU, int(width / 96 * 914400))
        cy = int(cx * height / width)
        self.doc_id += 1
        self.body.append(
            image_paragraph(rel_id, media_name, cx=cx, cy=cy, doc_id=self.doc_id)
        )


def image_size(path: Path) -> tuple[int, int]:
    """Width/height for PNG or JPEG without external libraries."""
    data = path.read_bytes()[:65536]
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        width, height = struct.unpack(">II", data[16:24])
        return int(width), int(height)
    if data[:2] == b"\xff\xd8":
        index = 2
        while index < len(data) - 9:
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB):
                height, width = struct.unpack(">HH", data[index + 5:index + 9])
                return int(width), int(height)
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                index += 2
                continue
            length = struct.unpack(">H", data[index + 2:index + 4])[0]
            index += 2 + length
    return 1200, 800


def strip_inline_markers(text: str) -> str:
    """Remove inline code/bold markers - Word headings must not show backticks."""
    return re.sub(r"\*\*([^*]+)\*\*", r"\1", re.sub(r"`([^`]+)`", r"\1", text))


def parse_markdown(path: Path, title: str) -> Document:
    doc = Document()
    lines = path.read_text(encoding="utf-8").split("\n")
    base = path.parent
    index = 0

    def flush_table(block: list[str]) -> None:
        rows: list[list[str]] = []
        for raw in block:
            cells = [c.strip() for c in raw.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c or "-") for c in cells):
                continue
            rows.append(cells)
        if rows:
            doc.body.append(table_xml(rows))

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        # ---- fenced code
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            buffer: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                buffer.append(lines[index])
                index += 1
            index += 1
            code = "\n".join(buffer)
            doc.body.append(code_block_xml(code, lang))
            if lang == "mermaid":
                doc.body.append(
                    para(
                        text_run(
                            "（上图为 Mermaid 源码；在 Markdown 版本中可直接渲染为流程图。）",
                            italic=True,
                            size=18,
                            color="808080",
                        ),
                        align="center",
                        spacing_after=160,
                    )
                )
            continue

        # ---- table
        if stripped.startswith("|") and stripped.endswith("|"):
            block = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                block.append(lines[index])
                index += 1
            flush_table(block)
            continue

        # ---- headings
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            level = len(heading.group(1))
            text = strip_inline_markers(heading.group(2).strip())
            if level == 1 and text == title:
                index += 1
                continue  # the cover already carries the title
            size = {1: 32, 2: 28, 3: 24, 4: 22}.get(level, 21)
            doc.body.append(
                para(
                    text_run(text, bold=True, size=size, east_asia=HEAD_FONT),
                    style=f"Heading{min(level, 4)}",
                    spacing_before=240 if level <= 2 else 180,
                    spacing_after=120,
                    line=300,
                    keep_next=True,
                )
            )
            doc.toc_entries.append((level, text))
            index += 1
            continue

        # ---- horizontal rule
        if re.fullmatch(r"-{3,}|\*{3,}", stripped):
            doc.body.append(
                '<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" w:color="A0A0A0"/></w:pBdr>'
                '<w:spacing w:before="120" w:after="160"/></w:pPr></w:p>'
            )
            index += 1
            continue

        # ---- blockquote
        if stripped.startswith(">"):
            buffer = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                buffer.append(lines[index].strip().lstrip(">").strip())
                index += 1
            text = " ".join(part for part in buffer if part)
            doc.body.append(
                f'<w:p><w:pPr><w:pBdr><w:left w:val="single" w:sz="18" w:color="C0C0C0" w:space="8"/></w:pBdr>'
                '<w:shd w:val="clear" w:color="auto" w:fill="FAFAF5"/>'
                '<w:spacing w:before="80" w:after="160" w:line="300" w:lineRule="auto"/>'
                f'<w:ind w:left="200"/></w:pPr>{inline_runs(text)}</w:p>'
            )
            continue

        # ---- image (standalone)
        image = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if image:
            target = (base / image.group(2)).resolve()
            if target.exists():
                doc.add_image(target, image.group(1))
            else:
                doc.body.append(
                    para(
                        text_run(f"[缺少图片: {image.group(2)}]", italic=True, color="C00000"),
                        align="center",
                    )
                )
            index += 1
            continue

        # ---- bullet / ordered list
        bullet = re.match(r"^[-*]\s+(.*)$", stripped)
        ordered = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if bullet or ordered:
            marker = "·" if bullet else f"{ordered.group(1)}."
            text = bullet.group(1) if bullet else ordered.group(2)
            doc.body.append(
                para(
                    text_run(marker + " ", bold=False) + inline_runs(text),
                    indent=360,
                    spacing_after=60,
                    line=300,
                )
            )
            index += 1
            continue

        # ---- blank
        if not stripped:
            index += 1
            continue

        # ---- paragraph
        doc.body.append(para(inline_runs(stripped), spacing_after=120, line=320))
        index += 1

    return doc


# --------------------------------------------------------------------------- #
# DOCX assembly
# --------------------------------------------------------------------------- #
CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Default Extension="jpg" ContentType="image/jpeg"/>
<Default Extension="jpeg" ContentType="image/jpeg"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="{BODY_FONT}" w:hAnsi="{BODY_FONT}" w:eastAsia="{BODY_FONT}" w:cs="{BODY_FONT}"/>
<w:sz w:val="{BODY_SIZE}"/><w:szCs w:val="{BODY_SIZE}"/>
</w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="320" w:lineRule="auto"/></w:pPr></w:pPrDefault>
</w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>
<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:outlineLvl w:val="0"/></w:pPr>
<w:rPr><w:rFonts w:ascii="{HEAD_FONT}" w:hAnsi="{HEAD_FONT}" w:eastAsia="{HEAD_FONT}"/><w:b/><w:sz w:val="32"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/>
<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:outlineLvl w:val="1"/></w:pPr>
<w:rPr><w:rFonts w:ascii="{HEAD_FONT}" w:hAnsi="{HEAD_FONT}" w:eastAsia="{HEAD_FONT}"/><w:b/><w:sz w:val="28"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/>
<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:outlineLvl w:val="2"/></w:pPr>
<w:rPr><w:rFonts w:ascii="{HEAD_FONT}" w:hAnsi="{HEAD_FONT}" w:eastAsia="{HEAD_FONT}"/><w:b/><w:sz w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading4"><w:name w:val="heading 4"/>
<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:outlineLvl w:val="3"/></w:pPr>
<w:rPr><w:rFonts w:ascii="{HEAD_FONT}" w:hAnsi="{HEAD_FONT}" w:eastAsia="{HEAD_FONT}"/><w:b/><w:sz w:val="22"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="CodeBlock"><w:name w:val="Code Block"/>
<w:basedOn w:val="Normal"/><w:rPr><w:rFonts w:ascii="{MONO_FONT}" w:hAnsi="{MONO_FONT}" w:eastAsia="{MONO_FONT}"/><w:sz w:val="18"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="TOCEntry"><w:name w:val="TOC Entry"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:after="40"/></w:pPr><w:rPr><w:sz w:val="20"/></w:rPr></w:style>
</w:styles>"""

SETTINGS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:zoom w:percent="100"/>
<w:defaultTabStop w:val="420"/>
<w:updateFields w:val="true"/>
</w:settings>"""

FOOTER = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:p><w:pPr><w:jc w:val="center"/></w:pPr>
<w:r><w:rPr><w:rFonts w:ascii="{BODY_FONT}" w:eastAsia="{BODY_FONT}"/><w:sz w:val="18"/><w:color w:val="808080"/></w:rPr>
<w:t xml:space="preserve">第 </w:t></w:r>
<w:r><w:fldChar w:fldCharType="begin"/></w:r>
<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>
<w:r><w:fldChar w:fldCharType="separate"/></w:r>
<w:r><w:t>1</w:t></w:r>
<w:r><w:fldChar w:fldCharType="end"/></w:r>
<w:r><w:rPr><w:rFonts w:ascii="{BODY_FONT}" w:eastAsia="{BODY_FONT}"/><w:sz w:val="18"/><w:color w:val="808080"/></w:rPr>
<w:t xml:space="preserve"> 页</w:t></w:r>
</w:p></w:ftr>"""


def build_cover(title: str, subtitle: str, english: str, version: str, report_date: str) -> list[str]:
    rows = [
        para("", spacing_after=1200),
        para(text_run(title, bold=True, size=52, east_asia=HEAD_FONT), align="center", spacing_after=200),
        para(text_run(subtitle, bold=True, size=32, east_asia=HEAD_FONT), align="center", spacing_after=200),
        para(text_run(english, size=24, east_asia=HEAD_FONT, color="595959"), align="center", spacing_after=900),
        para(text_run("项目类型：学校实习项目", size=24), align="center", spacing_after=120),
        para(text_run(f"文档版本：{version}", size=24), align="center", spacing_after=120),
        para(text_run(f"编制日期：{report_date}", size=24), align="center", spacing_after=700),
        para(text_run("姓名：________________", size=24), align="center", spacing_after=140),
        para(text_run("学号：________________", size=24), align="center", spacing_after=140),
        para(text_run("班级：________________", size=24), align="center", spacing_after=140),
        para(text_run("指导教师：________________", size=24), align="center", spacing_after=700),
        para(
            text_run(
                "本系统仅作为皮肤健康辅助自检工具，AI 辅助检测结果仅供参考，不能替代专业医生诊断。",
                size=18,
                color="A00000",
            ),
            align="center",
            spacing_after=200,
        ),
        '<w:p><w:r><w:br w:type="page"/></w:r></w:p>',
    ]
    return rows


def build_toc(entries: list[tuple[int, str]]) -> list[str]:
    field = (
        '<w:p><w:pPr><w:pStyle w:val="TOCEntry"/></w:pPr>'
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        f'<w:r>{run_props(bold=True, size=22)}<w:t>目录</w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
    )
    # A static outline follows the field, so the document is readable even in
    # viewers that do not evaluate fields; Word replaces it on "update field".
    static = [field]
    static.append(
        para(
            text_run(
                "（在 Word 中按 Ctrl+A 后按 F9 可刷新目录页码）",
                size=16,
                color="808080",
                italic=True,
            ),
            spacing_after=160,
        )
    )
    for level, text in entries:
        if level > 3:
            continue
        static.append(
            para(
                text_run(("    " * (level - 1)) + text, size=20, bold=level == 1),
                style="TOCEntry",
                indent=0 if level == 1 else 300 * (level - 1),
                spacing_after=40,
                line=260,
            )
        )
    static.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
    return static


def build_docx(md_path: Path, out_path: Path, title: str, subtitle: str,
               english: str, version: str, report_date: str | None = None) -> dict:
    report_date = report_date or date.today().strftime("%Y年%m月%d日")
    doc = parse_markdown(md_path, title)
    body = build_cover(title, subtitle, english, version, report_date)
    body += build_toc(doc.toc_entries)
    body += doc.body

    sect = (
        "<w:sectPr>"
        f'<w:pgSz w:w="{PAGE_W}" w:h="{PAGE_H}"/>'
        f'<w:pgMar w:top="{MARGIN}" w:right="{MARGIN}" w:bottom="{MARGIN}" w:left="{MARGIN}" '
        'w:header="720" w:footer="720" w:gutter="0"/>'
        '<w:footerReference w:type="default" r:id="rIdFooter"/>'
        "</w:sectPr>"
    )

    image_rels = "".join(
        f'<Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        f'Target="media/{media_name}"/>'
        for rel_id, _source, media_name in doc.images
    )

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        f'<w:body>{"".join(body)}{sect}</w:body></w:document>'
    )

    document_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '<Relationship Id="rIdSettings" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>'
        '<Relationship Id="rIdFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
        f"{image_rels}"
        "</Relationships>"
    )

    report_date_iso = date.today().isoformat()
    if report_date and len(report_date) >= 10 and report_date[4] == "-":
        report_date_iso = report_date[:10]
    elif report_date:
        parts = re.findall(r"\d+", report_date)
        if len(parts) >= 3:
            report_date_iso = f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"

    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{escape(title + ' · ' + subtitle)}</dc:title>"
        "<dc:subject>皮肤癌图像检测系统 · 学校实习项目交付文档</dc:subject>"
        "<dc:creator>Skin Cancer Image Detection System</dc:creator>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{report_date_iso}T00:00:00Z</dcterms:created>'
        "</cp:coreProperties>"
    )

    app = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>md_to_docx.py</Application>"
        f"<DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop>"
        f"<Company></Company><Manager></Manager>"
        "</Properties>"
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/_rels/document.xml.rels", document_rels)
        archive.writestr("word/styles.xml", STYLES)
        archive.writestr("word/settings.xml", SETTINGS)
        archive.writestr("word/footer1.xml", FOOTER)
        archive.writestr("docProps/core.xml", core)
        archive.writestr("docProps/app.xml", app)
        for _, source, media_name in doc.images:
            archive.write(source, f"word/media/{media_name}")

    return {
        "output": str(out_path),
        "bytes": out_path.stat().st_size,
        "paragraphs": document.count("<w:p>") + document.count("<w:p "),
        "tables": document.count("<w:tbl>"),
        "images": len(doc.images),
        "headings": len(doc.toc_entries),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Markdown -> DOCX (stdlib only)")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--title", required=True)
    parser.add_argument("--subtitle", required=True)
    parser.add_argument("--english", default="Skin Cancer Image Detection System")
    parser.add_argument("--version", default="V1.0")
    parser.add_argument("--date", default=None, help="cover date, e.g. 2026年09月10日 or 2026-09-10")
    args = parser.parse_args()

    stats = build_docx(
        Path(args.input).resolve(),
        Path(args.output).resolve(),
        args.title,
        args.subtitle,
        args.english,
        args.version,
        args.date,
    )
    print(
        f"[docx] {os.path.basename(stats['output'])}: {stats['bytes'] / 1024:.1f} KB · "
        f"paragraphs={stats['paragraphs']} tables={stats['tables']} "
        f"images={stats['images']} headings={stats['headings']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
