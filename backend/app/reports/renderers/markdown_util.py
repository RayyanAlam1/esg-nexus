"""Tiny markdown helpers shared by renderers (paragraphs, headings, pipe tables)."""

from __future__ import annotations

import re


def blocks(md: str) -> list[dict]:
    """Split markdown into blocks: {'type': 'heading'|'paragraph'|'table', ...}."""
    out: list[dict] = []
    lines = (md or "").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            out.append({"type": "heading", "level": level, "text": line.lstrip("#").strip()})
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                out.append({"type": "table", "columns": rows[0], "rows": rows[1:]})
            continue
        para = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith("#") and not lines[i].startswith("|"):
            para.append(lines[i].strip())
            i += 1
        out.append({"type": "paragraph", "text": " ".join(para)})
    return out


def strip_inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    return text
