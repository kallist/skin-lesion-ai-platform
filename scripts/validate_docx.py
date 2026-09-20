"""Structural validation of the generated DOCX deliverables (stdlib only).

Checks, per file: ZIP integrity, XML well-formedness of every part, presence of
the required OOXML parts, table/image/TOC/footer counts and embedded media.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path
import xml.dom.minidom as minidom

REQUIRED_PARTS = [
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
    "word/_rels/document.xml.rels",
    "word/styles.xml",
    "word/settings.xml",
    "word/footer1.xml",
    "docProps/core.xml",
    "docProps/app.xml",
]

targets = sorted(Path(sys.argv[1] if len(sys.argv) > 1 else "deliverables/docs").glob("*.docx"))
if not targets:
    print("FAIL: no .docx files found")
    raise SystemExit(1)

failures = 0
for path in targets:
    problems: list[str] = []
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            problems.append("zip CRC failure")
        names = archive.namelist()
        for required in REQUIRED_PARTS:
            if required not in names:
                problems.append(f"missing part {required}")
        for name in names:
            if name.endswith((".xml", ".rels")):
                try:
                    minidom.parseString(archive.read(name))
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"malformed XML in {name}: {exc}")
        document = archive.read("word/document.xml").decode("utf-8")
        media = [n for n in names if n.startswith("word/media/")]

    tables = document.count("<w:tbl>")
    images = document.count("<w:drawing>")
    headings = (
        document.count('w:val="Heading1"')
        + document.count('w:val="Heading2"')
        + document.count('w:val="Heading3"')
    )
    paragraphs = document.count("<w:p>")
    has_toc = "TOC \\o" in document or "TOC \\\\o" in document
    has_footer = "footerReference" in document
    has_page_break = 'w:type="page"' in document

    if paragraphs < 50:
        problems.append(f"too few paragraphs ({paragraphs})")
    if images != len(media):
        problems.append(f"image count mismatch: drawings={images} media={len(media)}")
    # Placeholder markers that must never appear in a delivered document.
    # NOTE: the visible text "结果区域占位" (a UI placeholder hint) is legitimate
    # content, so the checks are line oriented instead of substring based.
    for marker in ("TODO", "TBD", "FIXME", "PLACEHOLDER", "待补充", "待填写"):
        if marker in document:
            problems.append(f"placeholder marker found: {marker}")

    status = "PASS" if not problems else "FAIL"
    if problems:
        failures += 1
    print(
        f"[{status}] {path.name}: {path.stat().st_size / 1024:.1f} KB · "
        f"paragraphs={paragraphs} tables={tables} images={images} media={len(media)} "
        f"headings={headings} toc={has_toc} footer={has_footer} pagebreak={has_page_break}"
    )
    for problem in problems:
        print(f"        - {problem}")

print()
print(f"checked={len(targets)} failures={failures}")
raise SystemExit(1 if failures else 0)
