import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import api from "../../services/api";
import { ROUTES } from "../../utils/constants";

export const ForgotPasswordPage = () => {
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
      <h1 className="text-2xl font-bold text-center mb-2">Reset Password</h1>
      <p className="text-sm text-muted-foreground text-center mb-6">
        Enter your email and we&apos;ll send you a secure reset link.
      </p>

      {sent ? (
        <div className="text-center space-y-4">
          <div className="bg-green-50 text-green-600 text-sm rounded-md px-4 py-3">
            If an account exists with that email, you&apos;ll receive reset instructions shortly.
          </div>
          <Link to={ROUTES.LOGIN}>
            <Button variant="outline" fullWidth>
              Back to Login
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
            label="Email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <Button type="submit" variant="primary" fullWidth isLoading={isLoading}>
            Send Reset Link
          </Button>
        </form>
      )}

      <p className="text-center text-sm text-muted-foreground mt-6">
        <Link to={ROUTES.LOGIN} className="text-primary hover:underline font-medium">
          Back to Login
        </Link>
      </p>
    </div>
  );
};
