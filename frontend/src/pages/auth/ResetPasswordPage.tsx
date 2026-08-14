import { useState } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../utils/errorMessage";
import { Link, useSearchParams } from "react-router-dom";

import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import api from "../../services/api";
import { ROUTES } from "../../utils/constants";


export const ResetPasswordPage = () => {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!token) { setError("This password reset link is missing its security token."); return; }
    if (password.length < 8) { setError("Password must contain at least 8 characters."); return; }
    if (password !== confirmPassword) { setError("Passwords do not match."); return; }
    setError("");
    setIsLoading(true);
    try {
      await api.auth.resetPassword({ token, newPassword: password });
      setComplete(true);
    } catch (err: any) {
      setError(errorMessage(err, "This reset link is invalid or expired."));
    } finally {
      setIsLoading(false);
    }
  };

  if (complete) return <div className="space-y-4 p-6 text-center">
    <h1 className="text-2xl font-bold">{t("resetPassword.password_updated")}</h1>
    <p className="rounded-md bg-green-50 px-4 py-3 text-sm text-green-700">{t("resetPassword.your_password_was_changed_successfully")}</p>
    <Link to={ROUTES.LOGIN}><Button fullWidth>{t("resetPassword.go_to_login")}</Button></Link>
  </div>;

  return <div className="p-6">
    <h1 className="mb-2 text-center text-2xl font-bold">{t("resetPassword.choose_a_new_password")}</h1>
    <p className="mb-6 text-center text-sm text-muted-foreground">{t("resetPassword.use_at_least_8_characters_and_keep_this")}</p>
    <form className="space-y-4" onSubmit={handleSubmit}>
      {error && <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>}
      <Input label={t("resetPassword.new_password")} type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
      <Input label={t("resetPassword.confirm_password")} type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required />
      <Button type="submit" fullWidth isLoading={isLoading} disabled={!token}>{t("resetPassword.update_password")}</Button>
    </form>
    <p className="mt-6 text-center text-sm"><Link className="font-medium text-primary hover:underline" to={ROUTES.LOGIN}>{t("resetPassword.back_to_login")}</Link></p>
  </div>;
};
