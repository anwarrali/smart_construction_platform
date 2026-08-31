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
      /* The office's own name for the role, falling back to the retired label
         only for an account the backfill has not reached. */
      header: "Office role",
      render: (user) => (
        <Badge variant="info">{user.orgRole?.nameEn || getRoleLabel(user.role)}</Badge>
      ),
    },
    {
      key: "disciplines",
      header: "Disciplines",
      render: (user) => {
        const names = (user.disciplines || []).map((item) => item.nameEn);
        return (
          <span className="capitalize text-sm text-muted-foreground">
            {names.length
              ? names.join(", ")
              : user.engineerProfile?.discipline || user.specialization || "-"}
          </span>
        );
      },
    },
    {
      key: "isInternal",
      /* Replaces the "Affiliation" column, which read the retired
         `engineerAffiliation` string. What matters now is the one axis that
         governs authority: office staff, or somebody taking part from
         outside. */
      header: "Party",
      render: (user) => {
        const external = user.orgRole
          ? !user.orgRole.isInternalOnly
          : user.isInternal === false;
        return (
          <Badge variant={external ? "warning" : "neutral"}>
            {external ? "External" : "Office staff"}
          </Badge>
        );
      },
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
