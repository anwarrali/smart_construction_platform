"""Configurable roles, disciplines and external project parties.

Three ideas the platform used to conflate, separated here because a consulting
office needs them to vary independently:

  * **Role** — an organizational position that carries permissions. Configurable:
    an office creates "Resident Engineer" and decides what it may do, without a
    code change or a migration.
  * **Discipline** — a professional specialization. Carries no authority at all.
    It narrows *what a permission applies to* — which documents, which review
    queue, which findings — and is many-to-many, because one engineer may cover
    Mechanical and Electrical and an office may model that as either two
    disciplines or one MEP discipline.
  * **Party** — an external organization taking part in *one project*: the
    client, the main contractor, a subcontractor. Recorded on the project,
    never in the office's staff directory.

## Why a party is project-scoped and not a company row

A contractor works with many consulting offices, and an office works with many
contractors. Modelling that as a permanent company-to-company relationship
would invent a hierarchy that does not exist in the world and would make one
office's directory visible to another's. The project is the boundary where
these parties actually meet, so the party record lives there. `ProjectParty`
deliberately holds no foreign key to `companies`.

## What this module does not decide

Nothing here grants anything. `app.services.rbac` resolves what a person may
do, and `app.services.authorization` remains the one place that answers it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Role(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A named bundle of permissions an office can configure.

    `organization_id` NULL means a platform-wide template shared by every
    office. A row with an organization is that office's own, and only that
    office may edit it.
    """

    __tablename__ = "roles"
    __table_args__ = (
        # Partial unique indexes rather than one constraint, because NULL
        # organization_id must still be unique per code — the same pattern
        # `photo_categories` already uses for system vs project rows.
        Index("uq_roles_global_code", "code", unique=True,
              postgresql_where=text("organization_id IS NULL")),
        Index("uq_roles_org_code", "organization_id", "code", unique=True,
              postgresql_where=text("organization_id IS NOT NULL")),
        CheckConstraint("scope IN ('ORG','PROJECT','BOTH')", name="ck_roles_scope"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    name_en: Mapped[str] = mapped_column(String(120), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ORG, PROJECT or BOTH — where the role may be assigned.
    scope: Mapped[str] = mapped_column(String(10), nullable=False, server_default="BOTH")
    #: True for roles that only office staff may hold. Assigning one to a
    #: member who belongs to an external party is refused.
    is_internal_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", index=True,
    )
    #: Seeded by the platform. Still renameable and re-permissionable; the flag
    #: only records where the row came from.
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
    )
    #: The office administrator role. Deleting it would leave nobody able to
    #: administer, so the endpoint refuses.
    undeletable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
    )
    #: Display order only. Carries no authorization meaning.
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default="100")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true",
    )
    #: Which legacy `UserRole` an account created under this role is written
    #: with, and which `engineer_affiliation` goes with it. **Migration-window
    #: only.** `users.role` is still NOT NULL, so provisioning has to put
    #: something there; recording it on the role keeps that decision explicit
    #: instead of deriving it from whatever permissions an office configured.
    #: Both columns are dropped by the same migration that drops `users.role`.
    #: NULL means "no account may be created under this role" — which is the
    #: archived field-staff template, and nothing else.
    legacy_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    legacy_affiliation: Mapped[str | None] = mapped_column(String(40), nullable=True)

    permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Role id={self.id} code={self.code}>"


class RolePermission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One permission held by one role.

    `allowed` exists rather than presence-means-granted so an administrator can
    record a deliberate denial, which reads differently from an omission in the
    access-control UI and survives a later re-seed of the template.
    """

    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_code", name="uq_role_permission"),
        Index("ix_role_permission_lookup", "role_id", "allowed"),
    )

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    permission_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true",
    )

    role: Mapped["Role"] = relationship(back_populates="permissions")


class Discipline(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A professional specialization. Grants nothing on its own."""

    __tablename__ = "disciplines"
    __table_args__ = (
        Index("uq_disciplines_global_code", "code", unique=True,
              postgresql_where=text("organization_id IS NULL")),
        Index("uq_disciplines_org_code", "organization_id", "code", unique=True,
              postgresql_where=text("organization_id IS NOT NULL")),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    name_en: Mapped[str] = mapped_column(String(120), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: IFC classification names this discipline covers, so a person scoped to
    #: `mep` matches a coordination finding tagged `PLUMBING`. The two
    #: vocabularies were previously unrelated; this is the join between them.
    ifc_disciplines: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]",
    )
    #: The `EngineerDiscipline` value this replaces, where one existed. Used by
    #: the backfill and by compatibility reads; NULL for disciplines the enum
    #: never had.
    legacy_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default="100")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true",
    )

    def __repr__(self) -> str:
        return f"<Discipline id={self.id} code={self.code}>"


class UserDiscipline(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A discipline a person practises. Many-to-many on purpose.

    `EngineerProfile.discipline` allowed exactly one, which cannot express an
    engineer who covers Mechanical *and* Electrical — a structure the brief
    names explicitly.
    """

    __tablename__ = "user_disciplines"
    __table_args__ = (
        UniqueConstraint("user_id", "discipline_id", name="uq_user_discipline"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    discipline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("disciplines.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    #: The one shown when a single discipline has to be named. Not an authority.
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
    )

    discipline: Mapped["Discipline"] = relationship()


class OrganizationMembership(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """"I work for this office", and the role I hold there.

    Separate from `ProjectMember` because office membership and project
    participation answer different questions: the first says what someone may
    do across the office, the second what they may do on one job.
    """

    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_organization_membership"),
        Index("ix_org_membership_lookup", "user_id", "is_active"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    #: RESTRICT, not CASCADE: deleting a role that people still hold must fail
    #: loudly rather than silently stripping their authority.
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=True, index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true",
    )
    #: The person's home office, when they appear in more than one directory.
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true",
    )
    job_title: Mapped[str | None] = mapped_column(String(120), nullable=True)

    role: Mapped["Role | None"] = relationship()


class ProjectParty(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An external organization taking part in one project.

    Holds no link to `companies` by design — see the module docstring. A party
    is a fact about a project, not a standing relationship between firms.

    `parent_party_id` is the whole of the contractor/subcontractor distinction:
    a subcontractor is a party that points at the contractor it works under.
    That is why there is one table here and not separate Contractor and
    Subcontractor entities, and it is what lets a project have several main
    contractors without the model objecting.
    """

    __tablename__ = "project_parties"
    __table_args__ = (
        UniqueConstraint("project_id", "display_name", "kind", name="uq_project_party_name"),
        Index("ix_project_party_project_kind", "project_id", "kind"),
        CheckConstraint(
            "kind IN ('CLIENT','MAIN_CONTRACTOR','SUBCONTRACTOR','CONSULTANT',"
            "'SUPPLIER','AUTHORITY','OTHER')",
            name="ck_project_party_kind",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: A subcontractor's main contractor. NULL for a party that answers to the
    #: project directly.
    parent_party_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_parties.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    #: Marks the one main contractor on a project that has a single one. Does
    #: not forbid others — several parties of the same kind are legitimate.
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
    )
    contact_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true",
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    parent_party: Mapped["ProjectParty | None"] = relationship(remote_side="ProjectParty.id")

    def __repr__(self) -> str:
        return f"<ProjectParty id={self.id} kind={self.kind} name={self.display_name}>"


class ProjectMemberDiscipline(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """The disciplines a person covers *on one project*.

    Distinct from `UserDiscipline` because an engineer who practises three
    disciplines may be brought onto a project for one of them, and the review
    queues and document scoping should follow the project assignment rather
    than the whole CV.
    """

    __tablename__ = "project_member_disciplines"
    __table_args__ = (
        UniqueConstraint(
            "project_member_id", "discipline_id", name="uq_project_member_discipline",
        ),
    )

    project_member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_members.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    discipline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("disciplines.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    discipline: Mapped["Discipline"] = relationship()


class DocumentPartyShare(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An explicit decision to let one external party read one document.

    External document access is deny-by-default: a contractor added to a
    project sees nothing until a row exists here. That is the whole mechanism —
    there is no "external members see project-level documents" fallback,
    because that fallback is exactly the leak the redesign exists to prevent.
    """

    __tablename__ = "document_party_shares"
    __table_args__ = (
        UniqueConstraint("document_id", "party_id", name="uq_document_party_share"),
        Index("ix_document_party_share_party", "party_id", "document_id"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_parties.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    shared_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
