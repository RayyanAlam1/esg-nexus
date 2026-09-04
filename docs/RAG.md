# Retrieval-Augmented Generation

ESG Nexus implements *agentic RAG*: retrieval is a controlled tool (`search_knowledge_base`) that agents call while gathering facts, not a free-text channel to the model. The default index is an in-process BM25 lexical index that works air-gapped; a pgvector adapter is provided as an extension point.

Related: [AGENTS.md](AGENTS.md) · [DATABASE.md](DATABASE.md#39-ai-knowledge-evaluation-modelsaipy) · [DEPLOYMENT.md](DEPLOYMENT.md).

---

## 1. Knowledge documents

Documents live in `knowledge_documents` (tenant-scoped) with chunks in `knowledge_chunks`. The seeder (`seed/loader.py::_knowledge_base`) creates five documents for the reference tenant:

| Code | Kind | Content | Chunking | Permissions | Freshness |
|---|---|---|---|---|---|
| `KB-REPORT-2023` | report | Engro Sustainability Report 2023, one chunk per PDF page (`seed/ecorp_2023/report_pages.json`; pages with < 40 characters skipped; text capped at 6,000 characters) | `chunk_index = pdf_page`, `meta = {pdf_page, printed_pages, source: "report"}` | all roles | 2024-07-01 |
| `KB-METRIC-DEFINITIONS` | metric_definition | One chunk per metric: code, name, pillar, topic, unit, kind, description, formula, method, frameworks | `meta = {metric_code}` | all roles | seed date |
| `KB-FW-<CODE>` (×7) | framework | One chunk per requirement: code, title, description, disclosure type, metric codes, guidance | `meta = {requirement_code, framework}` | all roles | framework effective date |
| `KB-POLICIES` | policy | Governance policies and governance rules (code, severity, action, description, condition, required action) | `meta = {policy_code}` / `{rule_code}` | super_admin, org_admin, esg_manager, reviewer, auditor, report_approver, executive, esg_analyst — **not** data_contributor | seed date |
| `KB-METHODOLOGY` | methodology | Nine methodology statements (TRIR, LTIFR, turnover, intensities, renewable %, water balance, consolidation, quality weights, readiness weights) | `meta = {source: "methodology"}` | all roles | seed date |

Document fields: `code, title, kind (framework|policy|report|methodology|metric_definition|evidence|internal|regulation), version, source_ref, freshness_date, permissions {"roles": [...]}, status (approved|draft|retired), meta`. Only `approved` documents are indexed.

There is no upload API for knowledge documents in this release; documents are created by the seeder or directly through the models (see §7).

---

## 2. Indexing (`ai/rag/index.py`)

### Tokenisation

`tokenize(text)`: lower-case, regex `[a-z0-9][a-z0-9.\-]*`, stop-word list (`the a an of and or to in for on by with is are was were be as at from that this it its their our we they which what how why when where than into per vs`), tokens longer than one character. Metric codes such as `env.ghg.scope1` and requirement codes such as `gri.305-1` survive as single tokens.

### LexicalIndex (BM25)

- Built per tenant over chunks of approved documents; parameters `k1 = 1.5`, `b = 0.75`.
- IDF: `log(1 + (N − df + 0.5) / (df + 0.5))`.
- Score per term: `idf × tf × (k1 + 1) / (tf + k1 × (1 − b + b × dl / avgdl))`.
- `search(query, limit)` returns `(chunk_id, score)` pairs ranked descending.
- `get_index(db, tenant_id)` caches one index per tenant in `_INDEX_CACHE` keyed by chunk count; the index is rebuilt when the number of chunks changes. Editing chunk text without changing the count does not invalidate the cache in the running process.

### PgVectorIndex (extension point)

`PgVectorIndex(db, tenant_id, embed)` embeds the query with the supplied callable, loads chunks whose `embedding` is not NULL and computes cosine similarity in Python. The docstring gives the native replacement once `embedding` is a `vector` column:

```sql
SELECT id, 1 - (embedding <=> :q) AS score FROM knowledge_chunks ORDER BY embedding <=> :q LIMIT :k
```

Nothing constructs `PgVectorIndex` yet: `ESG_EMBEDDING_PROVIDER` accepts `none|voyage` but only `none` is implemented.

---

## 3. Retrieval (`ai/rag/retriever.py::retrieve`)

```
retrieve(db, principal, query, limit=6, kind=None, rerank=True)
  1. candidates = index.search(query, limit=max(limit*5, 30))
  2. for each candidate chunk:
       document must belong to principal.tenant_id and be status == "approved"
       permission filter: doc.permissions.roles contains "*" or intersects principal.roles
       optional kind filter (report | framework | policy | methodology | metric_definition | …)
  3. rerank (default on):
       coverage = |query tokens ∩ chunk tokens| / |query tokens|
       exact    = 1 if any dotted query token (e.g. ENV.GHG.SCOPE1, GRI.305-1) appears verbatim in the chunk
       final    = bm25 × (1 + coverage) + 2 × exact
  4. sort by final score, return top `limit` Hit objects
```

`Hit` fields: `chunk_id, document_code, document_title, kind, text, score, meta, version, freshness` and the derived `citation`.

Permission filtering happens **after** index search and **before** the results are returned, so a user never sees a chunk from a document their roles cannot access. The seeded `KB-POLICIES` document demonstrates this: `contributor@ecorp.local` (data_contributor) receives no policy or rule passages, and `GET /knowledge/documents` reports `accessible: false` for it.

---

## 4. Citations

`Hit.citation` is deterministic:

| Document kind / meta | Citation |
|---|---|
| `report` with `printed_pages` or `pdf_page` | `[KB-REPORT-2023 p.81-82]` |
| `requirement_code` in meta | `[GRI.305-1]` |
| `metric_code` in meta | `[ENV.GHG.SCOPE1]` |
| `policy_code` / `rule_code` in meta | `[POL-COC]` / `[GR-011]` |
| otherwise | `[<document_code>#<chunk_index>]` |

Metric values fetched through tools carry their own citation `[<metric> · <entity> · <period>]` and evidence codes `[EV-RPT23-P81]`. The evaluation scorer (`ai/agents/evaluation.py`) checks every `[...]` in a narrative against the set of citations supplied in the facts (exact match or same first token), and the output guardrail requires at least one citation or source for narrative outputs.

---

## 5. Freshness and versioning

- Every document carries `version` and `freshness_date`; both are returned on each hit (`version`, `freshness`) and are visible to agents and the Copilot response (`passages[].freshness`).
- Framework documents inherit the framework version and effective date (`KB-FW-GRI` → `2021`, 2023-01-01).
- Retired or draft documents (`status != approved`) are excluded from the index and from results.
- Re-seeding (`POST /admin/reseed`) only creates chunks when a document is new or has no chunks; to refresh an existing document, delete its chunks (or the document) and re-seed, which also invalidates the cached index by changing the chunk count.

---

## 6. API surface

| Endpoint | Purpose |
|---|---|
| `GET /knowledge/documents` | Documents with chunk counts and `accessible` for the caller |
| `POST /knowledge/search` `{query, limit, kind}` | Direct retrieval (returns `index: "lexical-bm25"`, `permission_filtered: true`) |
| tool `search_knowledge_base(query, limit, kind)` | Same retrieval from inside agents |
| `POST /copilot/ask` | Retrieval through the RAG Research Agent and other experts |

---

## 7. Enabling pgvector

The Docker database image is `pgvector/pgvector:pg16` and `deploy/postgres/init.sql` runs `CREATE EXTENSION IF NOT EXISTS vector;` at first initialisation. Steps to move from BM25 to vector or hybrid retrieval:

1. **Column type.** Add an Alembic revision that changes `knowledge_chunks.embedding` from JSON to `vector(<dim>)` (for example `vector(1024)`), e.g. with `sqlalchemy` + `pgvector.sqlalchemy.Vector`, and create an index: `CREATE INDEX ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);`.
2. **Embedding provider.** Implement an `embed(text) -> list[float]` callable behind `ESG_EMBEDDING_PROVIDER` (the enum already reserves `voyage`); add its API key to settings and `.env.example`. Populate embeddings for existing chunks in a one-off job (a natural addition to `app/worker.py::JOBS`).
3. **Index adapter.** Replace `PgVectorIndex.search` with the SQL above (parameterised by tenant) or keep the Python cosine fallback for small corpora.
4. **Retriever wiring.** In `ai/rag/retriever.py::retrieve`, choose the index from settings (`LexicalIndex` when `embedding_provider == "none"`, otherwise `PgVectorIndex`, or merge both candidate lists for hybrid search) — the permission filter, kind filter and reranking stay unchanged because they operate on `(chunk_id, score)` pairs.
5. **Seeder.** Compute embeddings in `_knowledge_base` when the provider is configured so that new chunks are searchable immediately.

Air-gapped deployments keep `ESG_EMBEDDING_PROVIDER=none` and `ESG_AI_PROVIDER=offline`; BM25 needs no external service.

---

## 8. Adding knowledge

Until an upload endpoint exists, add documents through the seeder pattern:

```python
from datetime import date
from app.models import KnowledgeDocument, KnowledgeChunk

doc = KnowledgeDocument(tenant_id=tenant_id, code="KB-POL-HSE-2024", title="HSE Policy 2024", kind="policy",
                        version="2024", source_ref="hse-policy-2024.pdf", freshness_date=date(2024, 1, 1),
                        permissions={"roles": ["*"]}, status="approved")
db.add(doc); db.flush()
for i, text in enumerate(chunks):                     # split on headings/pages, ≤ ~6,000 characters each
    db.add(KnowledgeChunk(document_id=doc.id, chunk_index=i, text=text, meta={"policy_code": "POL-HSE", "page": i + 1}))
db.commit()
```

Chunk `meta` keys drive citations (see §4); set `permissions.roles` to restrict visibility, and keep `status="approved"` only for content that may be quoted to users.
