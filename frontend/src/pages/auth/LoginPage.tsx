import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Eye, EyeOff, LockKeyhole } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { useAuth } from "../../hooks/useAuth";
import { ROUTES } from "../../utils/constants";

export const LoginPage = () => {
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
      setError("Enter your username or email and password.");
      return;
    }
    try {
      const user = await login({ email: identity.trim(), password });
      navigate(user.mustChangePassword ? ROUTES.CHANGE_PASSWORD : ROUTES.DASHBOARD, { replace: true });
    } catch (err: unknown) {
      const detail = typeof err === "object" && err !== null && "response" in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || "Unable to sign in. Check your credentials and try again.");
    }
  };

  return (
    <div className="space-y-7">
      <div>
        <span className="inline-flex items-center gap-2 rounded-full bg-primary/8 px-3 py-1 text-xs font-semibold text-primary"><LockKeyhole size={13} /> Secure workspace access</span>
        <h1 className="mt-5 text-3xl font-bold tracking-tight">Sign in to your project workspace</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">Use the account credentials created by your platform administrator.</p>
      </div>

      {error && <div role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

      <form onSubmit={handleSubmit} className="space-y-5">
        <Input id="identity" label="Username or email" placeholder="admin or name@company.com" value={identity} onChange={(event) => setIdentity(event.target.value)} autoComplete="username" required />
        <Input id="password" type={showPassword ? "text" : "password"} label="Password" placeholder="Enter your password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" rightElement={<button type="button" onClick={() => setShowPassword((value) => !value)} className="text-muted-foreground transition-colors hover:text-foreground" aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button>} required />
        <div className="flex justify-end"><Link to={ROUTES.FORGOT_PASSWORD} className="text-xs font-medium text-muted-foreground transition-colors hover:text-primary">Forgot password?</Link></div>
        <Button id="login-submit-btn" type="submit" fullWidth isLoading={isLoading} className="h-11">Sign In <ArrowRight size={16} /></Button>
      </form>

      <p className="border-t pt-5 text-center text-xs text-muted-foreground">Accounts are managed by your organization’s administrator.</p>
    </div>
  );
};
