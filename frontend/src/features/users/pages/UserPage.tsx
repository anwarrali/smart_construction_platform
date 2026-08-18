import { useState, useEffect, useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import { UserTable } from "../components/UserTable";
import { UserForm, type UserFormData } from "../components/UserForm";
import { usersService } from "../services/users.service";
import { useDebounce } from "../../../hooks/useDebounce";
import type { UserProfile } from "../../../types/user";
import type { EngineerDiscipline, UserRole, UserStatus } from "../../../types/auth";
import toast from "react-hot-toast";
import { useAuth } from "../../../hooks/useAuth";
import { useStepUp } from "../../../hooks/useStepUp";

const ROLE_FILTER_OPTIONS = [
  { value: "", label: "All Roles" },
  { value: "admin", label: "Administrator" },
  { value: "owner", label: "Owner" },
  { value: "project_manager", label: "Project Manager" },
  { value: "engineer", label: "Engineer" },
  { value: "consultant", label: "Consultant" },
];

const SPECIALIZATION_FILTER_OPTIONS = [
  { value: "", label: "All Specializations" },
  { value: "civil", label: "Civil" },
  { value: "architectural", label: "Architectural" },
  { value: "electrical", label: "Electrical" },
  { value: "mechanical", label: "Mechanical" },
];

const normalizeUsers = (response: unknown): UserProfile[] => {
  if (Array.isArray(response)) return response as UserProfile[];
  const data = response as { data?: UserProfile[]; items?: UserProfile[] };
  return data.data || data.items || [];
};

export const UsersPage = () => {
  // Sensitive operations may answer with a step-up challenge; `run` shows the
  // shared verification dialog and replays the call once it is satisfied.
  const { run, dialog } = useStepUp();
  const { t } = useTranslation();
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [specializationFilter, setSpecializationFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<UserProfile | null>(null);
  const debouncedSearch = useDebounce(search);

  const fetchUsers = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await usersService.list();
      setUsers(normalizeUsers(response));
    } catch (err: any) {
      toast.error(errorMessage(err, "Failed to load users."));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const filteredUsers = useMemo(() => {
    const q = debouncedSearch.trim().toLowerCase();
    return users.filter((user) => {
      const specialization = user.engineerProfile?.discipline || user.specialization || "";
      const matchesSearch = !q || [user.fullName, user.email, user.phoneNumber, user.organization]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(q));
      const matchesRole = !roleFilter || user.role === roleFilter;
      const matchesSpecialization = !specializationFilter || specialization === specializationFilter;
      const matchesStatus = !statusFilter || user.status === statusFilter;
      return matchesSearch && matchesRole && matchesSpecialization && matchesStatus;
    });
  }, [debouncedSearch, roleFilter, specializationFilter, statusFilter, users]);

  const handleEdit = (user: UserProfile) => {
    setEditingUser(user);
    setIsFormOpen(true);
  };

  const handleToggleStatus = async (user: UserProfile) => {
    try {
      if (user.status === "active") {
        await run(() => usersService.deactivate(user.id));
        toast.success("User deactivated.");
      } else {
        await usersService.activate(user.id);
        toast.success("User activated.");
      }
      fetchUsers();
    } catch (err: any) {
      toast.error(errorMessage(err, "Failed to update user status."));
    }
  };

  const handleResetPassword = async (user: UserProfile) => {
    if (!window.confirm(`Reset the password for ${user.fullName}? Their current password will stop working immediately.`)) return;
    try {
      const response = await run(() => usersService.resetPassword(user.id));
      toast.success(`Temporary password for ${user.fullName}: ${response.temporaryPassword}`, { duration: 20000 });
      fetchUsers();
    } catch (err: any) {
      toast.error(errorMessage(err, "Failed to reset password."));
    }
  };

  const handleDelete = async (user: UserProfile) => {
    if (!window.confirm(`Permanently delete ${user.fullName}? This cannot be undone.`)) return;
    try {
      await usersService.delete(user.id);
      toast.success("User permanently deleted.");
      fetchUsers();
    } catch (err: any) {
      toast.error(errorMessage(err, "User could not be permanently deleted."));
    }
  };

  const handleSubmit = async (data: UserFormData) => {
    const role = data.role as UserRole;
    const status = data.status as UserStatus;
    const specialization = data.specialization as EngineerDiscipline | undefined;
    const payload = {
      fullName: data.fullName || "",
      email: data.email || "",
      password: data.password || "",
      role,
      status,
      phoneNumber: data.phoneNumber || undefined,
      organization: data.organization || undefined,
      engineerAffiliation: data.engineerAffiliation,
      engineerProfile: ["engineer", "consultant"].includes(role)
        ? { discipline: specialization || "civil" }
        : undefined,
    };

    if (editingUser) {
      await usersService.update(editingUser.id, payload);
      toast.success("User updated successfully.");
    } else {
      await usersService.create(payload);
      toast.success("Active user account created successfully.");
    }
    setIsFormOpen(false);
    setEditingUser(null);
    fetchUsers();
  };

  return (
    <div className="page-container space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t("userPage.users")}</h1>
          <p className="text-muted-foreground">{t("userPage.manage_company_accounts_roles")}</p>
        </div>
        <Button
          onClick={() => {
            setEditingUser(null);
            setIsFormOpen(true);
          }}
        >
          + Add User
        </Button>
      </div>

      <Card>
        <div className="grid gap-3 mb-4 md:grid-cols-4">
          <Input
            placeholder={t("userPage.search_name_email_phone")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Select
            options={ROLE_FILTER_OPTIONS}
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
          />
          <Select
            options={SPECIALIZATION_FILTER_OPTIONS}
            value={specializationFilter}
            onChange={(e) => setSpecializationFilter(e.target.value)}
          />
          <Select
            options={[
              { value: "", label: "All Statuses" },
              { value: "active", label: "Active" },
              { value: "pending", label: "Pending" },
              { value: "inactive", label: "Inactive" },
              { value: "suspended", label: "Suspended" },
            ]}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          />
        </div>

        <UserTable
          users={filteredUsers}
          isLoading={isLoading}
          onEdit={handleEdit}
          onToggleStatus={handleToggleStatus}
          onResetPassword={handleResetPassword}
          onDelete={handleDelete}
          currentUserId={currentUser?.id}
        />
      </Card>

      <UserForm
        isOpen={isFormOpen}
        onClose={() => {
          setIsFormOpen(false);
          setEditingUser(null);
        }}
        onSubmit={handleSubmit}
        user={editingUser}
      />
      {dialog}
    </div>
  );
};
