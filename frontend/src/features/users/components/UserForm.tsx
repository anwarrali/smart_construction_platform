import { useEffect, useState } from "react";
import { Button } from "../../../components/ui/Button";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import { Modal, ModalActions } from "../../../components/ui/Modal";
import { ROLES_OPTIONS } from "../../../utils/roleMapper";
import type { UserProfile } from "../../../types/user";
import type { EngineerAffiliation, EngineerDiscipline, UserRole, UserStatus } from "../../../types/auth";
import { Eye, EyeOff } from "lucide-react";

interface UserFormProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: UserFormData) => Promise<void>;
  user?: UserProfile | null;
}

export type UserFormData = Partial<UserProfile> & { password?: string };

const SPECIALIZATION_OPTIONS = [
  { value: "civil", label: "Civil" },
  { value: "architectural", label: "Architectural" },
  { value: "electrical", label: "Electrical" },
  { value: "mechanical", label: "Mechanical" },
];

export const UserForm = ({
  isOpen,
  onClose,
  onSubmit,
  user,
}: UserFormProps) => {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [role, setRole] = useState<UserRole>("owner");
  const [status, setStatus] = useState<UserStatus>("active");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [organization, setOrganization] = useState("");
  const [specialization, setSpecialization] = useState<EngineerDiscipline | "">("");
  const [engineerAffiliation, setEngineerAffiliation] = useState<EngineerAffiliation>("internal_engineer");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const isEditing = !!user;
  const needsSpecialization = role === "engineer";

  useEffect(() => {
    if (!isOpen) return;
    setFullName(user?.fullName || "");
    setEmail(user?.email || "");
    setPassword("");
    setShowPassword(false);
    setRole(user?.role === "consultant" ? "engineer" : (user?.role || "owner"));
    setStatus((user?.status as UserStatus) || "pending");
    setPhoneNumber(user?.phoneNumber || "");
    setOrganization(user?.organization || "");
    setSpecialization(user?.engineerProfile?.discipline || "");
    setEngineerAffiliation(user?.engineerAffiliation || (user?.role === "consultant" ? "external_consultant" : "internal_engineer"));
    setError("");
  }, [isOpen, user]);

  const handleRoleChange = (nextRole: UserRole) => {
    setRole(nextRole);
    if (nextRole === "engineer") {
      setSpecialization((current) => current || "civil");
      setEngineerAffiliation("internal_engineer");
    } else {
      setSpecialization("");
    }
  };

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
    if (needsSpecialization && !specialization) {
      setError("Specialization is required for Engineer and Consultant users");
      return;
    }
    if (needsSpecialization && engineerAffiliation === "external_consultant" && !organization.trim()) {
      setError("External consultant company/organization is required");
      return;
    }

    setIsLoading(true);
    try {
      await onSubmit({
        fullName: fullName.trim(),
        email: email.trim(),
        password: isEditing ? undefined : password,
        role,
        status,
        phoneNumber: phoneNumber.trim() || undefined,
        organization: organization.trim() || undefined,
        engineerAffiliation: needsSpecialization ? engineerAffiliation : undefined,
        specialization: specialization || undefined,
      });
      onClose();
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || "Failed to save user.";
      setError(Array.isArray(msg) ? msg.map((item) => item.msg).join(", ") : msg);
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
            label="Full Name *"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
          />
          {!isEditing && <Input
            label="Password *"
            type={showPassword ? "text" : "password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            autoComplete="new-password"
            rightElement={<button type="button" onClick={() => setShowPassword((value) => !value)} className="text-muted-foreground transition-colors hover:text-foreground" aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button>}
            required
          />}
          <Input
            label="Email *"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <Input
            label="Phone Number"
            value={phoneNumber}
            onChange={(e) => setPhoneNumber(e.target.value)}
            placeholder="+970..."
          />
          <Input
            label="Organization"
            value={organization}
            onChange={(e) => setOrganization(e.target.value)}
            placeholder="Company / office"
          />
          <Select
            label="Role *"
            options={ROLES_OPTIONS.filter((r) => r.value !== "consultant").map((r) => ({
              value: r.value,
              label: r.label,
            }))}
            value={role}
            onChange={(e) => handleRoleChange(e.target.value as UserRole)}
          />
          {isEditing && <Select
            label="Status"
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
        {needsSpecialization && (
          <div className="grid gap-4 sm:grid-cols-2"><Select
            label="Engineer Affiliation *"
            value={engineerAffiliation}
            onChange={(e) => {
              const affiliation = e.target.value as EngineerAffiliation;
              setEngineerAffiliation(affiliation);
              setRole("engineer");
            }}
            options={[
              { value: "internal_engineer", label: "Internal Engineer" },
              { value: "external_consultant", label: "External consultant engineer" },
              { value: "main_contractor", label: "Main Contractor Engineer" },
            ]}
            required
          /><Select
            label="Specialization *"
            value={specialization}
            onChange={(e) => setSpecialization(e.target.value as EngineerDiscipline)}
            options={SPECIALIZATION_OPTIONS}
            required
          /></div>
        )}
        {engineerAffiliation === "external_consultant" && needsSpecialization && <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">External consultants receive access only after an administrator assigns them to a specific project. Enter their external company in Organization.</p>}
        {!isEditing && <p className="text-xs text-muted-foreground">The account is activated immediately. Store and share the password securely.</p>}
        <ModalActions>
          <Button variant="outline" onClick={onClose} type="button">
            Cancel
          </Button>
          <Button type="submit" isLoading={isLoading}>
            {isEditing ? "Save Changes" : "Create User"}
          </Button>
        </ModalActions>
      </form>
    </Modal>
  );
};
