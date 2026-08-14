import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import toast from "react-hot-toast";
import { Camera, KeyRound, Mail, Save, Shield, UserRound } from "lucide-react";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import { Badge } from "../../../components/ui/Badge";
import { Loader } from "../../../components/ui/Loader";
import { usersService } from "../services/users.service";
import { getRoleLabel } from "../../../utils/roleMapper";
import { formatDate } from "../../../utils/date";
import { getInitials, getAvatarColor } from "../../../utils/helpers";
import { useAuth } from "../../../hooks/useAuth";
import type { EngineerDiscipline } from "../../../types/auth";
import type { UserProfile } from "../../../types/user";

const SPECIALIZATION_OPTIONS = [
  { value: "civil", label: "Civil" },
  { value: "architectural", label: "Architectural" },
  { value: "electrical", label: "Electrical" },
  { value: "mechanical", label: "Mechanical" },
];

export const ProfilePage = () => {
  const { t } = useTranslation();
  const { refreshUser, logout } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [isSavingPassword, setIsSavingPassword] = useState(false);
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false);

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [notifyByEmail, setNotifyByEmail] = useState(true);
  const [specialization, setSpecialization] = useState<EngineerDiscipline | "">("");
  const [licenseNumber, setLicenseNumber] = useState("");
  const [yearsOfExperience, setYearsOfExperience] = useState("");

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const canEditSpecialization = profile?.role === "engineer" || profile?.role === "consultant";

  const loadProfile = async () => {
    setIsLoading(true);
    try {
      const data = await usersService.getProfile();
      setProfile(data);
      setFullName(data.fullName || "");
      setEmail(data.email || "");
      setPhoneNumber(data.phoneNumber || "");
      setNotifyByEmail(data.notifyByEmail ?? true);
      setSpecialization(data.engineerProfile?.discipline || "");
      setLicenseNumber(data.engineerProfile?.licenseNumber || "");
      setYearsOfExperience(data.engineerProfile?.yearsOfExperience?.toString() || "");
    } catch (err: any) {
      toast.error(errorMessage(err, "Failed to load profile."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadProfile();
  }, []);

  const accountStatus = useMemo(() => {
    if (!profile) return [];
    return [
      { label: "Status", value: profile.status || "unknown" },
      { label: "Email Verified", value: profile.isEmailVerified ? "Yes" : "No" },
      { label: "Invitation", value: profile.invitationAccepted ? "Accepted" : "Pending" },
      { label: "Joined", value: profile.createdAt ? formatDate(profile.createdAt) : "-" },
    ];
  }, [profile]);

  const handleSaveProfile = async () => {
    if (!fullName.trim() || !email.trim()) {
      toast.error("Full name and email are required.");
      return;
    }
    if (canEditSpecialization && !specialization) {
      toast.error("Specialization is required for your role.");
      return;
    }

    setIsSavingProfile(true);
    try {
      const updated = await usersService.updateProfile({
        fullName: fullName.trim(),
        email: email.trim(),
        phoneNumber: phoneNumber.trim() || undefined,
        notifyByEmail,
        engineerProfile: canEditSpecialization
          ? {
              discipline: specialization as EngineerDiscipline,
              licenseNumber: licenseNumber.trim() || undefined,
              yearsOfExperience: yearsOfExperience ? Number(yearsOfExperience) : undefined,
              canActAsProjectManager: profile?.engineerProfile?.canActAsProjectManager || false,
            }
          : undefined,
      });
      setProfile(updated);
      await refreshUser();
      toast.success("Profile updated successfully.");
    } catch (err: any) {
      toast.error(errorMessage(err, "Failed to update profile."));
    } finally {
      setIsSavingProfile(false);
    }
  };

  const handleChangePassword = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!currentPassword || !newPassword) {
      toast.error("Current and new password are required.");
      return;
    }
    if (newPassword.length < 8) {
      toast.error("New password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("New passwords do not match.");
      return;
    }

    setIsSavingPassword(true);
    try {
      await usersService.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      await refreshUser();
      toast.success("Password updated successfully.");
    } catch (err: any) {
      toast.error(errorMessage(err, "Failed to change password."));
    } finally {
      setIsSavingPassword(false);
    }
  };

  const handleAvatarUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setIsUploadingAvatar(true);
    try {
      const result = await usersService.uploadAvatar(file);
      const updated = await usersService.updateProfile({ avatarUrl: result.avatarUrl });
      setProfile(updated);
      await refreshUser();
      toast.success("Profile photo updated.");
    } catch (err: any) {
      toast.error(errorMessage(err, "Failed to upload avatar."));
    } finally {
      setIsUploadingAvatar(false);
      event.target.value = "";
    }
  };

  if (isLoading) return <Loader fullPage />;

  if (!profile) {
    return (
      <div className="page-container">
        <Card>
          <div className="empty-state">
            <p className="empty-state-title">{t("profilePage.profile_not_found")}</p>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="page-container space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{t("profilePage.profile_settings")}</h1>
          <p className="text-muted-foreground">{t("profilePage.manage_your_account_contact_details")}</p>
        </div>
        <Button variant="outline" onClick={logout}>{t("profilePage.sign_out")}</Button>
      </div>

      {profile.mustChangePassword && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
          {t("profilePage.you_are_using_a_temporary_password")}
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
        <div className="space-y-6">
          <Card>
            <div className="flex flex-col items-center text-center">
              <div
                className="w-24 h-24 rounded-full flex items-center justify-center text-white text-2xl font-bold overflow-hidden"
                style={{ backgroundColor: getAvatarColor(profile.fullName) }}
              >
                {profile.avatarUrl ? (
                  <img src={profile.avatarUrl} alt={profile.fullName} className="h-full w-full object-cover" />
                ) : (
                  getInitials(profile.fullName)
                )}
              </div>
              <h2 className="mt-4 text-lg font-semibold">{profile.fullName}</h2>
              <p className="text-sm text-muted-foreground">{profile.email}</p>
              <div className="mt-3 flex flex-wrap justify-center gap-2">
                <Badge variant="info">{getRoleLabel(profile.role)}</Badge>
                <Badge variant={profile.status === "active" ? "success" : "warning"}>
                  {profile.status || "unknown"}
                </Badge>
              </div>
              <label className="btn-outline btn-sm mt-5 cursor-pointer">
                <Camera size={14} />
                {isUploadingAvatar ? "Uploading..." : "Change Photo"}
                <input type="file" accept="image/*" onChange={handleAvatarUpload} className="hidden" disabled={isUploadingAvatar} />
              </label>
            </div>
          </Card>

          <Card>
            <div className="flex items-center gap-2 mb-4">
              <Shield size={18} className="text-primary" />
              <h2 className="font-semibold">{t("profilePage.account")}</h2>
            </div>
            <div className="space-y-3">
              {accountStatus.map((item) => (
                <div key={item.label} className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{item.label}</span>
                  <span className="font-medium">{item.value}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <div className="flex items-center gap-2 mb-5">
              <UserRound size={18} className="text-primary" />
              <h2 className="font-semibold">{t("profilePage.personal_information")}</h2>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <Input label={t("profilePage.full_name")} value={fullName} onChange={(e) => setFullName(e.target.value)} required />
              <Input label={t("profilePage.email")} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              <Input label={t("profilePage.phone_number")} value={phoneNumber} onChange={(e) => setPhoneNumber(e.target.value)} />
              {canEditSpecialization && (
                <>
                  <Select
                    label={t("profilePage.specialization")}
                    value={specialization}
                    onChange={(e) => setSpecialization(e.target.value as EngineerDiscipline)}
                    options={SPECIALIZATION_OPTIONS}
                  />
                  <Input label={t("profilePage.license_number")} value={licenseNumber} onChange={(e) => setLicenseNumber(e.target.value)} />
                  <Input
                    label={t("profilePage.years_of_experience")}
                    type="number"
                    min="0"
                    value={yearsOfExperience}
                    onChange={(e) => setYearsOfExperience(e.target.value)}
                  />
                </>
              )}
            </div>
            <div className="flex justify-end mt-6">
              <Button onClick={handleSaveProfile} isLoading={isSavingProfile} leftIcon={<Save size={16} />}>
                {t("profilePage.save_profile")}
              </Button>
            </div>
          </Card>

          <Card>
            <div className="flex items-center gap-2 mb-5">
              <Mail size={18} className="text-primary" />
              <h2 className="font-semibold">{t("profilePage.notification_preferences")}</h2>
            </div>
            <div className="grid gap-3">
              <label className="flex items-center justify-between rounded-md border px-4 py-3">
                <span>
                  <span className="block text-sm font-medium">{t("profilePage.email_notifications")}</span>
                  <span className="block text-xs text-muted-foreground">{t("profilePage.receive_account_and_project_updates_by")}</span>
                </span>
                <input type="checkbox" checked={notifyByEmail} onChange={(e) => setNotifyByEmail(e.target.checked)} />
              </label>
            </div>
            <div className="flex justify-end mt-6">
              <Button onClick={handleSaveProfile} isLoading={isSavingProfile} variant="outline">
                {t("profilePage.save_preferences")}
              </Button>
            </div>
          </Card>

          <Card>
            <form onSubmit={handleChangePassword}>
              <div className="flex items-center gap-2 mb-5">
                <KeyRound size={18} className="text-primary" />
                <h2 className="font-semibold">{t("profilePage.password")}</h2>
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                <Input
                  label={t("profilePage.current_password")}
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                />
                <Input
                  label={t("profilePage.new_password")}
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
                <Input
                  label={t("profilePage.confirm_new_password")}
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </div>
              <div className="flex justify-end mt-6">
                <Button type="submit" isLoading={isSavingPassword}>
                  {t("profilePage.update_password")}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      </div>
    </div>
  );
};
