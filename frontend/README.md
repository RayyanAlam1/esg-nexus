# ESG Nexus — Frontend

React 18 + TypeScript + Vite single-page app for the ESG Nexus platform (Intelligence, Governance & Reporting).

## Stack

- React 18, TypeScript (strict), Vite 5
- Tailwind CSS 3 (light enterprise theme, navy `#0F2A44` / teal `#1B7F79`)
- React Router v6, TanStack Query v5
- Recharts (trend / comparison / materiality matrix), custom SVG lineage graph
- lucide-react icons, react-markdown for narratives and Copilot answers

## Development

Prerequisites: Node 20+ (Node 24 tested) and the backend running on `http://localhost:8000`.

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 — /api and /health are proxied to http://localhost:8000
```

Other scripts:

```bash
npm run typecheck  # tsc --noEmit
npm run build      # tsc --noEmit && vite build → dist/
npm run preview    # serve dist/ on 5173
```

The API base is `import.meta.env.VITE_API_BASE` (default `/api/v1`). Copy `.env.example` to `.env.local` to override.

## Demo accounts (seeded tenant: Engro Corporation, FY2022–FY2023)

| Email | Password | Roles |
| --- | --- | --- |
| admin@esgnexus.local | Admin!2024 | super_admin, org_admin |
| cso@ecorp.local | Exec!2024 | executive |
| manager@ecorp.local | Manager!2024 | esg_manager |
| analyst@ecorp.local | Analyst!2024 | esg_analyst |
| contributor@ecorp.local | Data!2024 | data_contributor |
| reviewer@ecorp.local | Review!2024 | reviewer |
| approver@ecorp.local | Approve!2024 | report_approver |
| auditor@ecorp.local | Audit!2024 | auditor |

The login page lists these; click a row to sign in.

## Structure

```
src/
  app/          router (App.tsx), auth context, period/entity context, navigation config
  api/          fetch wrapper (client.ts), response types (types.ts), one module per backend router with TanStack hooks
  components/   AppShell (sidebar, topbar, breadcrumbs, Copilot slide-over), ui/ primitives, charts/
  features/     one folder per area: dashboard, esg, metrics, data, standards, materiality, evidence, ai, governance, reports, admin
  lib/          number/date formatting (null → "Data unavailable"), colours, small hooks
```

Conventions:

- Period and entity are chosen in the top bar, persisted in `localStorage`, and passed as `period=` / `entity=` query params to every endpoint that accepts them.
- The JWT lives in `localStorage`; `api/client.ts` adds `Authorization: Bearer`, unwraps the `{error:{code,message,details}}` envelope into `ApiError {status, code, message, details}`, and redirects to `/login` on 401.
- `ErrorBanner` renders `governance_blocked` / `guardrail_rejected` errors with the `required_action` and `reason` details prominently.
- Navigation items are hidden when the user lacks the capability (e.g. `admin`, `audit.read`, `ai.run`, `report.build`); routes are additionally guarded.
- Numbers use thousands separators and at most two decimals; `null` is always rendered as "Data unavailable", never as 0.
- Chart colours: single-series marks use the brand teal, previous period grey; pillar colours are the validated categorical set (`#2a78d6`, `#eb6834`, `#1baf7a`, `#4a3aa7`); severity colours are reserved for status.

## Docker

```bash
docker build -t esg-nexus-frontend ./frontend
```

`Dockerfile` is multi-stage (node build → nginx:alpine). `nginx.conf` serves the SPA with history fallback and proxies `/api/` and `/health` to `http://backend:8000` (the docker-compose service name). The compose file in the repository root builds this image and exposes it on port 8080.

## Report preview note

The report preview injects backend-rendered page HTML (`GET /reports/{id}/preview`). That HTML is produced by the server-side renderer from governed data with all text HTML-escaped; it is not user-supplied markup.
