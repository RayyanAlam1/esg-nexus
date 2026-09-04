"""HTML renderer used for the in-app paginated preview — mirrors the PDF structure."""

from __future__ import annotations

import html

from app.reports.renderers.markdown_util import blocks, strip_inline


def _table(columns, rows):
    head = "".join(f"<th>{html.escape(strip_inline(str(c)))}</th>" for c in columns)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(strip_inline(str(c)))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table class='rpt'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def pages(payload: dict) -> list[dict]:
    """Return logical pages [{number, title, html}] — one per section plus cover and TOC."""
    out = []
    wm = f"<div class='watermark'>{html.escape(payload['watermark'])}</div>" if payload.get("watermark") else ""
    out.append(
        {
            "number": 1,
            "title": "Cover",
            "html": f"{wm}<div class='cover'><h1>{html.escape(payload['title'])}</h1><p class='sub'>{html.escape(payload['organization'])}</p><p>Reporting period: {html.escape(payload['period'])}</p><p>Frameworks: {html.escape(', '.join(payload['frameworks']))}</p><p class='small'>Generated {payload['generated_at']}</p></div>",
        }
    )
    toc = "".join(f"<li class='l{s['level']}'>{html.escape(s['title'])}</li>" for s in payload["sections"] if s["code"] != "cover")
    out.append({"number": 2, "title": "Table of Contents", "html": f"{wm}<h1>Table of Contents</h1><ol class='toc'>{toc}</ol>"})
    n = 2
    for s in payload["sections"]:
        if s["code"] == "cover":
            continue
        n += 1
        parts = [wm, f"<h{1 if s['level'] <= 1 else 2}>{html.escape(s['title'])}</h{1 if s['level'] <= 1 else 2}>"]
        if s.get("requirement_codes"):
            parts.append(f"<p class='small'>Disclosures: {html.escape(', '.join(s['requirement_codes']))}</p>")
        for b in blocks(s["content_md"]):
            if b["type"] == "heading":
                parts.append(f"<h3>{html.escape(strip_inline(b['text']))}</h3>")
            elif b["type"] == "paragraph":
                parts.append(f"<p>{html.escape(strip_inline(b['text']))}</p>")
            elif b["type"] == "table":
                parts.append(_table(b["columns"], b["rows"]))
        for t in s.get("tables") or []:
            parts.append(f"<h3>{html.escape(t['title'])}</h3>" + _table(t["columns"], t["rows"]))
        if s.get("evidence_codes"):
            parts.append(f"<p class='small'>Evidence: {html.escape(', '.join(s['evidence_codes'][:12]))}</p>")
        parts.append(f"<p class='status'>Section status: {html.escape(s['status'])} · source: {html.escape(s['source'])}</p>")
        out.append({"number": n, "title": s["title"], "html": "".join(parts), "code": s["code"], "status": s["status"]})
    return out


CSS = """
.page{font-family:Georgia,'Times New Roman',serif;color:#1c2833;line-height:1.5;padding:48px 56px;background:#fff;min-height:1000px;position:relative}
.page h1{font-family:Helvetica,Arial,sans-serif;color:#0F2A44;font-size:22px;border-bottom:2px solid #1B7F79;padding-bottom:6px}
.page h2{font-family:Helvetica,Arial,sans-serif;color:#1B7F79;font-size:17px}.page h3{font-family:Helvetica,Arial,sans-serif;color:#0F2A44;font-size:13px}
.page p{font-size:13px;text-align:justify}.page .small,.page .status{font-size:11px;color:#5B6470}
.page table.rpt{border-collapse:collapse;width:100%;font-family:Helvetica,Arial,sans-serif;font-size:11px;margin:8px 0}
.page table.rpt th{background:#0F2A44;color:#fff;text-align:left;padding:5px 6px}.page table.rpt td{border-bottom:1px solid #C9D2DC;padding:4px 6px;vertical-align:top}
.page table.rpt tr:nth-child(even) td{background:#F2F5F8}.page .cover{padding-top:200px}.page .cover h1{font-size:30px;border:none}.page .sub{font-size:16px;color:#5B6470}
.page .toc li{font-size:13px;margin:4px 0}.page .toc li.l2{margin-left:18px;font-size:12px;color:#334}
.page .watermark{position:absolute;top:40%;left:10%;font-size:64px;color:rgba(176,58,46,.08);transform:rotate(-30deg);font-family:Helvetica,Arial,sans-serif;font-weight:bold;pointer-events:none}
.page footer{position:absolute;bottom:20px;left:56px;right:56px;font-size:10px;color:#5B6470;display:flex;justify-content:space-between;font-family:Helvetica,Arial,sans-serif}
"""


def render(payload: dict) -> bytes:
    body = "".join(
        f"<section class='page'>{p['html']}<footer><span>{html.escape(payload['organization'])} · {html.escape(payload['title'])}</span><span>Page {p['number']}</span></footer></section>"
        for p in pages(payload)
    )
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(payload['title'])}</title><style>{CSS}body{{background:#e9edf1;margin:0}}.page{{max-width:900px;margin:24px auto;box-shadow:0 2px 12px rgba(0,0,0,.12)}}</style></head><body>{body}</body></html>".encode()
