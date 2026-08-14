import { Table } from "../../../components/ui/Table";
import { useTranslation } from "react-i18next";
import type { Column } from "../../../components/ui/Table/Table";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { getRoleLabel } from "../../../utils/roleMapper";
import { formatDate } from "../../../utils/date";
import { getInitials, getAvatarColor } from "../../../utils/helpers";
import type { UserProfile } from "../../../types/user";

interface UserTableProps {
  users: UserProfile[];
  isLoading: boolean;
  onEdit?: (user: UserProfile) => void;
  onToggleStatus?: (user: UserProfile) => void;
  onResetPassword?: (user: UserProfile) => void;
  onDelete?: (user: UserProfile) => void;
  currentUserId?: string;
}

const statusVariant = (status?: string) => {
  if (status === "active") return "success";
  if (status === "pending") return "warning";
  return "danger";
};

export const UserTable = ({
  users,
  isLoading,
  onEdit,
  onToggleStatus,
  onResetPassword,
  onDelete,
  currentUserId,
}: UserTableProps) => {
  const { t } = useTranslation();
  const columns: Column<UserProfile>[] = [
    {
      key: "fullName",
      header: "User",
      render: (user) => (
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-medium"
            style={{ backgroundColor: getAvatarColor(user.fullName) }}
          >
            {getInitials(user.fullName)}
          </div>
          <div>
            <p className="font-medium">{user.fullName}</p>
            <p className="text-xs text-muted-foreground">{user.email}</p>
          </div>
        </div>
      ),
    },
    {
      key: "role",
      header: "Role",
      render: (user) => <Badge variant="info">{getRoleLabel(user.role)}</Badge>,
    },
    {
      key: "specialization",
      header: "Specialization",
      render: (user) => (
        <span className="capitalize text-sm text-muted-foreground">
          {["engineer", "consultant"].includes(user.role)
            ? user.engineerProfile?.discipline || user.specialization || "-"
            : "-"}
        </span>
      ),
    },
    {
      key: "engineerAffiliation",
      header: "Affiliation",
      render: (user) => ["engineer", "consultant"].includes(user.role)
        ? <Badge variant={user.engineerAffiliation === "external_consultant" ? "warning" : "neutral"}>{user.engineerAffiliation === "external_consultant" ? "External Consultant" : user.engineerAffiliation === "main_contractor" ? "Main Contractor" : "Internal Engineer"}</Badge>
        : <span className="text-muted-foreground">-</span>,
    },
    {
      key: "status",
      header: "Status",
      render: (user) => (
        <Badge variant={statusVariant(user.status) as "success" | "warning" | "danger"}>
          {user.status || "unknown"}
        </Badge>
      ),
    },
    {
      key: "phoneNumber",
      header: "Phone",
      render: (user) => <span className="text-sm text-muted-foreground">{user.phoneNumber || "-"}</span>,
    },
    {
      key: "createdAt",
      header: "Created",
      render: (user) => (
        <span className="text-sm text-muted-foreground">
          {user.createdAt ? formatDate(user.createdAt) : "-"}
        </span>
      ),
    },
    {
      key: "actions",
      header: "",
      render: (user) => (
        <div className="flex items-center gap-2 justify-end">
          {onEdit && (
            <Button variant="ghost" size="sm" onClick={() => onEdit(user)}>
              {t("userTable.edit")}
            </Button>
          )}
          {onToggleStatus && (
            <Button
              variant={user.status === "active" ? "destructive" : "outline"}
              size="sm"
              onClick={() => onToggleStatus(user)}
            >
              {user.status === "active" ? "Deactivate" : "Activate"}
            </Button>
          )}
          {onResetPassword && (
            <Button variant="outline" size="sm" onClick={() => onResetPassword(user)}>
              {t("userTable.reset_password")}
            </Button>
          )}
          {onDelete && user.id !== currentUserId && (
            <Button variant="destructive" size="sm" onClick={() => onDelete(user)}>
              {t("userTable.delete")}
            </Button>
          )}
        </div>
      ),
      className: "text-right",
    },
  ];

  return (
    <Table
      columns={columns}
      data={users}
      keyExtractor={(user) => user.id}
      isLoading={isLoading}
      emptyMessage={t("userTable.no_users_found")}
    />
  );
};
