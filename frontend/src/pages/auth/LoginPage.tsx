import { useState } from "react";
import { errorMessage } from "../../utils/errorMessage";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Eye, EyeOff } from "lucide-react";

import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { useAuth } from "../../hooks/useAuth";
import { ROUTES } from "../../utils/constants";
import { StructIQLogo } from "../../components/brand/StructIQLogo";

export const LoginPage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { login, isLoading } = useAuth();
  const [identity, setIdentity] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    if (!identity.trim() || !password) {
      setError(t("validation.required"));
      return;
    }
    try {
      const user = await login({ email: identity.trim(), password });
      navigate(user.mustChangePassword ? ROUTES.CHANGE_PASSWORD : ROUTES.DASHBOARD, { replace: true });
    } catch (err: unknown) {
      setError(errorMessage(err, t("auth.invalidCredentials")));
    }
  };

  return (
    <div className="animate-rise-in">
      {/* The brand is the way home. Nobody should feel trapped on a sign-in
          screen, and a logo that navigates is the expected affordance — so
          there is no separate back button competing with the form. */}
      <div className="mb-7 flex justify-center">
        <Link
          to={ROUTES.HOME}
          aria-label={t("auth.backToHome", { defaultValue: "StructIQ — back to home" })}
          title={t("auth.backToHome", { defaultValue: "StructIQ — back to home" })}
          className="rounded-control transition-opacity hover:opacity-80"
        >
          <StructIQLogo variant="full" size={38} />
        </Link>
      </div>

      <div className="text-center">
        <h1 className="text-[1.6rem] font-semibold">{t("auth.loginTitle")}</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">{t("authAside.credentialsHint")}</p>
      </div>

      {/* The sheet the form sits on. */}
      <div className="panel relative mt-7 p-6 shadow-lift">
        {/* Corner registration marks — a quiet drafting detail. */}
        <span aria-hidden className="pointer-events-none absolute -top-px -start-px h-3 w-3 rounded-ss-panel border-s-2 border-t-2 border-accent/70" />
        <span aria-hidden className="pointer-events-none absolute -bottom-px -end-px h-3 w-3 rounded-ee-panel border-b-2 border-e-2 border-accent/70" />

        {error && (
          <div role="alert" className="mb-5 rounded-control border border-destructive/25 bg-destructive/[0.07] px-3.5 py-2.5 text-sm text-destructive">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            id="identity"
            label={t("auth.email")}
            placeholder="admin or name@company.com"
            value={identity}
            onChange={(event) => setIdentity(event.target.value)}
            autoComplete="username"
            required
          />
          <Input
            id="password"
            type={showPassword ? "text" : "password"}
            label={t("auth.password")}
            placeholder={t("auth.password")}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            rightElement={
              <button
                type="button"
                onClick={() => setShowPassword((value) => !value)}
                className="text-muted-foreground transition-colors hover:text-foreground"
                aria-label={t("auth.password")}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            }
            required
          />

          <div className="flex justify-end">
            <Link to={ROUTES.FORGOT_PASSWORD} className="text-xs font-medium text-muted-foreground transition-colors hover:text-primary">
              {t("auth.forgotPassword")}
            </Link>
          </div>

          <Button id="login-submit-btn" type="submit" fullWidth isLoading={isLoading} className="h-11">
            {t("auth.login")} <ArrowRight size={16} className="rtl-flip" />
          </Button>
        </form>
      </div>

      <p className="mt-5 text-center text-xs text-muted-foreground">
        {t("authAside.managedByAdmin")}
      </p>
    </div>
  );
};
