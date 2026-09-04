from fastapi import APIRouter

from app.api.v1 import admin, agents, auth, datasets, esg, evidence, frameworks, governance, materiality, metrics, organizations, reports

api_router = APIRouter()
for r in [
    auth.router,
    organizations.router,
    esg.router,
    metrics.router,
    metrics.targets_router,
    metrics.calc_router,
    datasets.router,
    datasets.quality_router,
    datasets.lineage_router,
    evidence.router,
    frameworks.router,
    materiality.router,
    governance.router,
    governance.audit_router,
    agents.router,
    agents.copilot_router,
    agents.knowledge_router,
    agents.evaluations_router,
    reports.router,
    admin.router,
]:
    api_router.include_router(r)
