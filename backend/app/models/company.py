"""The organization. For this product that means a consulting office.

The table is still called `companies` and the class is still `Company`: the
name predates the product direction, and renaming a table that `users`,
`projects`, `roles` and `disciplines` all reference would be a large, risky
change that buys nothing an added column does not. Read it as *Organization*
— `ORGANIZATION_KINDS` below is what actually distinguishes the office from
the historical contractor and client rows.

## This is not a hierarchy

`kind` records what an organization is, not who it answers to. A contractor
row here is a leftover directory record from the pre-redesign model, kept so
existing users stay attributable; it is **not** how a contractor takes part in
a project. That is `ProjectParty`, which is scoped to a single project — see
`app.models.rbac`. Nothing joins one organization to another.

Exactly one row is expected to carry `is_tenant`: the consulting office the
deployment belongs to. It owns the projects, the configurable roles and the
discipline list.
"""


from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

#: What an organization row represents. CONSULTING_OFFICE is the product's
#: primary organization; the rest exist to preserve the meaning of rows created
#: before the redesign.
ORGANIZATION_KINDS = ("CONSULTING_OFFICE", "CONTRACTOR", "CLIENT", "OTHER")


class Company(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    #: One of ORGANIZATION_KINDS. Defaults to OTHER so a row created before the
    #: redesign is never silently promoted to being the office.
    kind: Mapped[str] = mapped_column(
        String(30), nullable=False, default="OTHER", server_default="OTHER", index=True,
    )
    #: The consulting office this deployment belongs to. At most one row.
    is_tenant: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True,
    )
    #: Logo, letterhead and report-template settings. Read by nothing yet;
    #: the branded site-report export is deliberately a later piece of work.
    branding_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
    )

    users: Mapped[list["User"]] = relationship(back_populates="company")
    projects: Mapped[list["Project"]] = relationship(back_populates="company")

    def __repr__(self) -> str:
        return f"<Company id={self.id} name={self.name} kind={self.kind}>"
