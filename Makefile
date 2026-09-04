# ESG Nexus — developer shortcuts (Windows: run from Git Bash / WSL)
PY ?= .venv/Scripts/python
ifeq ($(OS),)
PY = .venv/bin/python
endif

.PHONY: help venv api test seed migrate frontend build up down logs lint

help:
	@echo "make venv      create virtualenv + install backend deps"
	@echo "make api       run the API on http://localhost:8000 (auto-seeds SQLite)"
	@echo "make test      run backend tests"
	@echo "make seed      (re)seed the reference dataset"
	@echo "make migrate   apply Alembic migrations"
	@echo "make frontend  run the Vite dev server on http://localhost:5173"
	@echo "make up        docker compose up --build (full stack on :8080)"
	@echo "make lint      ruff lint + format check"

venv:
	python -m venv .venv && $(PY) -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt

api:
	cd backend && ../$(PY) -m uvicorn app.main:app --reload --port 8000

test:
	cd backend && ../$(PY) -m pytest -q

lint:
	cd backend && ../$(PY) -m ruff check . && ../$(PY) -m ruff format --check .

seed:
	cd backend && ../$(PY) -c "from app.core.db import Base, engine, SessionLocal; import app.models; Base.metadata.create_all(engine); from app.seed import Seeder; print(Seeder(SessionLocal()).run())"

migrate:
	cd backend && ../$(PY) -m alembic upgrade head

frontend:
	cd frontend && npm install && npm run dev

build:
	docker compose build

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f backend
