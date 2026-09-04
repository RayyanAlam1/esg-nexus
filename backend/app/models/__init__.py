"""Import every model so SQLAlchemy metadata is complete (Alembic + create_all)."""

from app.models.ai import Agent, AgentRun, Evaluation, KnowledgeChunk, KnowledgeDocument, ModelRun, QualityScore
from app.models.audit import AuditLog, Notification
from app.models.data import Dataset, DatasetRecord, DatasetVersion, DataSource
from app.models.esg import CalculationRun, CalculationVersion, EsgSubtopic, EsgTopic, MetricDefinition, MetricValue, Target
from app.models.evidence import Evidence, EvidenceLink
from app.models.frameworks import Framework, FrameworkMapping, FrameworkVersion, OrganizationFramework, Requirement
from app.models.governance import Approval, GovernancePolicy, GovernanceRule, Issue
from app.models.identity import Role, Tenant, User, UserRole
from app.models.materiality import MaterialityAssessment, MaterialityTopic, StakeholderInput
from app.models.organization import Entity, Organization, ReportingPeriod
from app.models.reporting import Report, ReportSection, ReportTemplate, ReportVersion

__all__ = [
    "Agent",
    "AgentRun",
    "Approval",
    "AuditLog",
    "CalculationRun",
    "CalculationVersion",
    "DataSource",
    "Dataset",
    "DatasetRecord",
    "DatasetVersion",
    "Entity",
    "EsgSubtopic",
    "EsgTopic",
    "Evaluation",
    "Evidence",
    "EvidenceLink",
    "Framework",
    "FrameworkMapping",
    "FrameworkVersion",
    "GovernancePolicy",
    "GovernanceRule",
    "Issue",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "MaterialityAssessment",
    "MaterialityTopic",
    "MetricDefinition",
    "MetricValue",
    "ModelRun",
    "Notification",
    "Organization",
    "OrganizationFramework",
    "QualityScore",
    "Report",
    "ReportSection",
    "ReportTemplate",
    "ReportVersion",
    "ReportingPeriod",
    "Requirement",
    "Role",
    "StakeholderInput",
    "Target",
    "Tenant",
    "User",
    "UserRole",
]
