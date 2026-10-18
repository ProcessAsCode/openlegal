"""SQLAlchemy 2.0 declarative models for OpenLegal.

Importing this package registers every model with the shared `Base.metadata`,
which is what Alembic walks at autogenerate time.
"""

from openlegal.models.agent import (
    AgentMessage,
    AgentRun,
    AgentRunStatus,
    AgentStep,
    AgentStepPhase,
    GuardrailVerdict,
)
from openlegal.models.ai_decision import AIDecision, AIDecisionStatus
from openlegal.models.attachment import Attachment, StorageBackend
from openlegal.models.audit_log import AuditLog
from openlegal.models.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from openlegal.models.case import (
    Case,
    CaseOwnership,
    CasePriority,
    CaseStatus,
)
from openlegal.models.case_event import (
    CaseEvent,
    CaseEventActorType,
    CaseEventType,
)
from openlegal.models.comment import Comment, CommentType
from openlegal.models.connection import (
    Connection,
    ConnectionKind,
    ConnectionStatus,
)
from openlegal.models.dmn_evaluation import DMNEvaluation
from openlegal.models.expert_group import ExpertGroup, ExpertGroupMembership
from openlegal.models.organization import Organization
from openlegal.models.signal import Signal, SignalSource, SignalStatus
from openlegal.models.taxonomy import ServiceTier, TaxonomyNode
from openlegal.models.uapf_execution import (
    UAPFCapabilityInvocation,
    UAPFExecution,
    UAPFExecutionStatus,
    UAPFInvocationStatus,
)
from openlegal.models.uapf_session import UAPFSession, UAPFSessionState
from openlegal.models.user import User, UserRole
from openlegal.models.vc_reference import VCReference, VCType

__all__ = [
    # Base
    "Base",
    "TenantScopedMixin",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    # Tenancy & identity
    "Organization",
    "User",
    "UserRole",
    "ExpertGroup",
    "ExpertGroupMembership",
    # Configuration
    "Connection",
    "ConnectionKind",
    "ConnectionStatus",
    "TaxonomyNode",
    "ServiceTier",
    # Incident core
    "Signal",
    "SignalSource",
    "SignalStatus",
    "Case",
    "CaseStatus",
    "CasePriority",
    "CaseOwnership",
    "CaseEvent",
    "CaseEventType",
    "CaseEventActorType",
    "Comment",
    "CommentType",
    "Attachment",
    "StorageBackend",
    # AI & decisions
    "AIDecision",
    "AIDecisionStatus",
    "DMNEvaluation",
    # Evidence
    "VCReference",
    "VCType",
    # UAPF
    "UAPFExecution",
    "UAPFExecutionStatus",
    "UAPFCapabilityInvocation",
    "UAPFInvocationStatus",
    "UAPFSession",
    "UAPFSessionState",
    # Audit
    "AuditLog",
]
from openlegal.models.legal_agreement import AgreementStatus, LegalAgreement  # noqa: F401
