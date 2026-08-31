import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import { Button } from "../../../components/ui/Button";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import { Modal, ModalActions } from "../../../components/ui/Modal";
import organizationService, {
  type Discipline,
  type Role,
} from "../../admin/services/organization.service";
import type { UserProfile } from "../../../types/user";
import type { UserStatus } from "../../../types/auth";
import { Eye, EyeOff } from "lucide-react";

interface UserFormProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: UserFormData) => Promise<void>;
  user?: UserProfile | null;
}

export type UserFormData = Partial<UserProfile> & {
  password?: string;
  orgRoleId?: string;
  disciplineIds?: string[];
};

/**
 * Create an account under one of the office's own roles.
 *
 * The retired version of this form asked for one of six fixed roles and, for
 * engineers, an "affiliation" that decided whether they were internal, a
 * contractor's engineer or an external consultant. Both are gone. What an
 * office actually has is a list of roles it maintains — General Manager,
 * Senior Structural Engineer, Site Engineer, Surveyor, whatever it decided —
 * and this form reads that list.
 *
 * Two things follow from the role and are therefore not asked for separately:
 *
 *  * **Internal or external.** A role the office marks internal-only produces
 *    office staff; the external roles (client, contractor, subcontractor
 *    representatives) produce project participants. The form says which, so
 *    the administrator can see what they are about to create, but it is not a
 *    field — the server derives it from the role and would refuse a
 *    contradiction anyway.
 *  * **What the account may do.** That is the role's permissions, configured
 *    on the Office Roles screen, not here.
 *
 * Disciplines are separate and multi-select on purpose. An office that
 * combines Mechanical and Electrical picks both for the same person; an office
 * that models them as one MEP discipline picks that. Neither arrangement needs
 * a code change, and neither grants anything — a discipline narrows what a
 * permission applies to.
 */
export const UserForm = ({
  isOpen,
  onClose,
  onSubmit,
  user,
}: UserFormProps) => {
  const { t } = useTranslation();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [orgRoleId, setOrgRoleId] = useState("");
  const [disciplineIds, setDisciplineIds] = useState<string[]>([]);
  const [status, setStatus] = useState<UserStatus>("active");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [organization, setOrganization] = useState("");
  const [roles, setRoles] = useState<Role[]>([]);
  const [disciplines, setDisciplines] = useState<Discipline[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const isEditing = !!user;

  useEffect(() => {
    if (!isOpen) return;
    Promise.all([organizationService.roles(), organizationService.disciplines()])
      .then(([roleRows, disciplineRows]) => {
        /* `archived_field_staff` is filtered out here as well as refused by the
           server. It is where retired worker accounts were parked; offering it
           would invite an administrator to create an account that can do
           nothing and then wonder why. */
        setRoles(roleRows.filter((role) => role.isActive && role.code !== "archived_field_staff"));
        setDisciplines(disciplineRows.filter((item) => item.isActive));
      })
      .catch(() => setError("Unable to load the office's roles and disciplines."));
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    setFullName(user?.fullName || "");
    setEmail(user?.email || "");
    setPassword("");
    setShowPassword(false);
    setOrgRoleId(user?.orgRole?.id || "");
    setDisciplineIds((user?.disciplines || []).map((item) => item.id));
    setStatus((user?.status as UserStatus) || "active");
    setPhoneNumber(user?.phoneNumber || "");
    setOrganization(user?.organization || "");
    setError("");
  }, [isOpen, user]);

  const selectedRole = useMemo(
    () => roles.find((role) => role.id === orgRoleId),
    [roles, orgRoleId],
  );
  const isExternalRole = selectedRole ? !selectedRole.isInternalOnly : false;

  const toggleDiscipline = (id: string) =>
    setDisciplineIds((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!fullName.trim() || !email.trim()) {
      setError("Full name and email are required");
      return;
    }
    if (!isEditing && password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    if (!orgRoleId) {
      setError("Choose the office role this account is created under");
      return;
    }
    /* The one field the role makes conditional. Somebody taking part for an
       outside organization has to be attributable to it — which organization
       is the whole basis of their access. */
    if (isExternalRole && !organization.trim()) {
      setError("Record the external organization this person belongs to");
      return;
    }

    setIsLoading(true);
    try {
      await onSubmit({
        fullName: fullName.trim(),
        email: email.trim(),
        password: isEditing ? undefined : password,
        orgRoleId,
        disciplineIds,
        status,
        phoneNumber: phoneNumber.trim() || undefined,
        organization: organization.trim() || undefined,
      });
      onClose();
    } catch (err: any) {
      setError(errorMessage(err, "Failed to save user."));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? "Edit User" : "Create User"}
      size="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="bg-red-50 text-red-600 text-sm rounded-md px-4 py-3">
            {error}
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label={t("userForm.full_name")}
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
          />
          {!isEditing && <Input
            label={t("userForm.password")}
            type={showPassword ? "text" : "password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            autoComplete="new-password"
            rightElement={<button type="button" onClick={() => setShowPassword((value) => !value)} className="text-muted-foreground transition-colors hover:text-foreground" aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button>}
            required
          />}
          <Input
            label={t("userForm.email")}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <Input
            label={t("userForm.phone_number")}
            value={phoneNumber}
            onChange={(e) => setPhoneNumber(e.target.value)}
            placeholder="+970..."
          />
          <Input
            label={isExternalRole ? t("userForm.external_organization") : t("userForm.organization")}
            value={organization}
            onChange={(e) => setOrganization(e.target.value)}
            placeholder={t("userForm.company_office")}
            required={isExternalRole}
          />
          <Select
            label={t("userForm.office_role")}
            options={[
              { value: "", label: t("userForm.select_office_role") },
              ...roles.map((role) => ({ value: role.id, label: role.nameEn })),
            ]}
            value={orgRoleId}
            onChange={(e) => setOrgRoleId(e.target.value)}
            required
          />
          {isEditing && <Select
            label={t("userForm.status")}
            options={[
              { value: "active", label: "Active" },
              { value: "pending", label: "Pending" },
              { value: "inactive", label: "Inactive" },
              { value: "suspended", label: "Suspended" },
            ]}
            value={status}
            onChange={(e) => setStatus(e.target.value as UserStatus)}
          />}
        </div>
        {selectedRole && (
          <p className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
            {selectedRole.description || selectedRole.nameEn}
            {" · "}
            {isExternalRole
              ? t("userForm.external_role_note")
              : t("userForm.internal_role_note")}
          </p>
        )}
        <fieldset className="rounded border p-3">
          <legend className="px-1 text-sm font-medium">{t("userForm.disciplines")}</legend>
          <p className="mb-2 text-xs text-muted-foreground">{t("userForm.disciplines_help")}</p>
          <div className="flex flex-wrap gap-2">
            {disciplines.map((item) => (
              <label key={item.id} className="flex items-center gap-1.5 rounded border px-2 py-1 text-sm">
                <input
                  type="checkbox"
                  checked={disciplineIds.includes(item.id)}
                  onChange={() => toggleDiscipline(item.id)}
                />
                {item.nameEn}
              </label>
            ))}
            {!disciplines.length && (
              <span className="text-xs text-muted-foreground">{t("userForm.no_disciplines_configured")}</span>
            )}
          </div>
        </fieldset>
        {!isEditing && <p className="text-xs text-muted-foreground">{t("userForm.the_account_is_activated_immediately")}</p>}
        <ModalActions>
          <Button variant="outline" onClick={onClose} type="button">
            {t("userForm.cancel")}
          </Button>
          <Button type="submit" isLoading={isLoading}>
            {isEditing ? "Save Changes" : "Create User"}
          </Button>
        </ModalActions>
      </form>
    </Modal>
  );
};
