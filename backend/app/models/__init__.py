"""
Central import point for all SQLAlchemy models.
This ensures Alembic detects all tables during autogeneration.
"""

# Base + enums (important first)

from app.db.database import Base

from app.models.enums import (
    UserRole,
    EngineerDiscipline,
    UserStatus,
    ProjectStatus,
    ConsultantApprovalMode,
    FieldSubmissionStatus,
    EvidencePhotoDirection,
    TaskStatus,
    TaskPriority,
    DependencyType,
    RescheduleReason,
    CostRiskLevel,
    CostValidationStatus,
    DesignChangeStatus,
    IssueStatus,
    IssueSeverity,
    DocumentType,
    MediaType,
    NotificationType,
    NotificationChannel,
    NotificationStatus,
    VoiceProcessingStatus,
    VoiceAnalysisStatus,
    VoiceConfirmationStatus,
    ReportType,
    MessageType,
    ConversationType,
    ResourceRequestStatus,
)

# Core models
from app.models.company import Company
from app.models.password_reset import PasswordResetToken
from app.models.user import User, EngineerProfile
from app.models.project import Project, ProjectMember, ProjectConsultantReviewer, ProjectViewState
from app.models.permission import ConsultantEngineerScope, RolePermissionOverride, UserPermissionOverride
from app.models.milestone import Milestone
from app.models.task import Task, TaskDependency, TaskRescheduleLog, TaskComment, TaskReview
from app.models.message import Conversation, ConversationParticipant, Message

# Cost system (owner protection feature)
from app.models.cost_validation import CostValidation

# Engineering coordination
from app.models.design_change import DesignChange, DesignChangeAffectedDiscipline

# Issue tracking
from app.models.issue import Issue

# Documents + media
from app.models.document import Document, MediaAsset
from app.models.attachment import Attachment
from app.models.field_submission import (
    FieldSubmission,
    FieldSubmissionPhoto,
    PhotoCategory,
    PhotoCategoryAssignment,
)

# Reports + AI + voice system
from app.models.site_report import SiteReport
from app.models.voice_recording import VoiceRecording
from app.models.voice_analysis import VoiceAnalysis
from app.models.voice_action import VoiceActionDraft, VoiceClarification, VoiceExecutionLog
from app.models.ai_governance import AIActionVersion, DomainEvent, AIProviderCall

# Notifications
from app.models.notification import Notification
from app.models.audit_log import AuditLog
from app.models.revoked_token import RevokedToken
from app.models.ifc import (
    IFCModelGroup,
    IFCModelVersion,
    IFCSpatialNode,
    IFCElement,
    IFCEntityLink,
    IFCComparison,
    IFCChangeRecord,
    IFCImpactSuggestion,
    IFCCoordinationFinding,
    IFCSuggestion,
    IFCProcessingJob,
    AIInsight,
)
from app.models.collaboration import (
    OwnerRequest, MessageRecipientState, ReminderRule, ReminderEvent,
    SiteVisit, SiteVisitParticipant, AIInsightSource,
)

