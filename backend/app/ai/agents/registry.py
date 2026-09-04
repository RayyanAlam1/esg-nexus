"""Agent registry (registry pattern): add a class here to make it available to the API and MoE router."""

from __future__ import annotations

from app.ai.agents.base import AgentSpec, BaseAgent
from app.ai.agents.specialists import (
    AssuranceAgent,
    CalculationAgent,
    ESGDataAgent,
    EvaluationAgent,
    EvidenceAgent,
    GovernanceAgent,
    MaterialityAgent,
    RAGResearchAgent,
    ReportingAgent,
    StandardsMappingAgent,
)

AGENTS: dict[str, type[BaseAgent]] = {
    cls.spec.code: cls
    for cls in [
        ESGDataAgent,
        CalculationAgent,
        StandardsMappingAgent,
        MaterialityAgent,
        EvidenceAgent,
        GovernanceAgent,
        RAGResearchAgent,
        ReportingAgent,
        EvaluationAgent,
        AssuranceAgent,
    ]
}


def specs() -> list[AgentSpec]:
    return [cls.spec for cls in AGENTS.values()]


def get(code: str) -> type[BaseAgent]:
    if code not in AGENTS:
        raise KeyError(f"Unknown agent: {code}")
    return AGENTS[code]


def register(cls: type[BaseAgent]) -> None:
    AGENTS[cls.spec.code] = cls
