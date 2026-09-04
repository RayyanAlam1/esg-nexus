# Guide: Add an ingestion connector

Connectors turn uploaded bytes into row dictionaries; the pipeline (`backend/app/ingestion/pipeline.py`) validates, normalises, scores and loads the rows. Adding a format is a single decorated function.

Related: [../ARCHITECTURE.md](../ARCHITECTURE.md#ingestion-appingestion) · [../API.md](../API.md#28-data--datasets-quality-lineage).

---

## 1. Connector contract

```python
CONNECTORS: dict[str, Callable[[bytes, str], list[dict]]]
```

A connector receives the raw file bytes and the file name and returns a list of dicts. For **tabular** connectors each dict is one row that the pipeline normalises with `ALIASES` (`metric`/`code` → `metric_code`, `entity`/`company` → `entity_code`, `period`/`year`/`fy` → `period_code`, `amount`/`val` → `value`) and validates against the metric library. For **document** connectors (`pdf`, `text`) rows are `{"page", "kind": "page_text" | "candidate_fact", ...}` records stored for the ESG Data Agent; they are not auto-loaded.

Existing connectors: `csv`, `json`, `excel` (first sheet, header row), `pdf` (page text + `label: number [unit]` candidate facts via pypdf), `text`.

## 2. Implement it

Example: an XML export from an EHS system.

Uploaded files are untrusted input; parse XML with `defusedxml` (add `defusedxml>=0.7` to `backend/requirements.txt`) rather than the standard-library parser, which is vulnerable to external-entity and entity-expansion attacks.

```python
# backend/app/ingestion/connectors.py
from defusedxml import ElementTree as ET

@connector("xml")
def read_xml(data: bytes, file_name: str = "") -> list[dict]:
    """<records><record metric="ENV.WATER.WITHDRAWN" entity="EFERT" period="FY2023" unit="ML">12,345</record>…</records>"""
    root = ET.fromstring(data.decode("utf-8"))
    rows = []
    for rec in root.iter("record"):
        rows.append({
            "metric_code": rec.get("metric"),
            "entity_code": rec.get("entity"),
            "period_code": rec.get("period"),
            "unit": rec.get("unit"),
            "value": _norm((rec.text or "").strip()),     # _norm converts "12,345" → 12345.0
        })
    return rows
```

Use `_norm` for numeric strings so thousands separators are handled consistently.

## 3. Register the extension

`detect_kind(file_name)` maps extensions to connector kinds; add the new extension:

```python
def detect_kind(file_name: str) -> str:
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    return {"csv": "csv", "json": "json", "xlsx": "excel", "xlsm": "excel", "xls": "excel", "pdf": "pdf", "txt": "text", "md": "text", "xml": "xml"}.get(ext, "csv")
```

Add the extension to the upload allow-list in `backend/app/ai/guardrails/__init__.py`:

```python
SUPPORTED_UPLOADS = {".csv", ".xlsx", ".xls", ".json", ".pdf", ".txt", ".md", ".xml"}
```

Without this the upload is rejected by the input guardrail (`unsupported_format`).

## 4. Register the data source (optional)

Sources describe where data originates and appear in lineage. Either add to `seed/ecorp_2023/data_sources.yaml`:

```yaml
  - code: SRC-EHS-XML
    name: EHS system XML export
    kind: environmental
    system_name: VelocityEHS
    owner: Group HSE
    description: Monthly environmental parameters exported as XML.
```

or create it at runtime with `POST /datasets/sources` (capability `admin`).

## 5. Upload

```bash
curl -X POST localhost:8000/api/v1/datasets/upload -H "authorization: Bearer $T" \
  -F file=@water_2023.xml -F source_code=SRC-EHS-XML -F dataset_code=DS-EHS-WATER-2023 \
  -F dataset_name="Water 2023 (EHS)" -F period_default=FY2023 -F auto_load=true -F idempotency_key=water-2023-v1
```

Response: `status` (`validated`/`loaded`/`failed`/`duplicate`/`rejected`), `rows`, `valid_rows`, `loaded_values`, `quality` (completeness, validity, uniqueness), `validation_result`. Invalid rows (unknown metric/entity/period, out-of-range values) are kept with their `issues` and visible through `GET /datasets/versions/{id}/records?only_invalid=true`.

Loading respects governance: `check_data_change` blocks writes for periods with an approved/published report (GR-020), and approved/final *reported* values are not overwritten (the record receives a `locked_value` issue).

## 6. Document connectors and the ESG Data Agent

For formats without an explicit metric column, return document-style rows (`kind: "page_text"` / `"candidate_fact"` with `label`, `value`, `unit`) and let analysts map them: `POST /datasets/classify` with the column names proposes metric mappings (`esg_data_agent`), after which a tabular re-upload or manual entry (`POST /metrics/{code}/values`) loads the values with evidence.

## 7. Tests

- Unit: `read_xml(b"<records>…</records>", "x.xml")` returns normalised rows.
- API: upload through `TestClient` with `files={"file": ("x.xml", data, "application/xml")}`, assert `loaded_values`, then `GET /metrics/ENV.WATER.WITHDRAWN/values?period=FY2023` shows `source_type: "ingested"` and the `dataset_version_id`; the lineage graph for the value contains the dataset and source nodes.
- Idempotency: the same `idempotency_key` returns `status: "duplicate"`.
