"""baseline

Revision ID: b2ac9f00788a
Revises: 
Create Date: 2026-06-16 17:42:52.857619

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = 'b2ac9f00788a'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # Helper function to check if enum exists
    def enum_exists(enum_name: str) -> bool:
        result = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = :enum_name)"),
            {"enum_name": enum_name}
        ).scalar()
        return result
    
    # Create all enum types with create_type=False to prevent auto-creation
    # This tells SQLAlchemy "the enum already exists or will be created manually"
    
    # user_status enum
    user_status = postgresql.ENUM(
        "active", "inactive", "suspended", "pending",
        name="user_status",
        create_type=False  # Don't auto-create
    )
    if not enum_exists('user_status'):
        user_status.create(conn, checkfirst=True)
    
    # user_role enum
    user_role = postgresql.ENUM(
        'ADMIN', 'OWNER', 'PROJECT_MANAGER', 'ARCHITECT', 
        'CIVIL_ENGINEER', 'ELECTRICAL_ENGINEER', 'MECHANICAL_ENGINEER', 
        'CONTRACTOR', 'SUPERVISOR',
        name='user_role',
        create_type=False  # Don't auto-create
    )
    if not enum_exists('user_role'):
        user_role.create(conn, checkfirst=True)
    
    # engineer_discipline enum
    engineer_discipline = postgresql.ENUM(
        'ARCHITECT', 'CIVIL', 'ELECTRICAL', 'MECHANICAL',
        name='engineer_discipline',
        create_type=False
    )
    if not enum_exists('engineer_discipline'):
        engineer_discipline.create(conn, checkfirst=True)
    
    # project_status enum
    project_status = postgresql.ENUM(
        'PLANNING', 'ACTIVE', 'ON_HOLD', 'DELAYED', 'COMPLETED', 'CANCELLED',
        name='project_status',
        create_type=False
    )
    if not enum_exists('project_status'):
        project_status.create(conn, checkfirst=True)
    
    # cost_risk_level enum
    cost_risk_level = postgresql.ENUM(
        'LOW', 'MEDIUM', 'HIGH', 'CRITICAL',
        name='cost_risk_level',
        create_type=False
    )
    if not enum_exists('cost_risk_level'):
        cost_risk_level.create(conn, checkfirst=True)
    
    # cost_validation_status enum
    cost_validation_status = postgresql.ENUM(
        'PENDING', 'APPROVED', 'REJECTED', 'NEEDS_REVIEW',
        name='cost_validation_status',
        create_type=False
    )
    if not enum_exists('cost_validation_status'):
        cost_validation_status.create(conn, checkfirst=True)
    
    # task_status enum
    task_status = postgresql.ENUM(
        'BACKLOG', 'TODO', 'IN_PROGRESS', 'UNDER_REVIEW', 'BLOCKED', 'DONE', 'CANCELLED',
        name='task_status',
        create_type=False
    )
    if not enum_exists('task_status'):
        task_status.create(conn, checkfirst=True)
    
    # task_priority enum
    task_priority = postgresql.ENUM(
        'LOW', 'MEDIUM', 'HIGH', 'CRITICAL',
        name='task_priority',
        create_type=False
    )
    if not enum_exists('task_priority'):
        task_priority.create(conn, checkfirst=True)
    
    # design_change_status enum
    design_change_status = postgresql.ENUM(
        'PROPOSED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'IMPLEMENTED',
        name='design_change_status',
        create_type=False
    )
    if not enum_exists('design_change_status'):
        design_change_status.create(conn, checkfirst=True)
    
    # document_type enum
    document_type = postgresql.ENUM(
        'DRAWING', 'REPORT', 'CONTRACT', 'PERMIT', 'SPECIFICATION', 'INVOICE', 'OTHER',
        name='document_type',
        create_type=False
    )
    if not enum_exists('document_type'):
        document_type.create(conn, checkfirst=True)
    
    # issue_severity enum
    issue_severity = postgresql.ENUM(
        'LOW', 'MEDIUM', 'HIGH', 'CRITICAL',
        name='issue_severity',
        create_type=False
    )
    if not enum_exists('issue_severity'):
        issue_severity.create(conn, checkfirst=True)
    
    # issue_status enum
    issue_status = postgresql.ENUM(
        'OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED',
        name='issue_status',
        create_type=False
    )
    if not enum_exists('issue_status'):
        issue_status.create(conn, checkfirst=True)
    
    # dependency_type enum
    dependency_type = postgresql.ENUM(
        'FINISH_TO_START', 'START_TO_START', 'FINISH_TO_FINISH', 'START_TO_FINISH',
        name='dependency_type',
        create_type=False
    )
    if not enum_exists('dependency_type'):
        dependency_type.create(conn, checkfirst=True)
    
    # reschedule_reason enum
    reschedule_reason = postgresql.ENUM(
        'DEPENDENCY_DELAY', 'RESOURCE_DELAY', 'WEATHER', 'MATERIAL_DELAY', 
        'DESIGN_CHANGE', 'MANUAL', 'OTHER',
        name='reschedule_reason',
        create_type=False
    )
    if not enum_exists('reschedule_reason'):
        reschedule_reason.create(conn, checkfirst=True)
    
    # voice_processing_status enum
    voice_processing_status = postgresql.ENUM(
        'UPLOADED', 'TRANSCRIBING', 'TRANSCRIBED', 'LINKED', 'FAILED',
        name='voice_processing_status',
        create_type=False
    )
    if not enum_exists('voice_processing_status'):
        voice_processing_status.create(conn, checkfirst=True)
    
    # media_type enum
    media_type = postgresql.ENUM(
        'IMAGE', 'VIDEO', 'AUDIO', 'DOCUMENT',
        name='media_type',
        create_type=False
    )
    if not enum_exists('media_type'):
        media_type.create(conn, checkfirst=True)

    notification_type = postgresql.ENUM(
        'TASK_ASSIGNED','TASK_UPDATED','TASK_OVERDUE','TASK_RESCHEDULED','DESIGN_CHANGE',
        'COST_ALERT','APPROVAL_REQUEST','MESSAGE','REPORT_READY','SYSTEM',
        name='notification_type', create_type=False
    )
    if not enum_exists('notification_type'):
        notification_type.create(conn, checkfirst=True)
    notification_status = postgresql.ENUM('PENDING','SENT','FAILED','READ', name='notification_status', create_type=False)
    if not enum_exists('notification_status'):
        notification_status.create(conn, checkfirst=True)
    
    # Now create all tables - use the enum objects we defined above
    op.create_table('users',
        sa.Column('full_name', sa.String(length=150), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('phone_number', sa.String(length=30), nullable=True),
        sa.Column('avatar_url', sa.String(length=500), nullable=True),
        # Use the enum objects directly (with create_type=False)
        sa.Column('role', user_role, nullable=False),
        sa.Column('status', user_status, nullable=False, server_default=text("'pending'::user_status")),
        sa.Column('is_email_verified', sa.Boolean(), nullable=False),
        sa.Column('is_superuser', sa.Boolean(), nullable=False),
        sa.Column('last_login_at', sa.String(), nullable=True),
        sa.Column('telegram_chat_id', sa.String(length=64), nullable=True),
        sa.Column('notify_by_email', sa.Boolean(), nullable=False),
        sa.Column('notify_by_telegram', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)
    
    op.create_table('contractor_profiles',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('company_name', sa.String(length=200), nullable=True),
        sa.Column('license_number', sa.String(length=100), nullable=True),
        sa.Column('specialty', sa.String(length=150), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    
    op.create_table('engineer_profiles',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('discipline', engineer_discipline, nullable=False),
        sa.Column('license_number', sa.String(length=100), nullable=True),
        sa.Column('years_of_experience', sa.Integer(), nullable=True),
        sa.Column('can_act_as_project_manager', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_engineer_profiles_discipline'), 'engineer_profiles', ['discipline'], unique=False)
    
    op.create_table('projects',
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('project_type', sa.String(length=100), nullable=True),
        sa.Column('status', project_status, server_default='PLANNING', nullable=False),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('planned_end_date', sa.Date(), nullable=True),
        sa.Column('actual_end_date', sa.Date(), nullable=True),
        sa.Column('budget_total', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('budget_spent', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('completion_percentage', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('project_manager_id', sa.UUID(), nullable=True),
        sa.Column('cover_image_url', sa.String(length=500), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_manager_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_projects_name'), 'projects', ['name'], unique=False)
    op.create_index(op.f('ix_projects_owner_id'), 'projects', ['owner_id'], unique=False)
    op.create_index(op.f('ix_projects_status'), 'projects', ['status'], unique=False)
    
    op.create_table('cost_validations',
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('requested_by_id', sa.UUID(), nullable=False),
        sa.Column('material_name', sa.String(length=200), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('unit', sa.String(length=30), nullable=True),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('requested_cost', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('market_price_min', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('market_price_max', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('risk_level', cost_risk_level, nullable=True),
        sa.Column('ai_suggestion', sa.Text(), nullable=True),
        sa.Column('status', cost_validation_status, server_default='PENDING', nullable=False),
        sa.Column('reviewed_by_id', sa.UUID(), nullable=True),
        sa.Column('review_notes', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requested_by_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cost_validations_project_id'), 'cost_validations', ['project_id'], unique=False)
    op.create_index(op.f('ix_cost_validations_status'), 'cost_validations', ['status'], unique=False)
    
    op.create_table('project_members',
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('role_on_project', user_role, nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'user_id', name='uq_project_member')
    )
    op.create_index(op.f('ix_project_members_project_id'), 'project_members', ['project_id'], unique=False)
    op.create_index(op.f('ix_project_members_user_id'), 'project_members', ['user_id'], unique=False)
    
    op.create_table('tasks',
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=250), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('discipline', sa.String(length=50), nullable=True),
        sa.Column('status', task_status, server_default='TODO', nullable=False),
        sa.Column('priority', task_priority, server_default='MEDIUM', nullable=False),
        sa.Column('assignee_id', sa.UUID(), nullable=True),
        sa.Column('created_by_id', sa.UUID(), nullable=False),
        sa.Column('planned_start_date', sa.Date(), nullable=True),
        sa.Column('planned_end_date', sa.Date(), nullable=True),
        sa.Column('actual_start_date', sa.Date(), nullable=True),
        sa.Column('actual_end_date', sa.Date(), nullable=True),
        sa.Column('duration_days', sa.Integer(), nullable=True),
        sa.Column('progress_percentage', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('is_critical_path', sa.Boolean(), nullable=False),
        sa.Column('is_milestone', sa.Boolean(), nullable=False),
        sa.Column('total_float_days', sa.Integer(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tasks_assignee_id'), 'tasks', ['assignee_id'], unique=False)
    op.create_index(op.f('ix_tasks_discipline'), 'tasks', ['discipline'], unique=False)
    op.create_index(op.f('ix_tasks_is_critical_path'), 'tasks', ['is_critical_path'], unique=False)
    op.create_index(op.f('ix_tasks_priority'), 'tasks', ['priority'], unique=False)
    op.create_index(op.f('ix_tasks_project_id'), 'tasks', ['project_id'], unique=False)
    op.create_index(op.f('ix_tasks_status'), 'tasks', ['status'], unique=False)
    
    op.create_table('design_changes',
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('task_id', sa.UUID(), nullable=True),
        sa.Column('title', sa.String(length=250), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('source_discipline', sa.String(length=50), nullable=False),
        sa.Column('proposed_by_id', sa.UUID(), nullable=False),
        sa.Column('approved_by_id', sa.UUID(), nullable=True),
        sa.Column('status', design_change_status, server_default='PROPOSED', nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['proposed_by_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_design_changes_project_id'), 'design_changes', ['project_id'], unique=False)
    op.create_index(op.f('ix_design_changes_status'), 'design_changes', ['status'], unique=False)
    
    op.create_table('documents',
        sa.Column('project_id', sa.UUID(), nullable=False), sa.Column('task_id', sa.UUID(), nullable=True),
        sa.Column('uploaded_by_id', sa.UUID(), nullable=False), sa.Column('title', sa.String(250), nullable=False),
        sa.Column('document_type', document_type, server_default='OTHER', nullable=False),
        sa.Column('file_url', sa.String(500), nullable=False), sa.Column('file_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('mime_type', sa.String(100), nullable=True), sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True), sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id'], ondelete='RESTRICT'), sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_documents_project_id','documents',['project_id'])
    op.create_index('ix_documents_document_type','documents',['document_type'])

    op.create_table('issues',
        sa.Column('project_id', sa.UUID(), nullable=False), sa.Column('task_id', sa.UUID(), nullable=True),
        sa.Column('title', sa.String(250), nullable=False), sa.Column('description', sa.Text(), nullable=True),
        sa.Column('severity', issue_severity, server_default='MEDIUM', nullable=False),
        sa.Column('status', issue_status, server_default='OPEN', nullable=False),
        sa.Column('raised_by_id', sa.UUID(), nullable=False), sa.Column('assigned_to_id', sa.UUID(), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True), sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['raised_by_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['assigned_to_id'], ['users.id'], ondelete='SET NULL'), sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_issues_project_id','issues',['project_id'])
    op.create_index('ix_issues_status','issues',['status'])

    op.create_table('task_dependencies',
        sa.Column('task_id', sa.UUID(), nullable=False), sa.Column('depends_on_task_id', sa.UUID(), nullable=False),
        sa.Column('dependency_type', dependency_type, server_default='FINISH_TO_START', nullable=False),
        sa.Column('lag_days', sa.Integer(), nullable=False), sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('task_id != depends_on_task_id', name='ck_task_dependency_not_self'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['depends_on_task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'), sa.UniqueConstraint('task_id','depends_on_task_id',name='uq_task_dependency_pair'))
    op.create_index('ix_task_dependencies_task_id','task_dependencies',['task_id'])
    op.create_index('ix_task_dependencies_depends_on_task_id','task_dependencies',['depends_on_task_id'])

    op.create_table('task_reschedule_logs',
        sa.Column('task_id', sa.UUID(), nullable=False), sa.Column('triggered_by_task_id', sa.UUID(), nullable=True),
        sa.Column('triggered_by_user_id', sa.UUID(), nullable=True), sa.Column('reason', reschedule_reason, server_default='MANUAL', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True), sa.Column('previous_start_date', sa.Date(), nullable=True),
        sa.Column('previous_end_date', sa.Date(), nullable=True), sa.Column('new_start_date', sa.Date(), nullable=True),
        sa.Column('new_end_date', sa.Date(), nullable=True), sa.Column('shift_days', sa.Integer(), nullable=False),
        sa.Column('is_automatic', sa.Boolean(), nullable=False), sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['triggered_by_task_id'], ['tasks.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['triggered_by_user_id'], ['users.id'], ondelete='SET NULL'), sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_task_reschedule_logs_task_id','task_reschedule_logs',['task_id'])

    op.create_table('voice_recordings',
        sa.Column('project_id', sa.UUID(), nullable=False), sa.Column('recorded_by_id', sa.UUID(), nullable=False),
        sa.Column('linked_task_id', sa.UUID(), nullable=True), sa.Column('audio_file_url', sa.String(500), nullable=False),
        sa.Column('duration_seconds', sa.Integer(), nullable=True), sa.Column('transcript_text', sa.Text(), nullable=True),
        sa.Column('transcript_language', sa.String(10), nullable=True), sa.Column('confidence_score', sa.Numeric(5,4), nullable=True),
        sa.Column('status', voice_processing_status, server_default='UPLOADED', nullable=False),
        sa.Column('processing_error', sa.Text(), nullable=True), sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['recorded_by_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['linked_task_id'], ['tasks.id'], ondelete='SET NULL'), sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_voice_recordings_project_id','voice_recordings',['project_id'])
    op.create_index('ix_voice_recordings_status','voice_recordings',['status'])

    op.create_table('design_change_affected_disciplines',
        sa.Column('design_change_id', sa.UUID(), nullable=False), sa.Column('discipline', sa.String(50), nullable=False),
        sa.Column('acknowledged_by_id', sa.UUID(), nullable=True), sa.Column('acknowledged', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['design_change_id'], ['design_changes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['acknowledged_by_id'], ['users.id'], ondelete='SET NULL'), sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_design_change_affected_disciplines_design_change_id','design_change_affected_disciplines',['design_change_id'])

    op.create_table('site_reports',
        sa.Column('project_id', sa.UUID(), nullable=False), sa.Column('task_id', sa.UUID(), nullable=True),
        sa.Column('submitted_by_id', sa.UUID(), nullable=False), sa.Column('report_date', sa.Date(), nullable=False),
        sa.Column('summary_text', sa.Text(), nullable=True), sa.Column('progress_percentage_reported', sa.Numeric(5,2), nullable=True),
        sa.Column('weather_conditions', sa.String(100), nullable=True), sa.Column('voice_recording_id', sa.UUID(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['submitted_by_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['voice_recording_id'], ['voice_recordings.id'], ondelete='SET NULL'), sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_site_reports_project_id','site_reports',['project_id'])
    op.create_index('ix_site_reports_task_id','site_reports',['task_id'])
    op.create_index('ix_site_reports_report_date','site_reports',['report_date'])

    op.create_table('media_assets',
        sa.Column('project_id', sa.UUID(), nullable=False), sa.Column('task_id', sa.UUID(), nullable=True),
        sa.Column('site_report_id', sa.UUID(), nullable=True), sa.Column('uploaded_by_id', sa.UUID(), nullable=False),
        sa.Column('media_type', media_type, server_default='IMAGE', nullable=False), sa.Column('file_url', sa.String(500), nullable=False),
        sa.Column('thumbnail_url', sa.String(500), nullable=True), sa.Column('caption', sa.String(500), nullable=True),
        sa.Column('project_stage', sa.String(100), nullable=True), sa.Column('file_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['site_report_id'], ['site_reports.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id'], ondelete='RESTRICT'), sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_media_assets_project_id','media_assets',['project_id'])
    op.create_index('ix_media_assets_task_id','media_assets',['task_id'])
    op.create_index('ix_media_assets_site_report_id','media_assets',['site_report_id'])

    op.create_table('notifications',
        sa.Column('user_id', sa.UUID(), nullable=False), sa.Column('title', sa.String(250), nullable=False),
        sa.Column('message', sa.Text(), nullable=False), sa.Column('type', notification_type, server_default='SYSTEM', nullable=False),
        sa.Column('status', notification_status, server_default='PENDING', nullable=False),
        sa.Column('is_read', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=True), sa.Column('task_id', sa.UUID(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='SET NULL'), sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_notifications_user_id','notifications',['user_id'])
    op.create_index('ix_notifications_status','notifications',['status'])


def downgrade() -> None:
    # Keep your existing downgrade function exactly as it was
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('ix_notifications_status', table_name='notifications')
    op.drop_index('ix_notifications_user_id', table_name='notifications')
    op.drop_table('notifications')
    op.drop_index(op.f('ix_media_assets_task_id'), table_name='media_assets')
    op.drop_index(op.f('ix_media_assets_site_report_id'), table_name='media_assets')
    op.drop_index(op.f('ix_media_assets_project_id'), table_name='media_assets')
    op.drop_table('media_assets')
    op.drop_index(op.f('ix_site_reports_task_id'), table_name='site_reports')
    op.drop_index(op.f('ix_site_reports_report_date'), table_name='site_reports')
    op.drop_index(op.f('ix_site_reports_project_id'), table_name='site_reports')
    op.drop_table('site_reports')
    op.drop_index(op.f('ix_design_change_affected_disciplines_design_change_id'), table_name='design_change_affected_disciplines')
    op.drop_table('design_change_affected_disciplines')
    op.drop_index(op.f('ix_voice_recordings_status'), table_name='voice_recordings')
    op.drop_index(op.f('ix_voice_recordings_project_id'), table_name='voice_recordings')
    op.drop_table('voice_recordings')
    op.drop_index(op.f('ix_task_reschedule_logs_task_id'), table_name='task_reschedule_logs')
    op.drop_table('task_reschedule_logs')
    op.drop_index(op.f('ix_task_dependencies_task_id'), table_name='task_dependencies')
    op.drop_index(op.f('ix_task_dependencies_depends_on_task_id'), table_name='task_dependencies')
    op.drop_table('task_dependencies')
    op.drop_index(op.f('ix_issues_status'), table_name='issues')
    op.drop_index(op.f('ix_issues_project_id'), table_name='issues')
    op.drop_table('issues')
    op.drop_index(op.f('ix_documents_project_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_document_type'), table_name='documents')
    op.drop_table('documents')
    op.drop_index(op.f('ix_design_changes_status'), table_name='design_changes')
    op.drop_index(op.f('ix_design_changes_project_id'), table_name='design_changes')
    op.drop_table('design_changes')
    op.drop_index(op.f('ix_tasks_status'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_project_id'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_priority'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_is_critical_path'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_discipline'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_assignee_id'), table_name='tasks')
    op.drop_table('tasks')
    op.drop_index(op.f('ix_project_members_user_id'), table_name='project_members')
    op.drop_index(op.f('ix_project_members_project_id'), table_name='project_members')
    op.drop_table('project_members')
    op.drop_index(op.f('ix_cost_validations_status'), table_name='cost_validations')
    op.drop_index(op.f('ix_cost_validations_project_id'), table_name='cost_validations')
    op.drop_table('cost_validations')
    op.drop_index(op.f('ix_projects_status'), table_name='projects')
    op.drop_index(op.f('ix_projects_owner_id'), table_name='projects')
    op.drop_index(op.f('ix_projects_name'), table_name='projects')
    op.drop_table('projects')
    op.drop_index(op.f('ix_engineer_profiles_discipline'), table_name='engineer_profiles')
    op.drop_table('engineer_profiles')
    op.drop_table('contractor_profiles')
    op.drop_index(op.f('ix_users_role'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
