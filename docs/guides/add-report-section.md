# Guide: Add a report section

Report structure is configuration: `backend/app/reports/templates/*.yaml` defines ordered sections, each with the metrics it discloses, the framework requirements it addresses and its narrative source. The builder (`backend/app/reports/builder.py`) turns sections into tables, AI drafts or deterministic data sections.

Related: [../GOVERNANCE.md](../GOVERNANCE.md#9-nine-pre-generation-checks-reportsbuilderpyvalidate) · [../FRAMEWORKS.md](../FRAMEWORKS.md#6-frameworks-and-report-templates) · [../AGENTS.md](../AGENTS.md).

---

## 1. Section schema

```yaml
- code: supply_chain                    # unique within the template; becomes report_sections.code
  title: Responsible Supply Chain
  level: 2                              # 0 cover, 1 chapter, 2 sub-section (numbering and headings)
  source: ai                            # ai | data | template
  metrics: [SOC.SUPPLY.SUPPLIERS_SCREENED, SOC.SUPPLY.SCREENED_PCT, SOC.SUPPLY.DUE_DILIGENCE_APPROACH]
  requirements: [GRI.308-1, UNGC.P2]    # requirement codes; used for section filtering, disclosures line, narrative coverage
  table: {metrics: [SOC.SUPPLY.SUPPLIERS_SCREENED], by_entity: true}   # optional extra table
  chart: trend                          # optional hint stored on the section (charts JSON) for the frontend
```

| `source` | Behaviour in `generate_draft` |
|---|---|
| `ai` | Key-metrics table (current, prior period, unit, evidence) from governed values; narrative drafted by the Reporting Agent (`draft_section`) with evaluation and governance; section status `ai_generated`, `requires_review` (low confidence / rule) or `blocked` |
| `data` | Deterministic markdown produced by `ReportBuilder._data_section(code, …)`; status `requires_review` |
| `template` | Static structural section (chapter headings, cover); `cover` is auto-approved with title, period and frameworks |

## 2. Add an AI-drafted section

Edit `backend/app/reports/templates/esg_annual.yaml` and insert the section in order (position = `sort_order`):

```yaml
  - {code: community, title: Community Investment, level: 2, source: ai, metrics: [...], requirements: [GRI.413-1]}
  - {code: supply_chain, title: Responsible Supply Chain, level: 2, source: ai,
     metrics: [SOC.SUPPLY.SUPPLIERS_SCREENED, SOC.SUPPLY.SCREENED_PCT, SOC.SUPPLY.DUE_DILIGENCE_APPROACH],
     requirements: [GRI.308-1, UNGC.P2], table: {metrics: [SOC.SUPPLY.SUPPLIERS_SCREENED], by_entity: true}}
```

Nothing else is required: the section is created for every new report whose `framework_codes` include a framework matching one of its requirement prefixes (`GRI` or `UNGC` here). Sections with no `requirements` are always included.

## 3. Add a deterministic data section

Data sections need a renderer branch. Add the YAML entry with `source: data`:

```yaml
  - {code: evidence_register, title: Evidence Register, level: 1, source: data}
```

and a branch in `ReportBuilder._data_section` (`backend/app/reports/builder.py`), returning markdown (headings, paragraphs and pipe tables are understood by every renderer through `markdown_util.blocks`):

```python
        if code == "evidence_register":
            lines = ["| Code | Title | Kind | Page | Verification | Confidence |", "|---|---|---|---|---|---|"]
            for ev in self.db.execute(select(Evidence).where(Evidence.tenant_id == self.principal.tenant_id).order_by(Evidence.code)).scalars().all():
                lines.append(f"| {ev.code} | {ev.title} | {ev.kind} | {ev.printed_page or '—'} | {ev.verification_status} | {ev.confidence or '—'} |")
            return "\n".join(lines)
```

Existing data sections: `targets`, `framework_index`, `methodology`, `assurance`, `appendix`.

## 4. Add a template

Create `backend/app/reports/templates/climate_report.yaml` with `code`, `name`, `description`, `sections` (always start with a `cover` section of `source: template`). Templates are discovered by `load_templates()` (`GET /reports/templates`) and mirrored into `report_templates` at seed time. Create a report with `"template_code": "CLIMATE"`.

## 5. Add a renderer (optional)

Create `backend/app/reports/renderers/json_renderer.py` with `render(payload: dict) -> bytes` (payload keys: `title, organization, period, period_code, frameworks, status, generated_at, readiness, sections[{code,title,level,content_md,tables,status,metric_codes,evidence_codes,requirement_codes,source}], metric_rows, watermark`), register it in `builder.py::RENDERERS`, and add the media type to the `download` route in `backend/app/api/v1/reports.py`.

## 6. Generate and validate

```bash
curl -X POST localhost:8000/api/v1/reports -H "authorization: Bearer $T" -H 'content-type: application/json' \
  -d '{"period_code": "FY2023", "template_code": "ESG_ANNUAL", "framework_codes": ["WEF_SCM", "UNGC", "UN_SDG", "GRI"]}'
curl -X POST localhost:8000/api/v1/reports/1/generate-draft?sections=supply_chain -H "authorization: Bearer $T"
curl -X POST localhost:8000/api/v1/reports/1/validate -H "authorization: Bearer $T"
curl  localhost:8000/api/v1/reports/1/preview -H "authorization: Bearer $T"
```

The nine checks apply to the new section: its metrics must have values (check 1) and evidence (check 4), the narrative must be non-empty (check 5) and must only contain governed numbers (check 6, CRITICAL), and the section must be approved before final generation (check 9).

## 7. Checklist

- [ ] `code` unique within the template; `level` consistent with neighbours.
- [ ] Every metric code exists; narrative metrics (`kind: narrative`) are fine in `metrics` — they are excluded from the numeric table but supplied to the Reporting Agent as text facts.
- [ ] `requirements` prefixes match the frameworks you expect to select the section.
- [ ] For `data` sections, the `_data_section` branch handles empty data with an explicit "Data unavailable" / "Evidence required" line rather than an empty string (check 5 fails on empty content).
- [ ] Rendered in all formats: run `POST /reports/{id}/generate?format=pdf|docx|xlsx|csv|html` on a draft.
