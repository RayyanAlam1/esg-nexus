# Contributing

Thanks for your interest in ESG Nexus. This page covers the workflow; design and code conventions are in
[docs/ONBOARDING.md](docs/ONBOARDING.md) and the how-to guides in [docs/guides](docs/guides).

## Development setup

```bash
# backend
cd backend
python -m venv ../.venv && ../.venv/Scripts/pip install -r requirements.txt -r requirements-dev.txt   # Linux/macOS: ../.venv/bin/pip
../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# frontend
cd frontend && npm install && npm run dev
```

The API seeds the reference dataset into SQLite on first start. Delete `backend/esg_nexus.db` to reseed.

## Branches and pull requests

- Branch from `main`: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `chore/<topic>`.
- Keep pull requests focused; one logical change per PR.
- Fill in the pull-request template. CI must be green (lint, tests, typecheck, build, CodeQL, dependency review).
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `feat(metrics): add renewable share metric`.

## Quality gates

| Area | Command |
|---|---|
| Backend lint | `cd backend && ruff check .` |
| Backend tests | `cd backend && pytest` |
| Frontend typecheck | `cd frontend && npx tsc --noEmit` |
| Frontend build | `cd frontend && npm run build` |
| Migrations | `cd backend && alembic revision --autogenerate -m "…"` after model changes |

## Data integrity rules

1. Never invent ESG figures. A missing value is `Data unavailable`; a missing document is `Evidence required`.
2. Every seeded value cites its evidence (`evidence: [P80]` → report page 80).
3. Frameworks, templates and governance rules are configuration, not code.
4. Report inconsistencies found in source documents are surfaced as data-quality findings, not silently corrected.

## Releases

Tag `main` with a semantic version (`v1.2.0`). The release workflow publishes versioned container images to
GitHub Container Registry and creates a GitHub Release with generated notes. Update `CHANGELOG.md` in the same PR.
