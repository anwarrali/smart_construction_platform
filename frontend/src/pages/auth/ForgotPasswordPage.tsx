import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import api from "../../services/api";
import { ROUTES } from "../../utils/constants";

export const ForgotPasswordPage = () => {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      await api.auth.forgotPassword({ email: email.trim() });
      setSent(true);
    } catch {
      setError("Unable to process your request. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-center mb-2">{t("forgotPasswordPage.reset_password")}</h1>
      <p className="text-sm text-muted-foreground text-center mb-6">
        {t("forgotPasswordPage.enter_your_email_and_we_apos_ll_send_you")}
      </p>

      {sent ? (
        <div className="text-center space-y-4">
          <div className="bg-green-50 text-green-600 text-sm rounded-md px-4 py-3">
            If an account exists with that email, you&apos;ll receive reset instructions shortly.
          </div>
          <Link to={ROUTES.LOGIN}>
            <Button variant="outline" fullWidth>
              {t("forgotPasswordPage.back_to_login")}
            </Button>
          </Link>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="bg-red-50 text-red-600 text-sm rounded-md px-4 py-3">
              {error}
            </div>
          )}
          <Input
            id="email"
            type="email"
            label={t("forgotPasswordPage.email")}
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <Button type="submit" variant="primary" fullWidth isLoading={isLoading}>
            {t("forgotPasswordPage.send_reset_link")}
          </Button>
        </form>
      )}

      <p className="text-center text-sm text-muted-foreground mt-6">
        <Link to={ROUTES.LOGIN} className="text-primary hover:underline font-medium">
          {t("forgotPasswordPage.back_to_login")}
        </Link>
      </p>
    </div>
  );
};
