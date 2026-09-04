# Security

This document describes the security controls implemented in the backend (`backend/app/core/security.py`, `main.py`, `api/deps.py`, `ai/guardrails/`) and the hardening expected around a deployment.

Related: [API.md](API.md) · [GOVERNANCE.md](GOVERNANCE.md) · [DEPLOYMENT.md](DEPLOYMENT.md).

---

## 1. Authentication

| Control | Implementation |
|---|---|
| Credentials | Email + password. Passwords are hashed with **PBKDF2-HMAC-SHA256, 310,000 iterations, 16-byte random salt**, stored as `pbkdf2_sha256$<iter>$<salt_b64>$<digest_b64>`; verification uses `hmac.compare_digest`. No compiled dependency. |
| Tokens | JWT (PyJWT, **HS256**) signed with `ESG_SECRET_KEY`. Payload `{sub: user_id, tid: tenant_id, roles: [...], type: access|refresh, iat, exp}`. Access lifetime `ESG_ACCESS_TOKEN_MINUTES` (480), refresh `ESG_REFRESH_TOKEN_DAYS` (14). |
| Transport | `HTTPBearer(auto_error=False)`; missing token → 401 `unauthorized`. Refresh tokens are rejected on protected routes (`type != access`). |
| Principal | `get_principal` reloads the user and role assignments from the database on every request (revoked users and role changes take effect immediately; roles inside the token are informational). Inactive users are rejected. |
| Login audit | Every successful login is written to `audit_logs` (`auth.login`). Failed logins return a generic "Invalid credentials". |
| OIDC | Not implemented; the principal model (`Principal`) is the integration point for an OIDC/SAML dependency. |

---

## 2. RBAC matrix

Roles (`security.ROLES`): `super_admin, org_admin, esg_manager, esg_analyst, data_contributor, reviewer, auditor, executive, report_approver`. Capabilities are role sets in `security.CAPABILITIES`; `Principal.has(capability)` and the `require(capability)` dependency enforce them. `read` is granted to every authenticated user.

| Capability | super_admin | org_admin | esg_manager | esg_analyst | data_contributor | reviewer | auditor | executive | report_approver |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| read | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| data.write | ✓ | ✓ | ✓ | ✓ | ✓ | | | | |
| data.delete | ✓ | ✓ | ✓ | | | | | | |
| metric.write | ✓ | ✓ | ✓ | ✓ | | | | | |
| metric.validate | ✓ | ✓ | ✓ | ✓ | | | | | |
| metric.approve | ✓ | ✓ | ✓ | | | | | | |
| evidence.write | ✓ | ✓ | ✓ | ✓ | ✓ | | | | |
| evidence.verify | ✓ | ✓ | ✓ | | | ✓ | ✓ | | |
| framework.manage | ✓ | ✓ | ✓ | | | | | | |
| governance.manage | ✓ | ✓ | | | | | | | |
| governance.exception | ✓ | ✓ | ✓ | | | | | | |
| ai.run | ✓ | ✓ | ✓ | ✓ | | ✓ | | ✓ | |
| review | ✓ | ✓ | ✓ | | | ✓ | | | |
| report.build | ✓ | ✓ | ✓ | ✓ | | | | | |
| report.approve | ✓ | ✓ | | | | | | | ✓ |
| report.publish | ✓ | ✓ | | | | | | | ✓ |
| audit.read | ✓ | ✓ | ✓ | | | ✓ | ✓ | ✓ | ✓ |
| admin | ✓ | ✓ | | | | | | | |
| tenant.admin | ✓ | | | | | | | | |

Workflow transitions (who may move a report/section into a state) are a separate table, `security.WORKFLOW_TRANSITIONS` — see [GOVERNANCE.md](GOVERNANCE.md#7-approvals-and-workflow-states). Some handlers check capabilities conditionally: `POST /metrics/{code}/status` maps the target status to `data.write`/`metric.validate`/`metric.approve`; `PUT /reports/{id}/sections/{code}` requires `report.build` or `review` to edit content; `POST /reports/{id}/generate?final=true` requires `report.approve`; approving a `report`/`exception` approval requires the `approved` transition right.

`GET /admin/roles` returns the computed capability list per role; `GET /auth/me` returns the caller's capabilities so the frontend can hide unavailable actions (server-side checks remain authoritative).

---

## 3. Tenant isolation

- Every tenant-owned table carries `tenant_id`; every query in routers, tools and engines filters by `principal.tenant_id`. Lookup helpers (`deps.get_org`, `get_metric`, `ToolContext.metric/entity/period`) never return objects from another tenant; direct-by-id reads (`ReportBuilder.report`, `dataset_detail`, `run_detail`, `download`) verify `obj.tenant_id == principal.tenant_id`.
- The tenant is taken from the authenticated user (`users.tenant_id`), never from request parameters.
- Global tables (frameworks, agents, templates, roles) are read-only for tenants; only `super_admin` (`tenant.admin`) can reseed.

---

## 4. Organisation and entity scoping

- `user_roles.organization_id` restricts `GET /organizations` and the default organisation resolution to the assigned organisations (`Principal.organization_ids`).
- `user_roles.entity_id` restricts data access to a subtree root: `deps.get_entity` and `ToolContext.entity` raise 403 / `PermissionError` for entities outside `Principal.entity_ids`. The seeded contributor is scoped to `EFERT`. Note that scoping is enforced on entity *lookups*; list endpoints that aggregate across entities (for example `GET /esg/entity-comparison`) are not filtered by entity scope in this release.

---

## 5. Dataset, document and evidence permissions

| Object | Column | Enforcement |
|---|---|---|
| Knowledge documents | `knowledge_documents.permissions {"roles": [...]}` | Enforced in `ai/rag/retriever.py::_allowed` on every retrieval (permission-aware RAG) and reported as `accessible` by `GET /knowledge/documents`. |
| Datasets | `datasets.permissions` | Stored; **not enforced** by the current routers. |
| Evidence | `evidence.permissions` | Stored; **not enforced** by the current routers. |

Uploaded evidence and dataset files are hashed (SHA-256) and the hash is recorded on the version/evidence row; report files carry a SHA-256 in `report_versions.file_hash`.

---

## 6. Request-level controls (`main.py`)

| Control | Detail |
|---|---|
| Rate limiting | Sliding 60-second window per client IP, `ESG_RATE_LIMIT_PER_MINUTE` (600). Exceeding returns 429 `rate_limited`. Buckets are in-process memory (per worker); use a gateway limiter for multi-replica deployments. |
| CORS | `ESG_CORS_ORIGINS` (default localhost 5173/3000/8080), credentials allowed, all methods/headers. Restrict to the frontend origin in production. |
| Security headers | `x-content-type-options: nosniff`, `x-frame-options: DENY`, `referrer-policy: strict-origin-when-cross-origin` on every response. HSTS/CSP are expected from the TLS-terminating proxy. |
| Request id | `x-request-id` echoed or generated; bound to structured logs. |
| Error handling | Uniform envelope; stack traces are never returned. Validation errors expose field paths only. |

---

## 7. Input and output validation

- **Schema validation** — Pydantic v2 models for every JSON body; unknown fields ignored; `EmailStr` on login and user creation.
- **ESG value guardrail** — `validate_esg_value` on manual writes and ingestion rows (type, min/max, percentage range); HIGH findings reject the write with 422 `guardrail_rejected`.
- **File uploads** — extension allow-list (`.csv .xlsx .xls .json .pdf .txt .md`) via `guardrails.check_input(file_name=…)`; files are read fully into memory (size limits belong at the proxy).
- **Expressions** — formulas and rule conditions are parsed against an AST whitelist (`engines/safe_expr.py`); `eval` runs with empty builtins and only whitelisted helpers. Rule creation syntax-checks the condition.
- **AI input** — prompt-injection patterns, sensitive-data patterns (API keys, passwords, card numbers, CNIC, JWTs), size limit; blocked inputs never reach the provider and are recorded as blocked runs.
- **AI output** — unsupported numbers (CRITICAL, blocked), missing citations, compliance claims, confidentiality leakage (CRITICAL), framework mismatch. Raw model text never becomes a disclosure: sections stay `requires_review`/`blocked` until humans approve.
- **Governance** — `PREVENT_DATA_MODIFICATION` rules (GR-020) are checked before any metric value write once a report for the period is approved/published.

---

## 8. Secrets and configuration

- All configuration comes from environment variables with the `ESG_` prefix (`core/config.py`), optionally from `.env` (ignored by git; `.env.example` is the template).
- `ESG_SECRET_KEY` defaults to `change-me-in-production` — **must** be overridden outside development.
- `ANTHROPIC_API_KEY` is read by the SDK from the environment and never logged; provider errors are reduced to short codes (`authentication_failed`, `rate_limited`, …).
- Demo passwords are seeded from `seed/ecorp_2023/organization.yaml` and are intended for local evaluation; rotate or remove the demo users (`PUT /admin/users/{id}/roles`, or edit the seed) before exposing an instance.
- Database credentials, MinIO keys and the secret key are injected by Compose from `.env`; in Kubernetes mount them as Secrets.

---

## 9. Audit and observability

Append-only `audit_logs` for every state change (see [GOVERNANCE.md](GOVERNANCE.md#10-audit-trail)); structured logs with request ids (JSON when `ESG_JSON_LOGS=true`); `model_runs` for every LLM call; `agent_runs.guardrail_result` for every guardrail decision.

---

## 10. Deployment hardening checklist

- [ ] Set a strong `ESG_SECRET_KEY` (≥ 32 random bytes) and rotate it on compromise (invalidates all tokens).
- [ ] Set `ESG_ENVIRONMENT=production` (disables `create_all`; run Alembic migrations explicitly) and `ESG_DEBUG=false`.
- [ ] Terminate TLS at a reverse proxy/ingress; add HSTS and a Content-Security-Policy; forward the client IP (`X-Forwarded-For`) so rate limiting and audit `ip` are meaningful, or rate-limit at the proxy.
- [ ] Restrict `ESG_CORS_ORIGINS` to the frontend origin(s).
- [ ] Lower `ESG_RATE_LIMIT_PER_MINUTE` to fit expected traffic; enforce upload size limits at the proxy.
- [ ] Replace demo users; enforce password policy at user creation (not enforced by the API); consider shorter `ESG_ACCESS_TOKEN_MINUTES`.
- [ ] Set `ESG_AUTO_SEED=false` after the initial load in production.
- [ ] Use PostgreSQL with TLS, least-privilege roles and encrypted volumes; back up the database and `ESG_LOCAL_STORAGE_DIR` together.
- [ ] Keep `ESG_AI_PROVIDER=offline` in air-gapped environments; when using `anthropic`, store `ANTHROPIC_API_KEY` in a secret store and review data-residency requirements for prompt content (facts blocks contain metric values and evidence excerpts).
- [ ] Run the API as the non-root `esg` user (already configured in the Dockerfile) and mount `/data/storage` on a persistent, backed-up volume.
- [ ] Monitor `/health/ready`, 401/403/429 rates, `agent_runs.status = blocked` and `model_runs.status = error`.
- [ ] Review knowledge-document `permissions` before adding internal documents to the RAG corpus.
