
import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"  # Company Administrator
    OWNER = "owner"
    PROJECT_MANAGER = "project_manager"
    ENGINEER = "engineer"
    CONSULTANT = "consultant"
    WORKER = "worker"


class EngineerDiscipline(str, enum.Enum):
    ARCHITECTURAL = "architectural"
    CIVIL = "civil"
    ELECTRICAL = "electrical"
    MECHANICAL = "mechanical"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


class ProjectStatus(str, enum.Enum):
    PLANNING = "planning"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    DELAYED = "delayed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ConsultantApprovalMode(str, enum.Enum):
    CENTRALIZED_REVIEW = "CENTRALIZED_REVIEW"
    DISCIPLINE_BASED_REVIEW = "DISCIPLINE_BASED_REVIEW"


class FieldSubmissionStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class EvidencePhotoDirection(str, enum.Enum):
    FRONT = "FRONT"
    BACK = "BACK"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    TOP = "TOP"
    DETAIL = "DETAIL"
    OTHER = "OTHER"


class TaskStatus(str, enum.Enum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    UNDER_REVIEW = "under_review"
    REWORK_REQUIRED = "rework_required"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DependencyType(str, enum.Enum):
    FINISH_TO_START = "finish_to_start"
    START_TO_START = "start_to_start"
    FINISH_TO_FINISH = "finish_to_finish"
    START_TO_FINISH = "start_to_finish"


class RescheduleReason(str, enum.Enum):
    DEPENDENCY_DELAY = "dependency_delay"
    RESOURCE_DELAY = "resource_delay"
    WEATHER = "weather"
    MATERIAL_DELAY = "material_delay"
    DESIGN_CHANGE = "design_change"
    MANUAL = "manual"
    OTHER = "other"


class CostRiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CostValidationStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class DesignChangeStatus(str, enum.Enum):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"


class IssueStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class IssueSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DocumentType(str, enum.Enum):
    DRAWING = "drawing"
    REPORT = "report"
    CONTRACT = "contract"
    PERMIT = "permit"
    SPECIFICATION = "specification"
    INVOICE = "invoice"
    OTHER = "other"


class MediaType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"


class NotificationType(str, enum.Enum):
    TASK_ASSIGNED = "task_assigned"
    TASK_UPDATED = "task_updated"
    TASK_OVERDUE = "task_overdue"
    TASK_RESCHEDULED = "task_rescheduled"
    DESIGN_CHANGE = "design_change"
    COST_ALERT = "cost_alert"
    APPROVAL_REQUEST = "approval_request"
    MESSAGE = "message"
    REPORT_READY = "report_ready"
    SYSTEM = "system"


class NotificationChannel(str, enum.Enum):
    IN_APP = "in_app"
    EMAIL = "email"
    TELEGRAM = "telegram"


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    READ = "read"


class VoiceProcessingStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    LINKED = "linked"
    FAILED = "failed"


class VoiceAnalysisStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    TRANSCRIBING = "TRANSCRIBING"
    ANALYZING = "ANALYZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class VoiceConfirmationStatus(str, enum.Enum):
    PENDING = "PENDING"
    PARTIALLY_CONFIRMED = "PARTIALLY_CONFIRMED"
    CONFIRMED = "CONFIRMED"


class ReportType(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    AI_SUMMARY = "ai_summary"
    SITE_REPORT = "site_report"
    CUSTOM = "custom"


class MessageType(str, enum.Enum):
    DIRECT = "direct"
    PROJECT_CHANNEL = "project_channel"


class ConversationType(str, enum.Enum):
    DIRECT = "DIRECT"
    GROUP = "GROUP"
    PROJECT_CHANNEL = "PROJECT_CHANNEL"
    CONTEXTUAL = "CONTEXTUAL"


class ResourceRequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    FULFILLED = "fulfilled"
