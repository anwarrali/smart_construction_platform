export interface StepUpChallenge {
  purpose: string;
  label: string;
  expiresAt: string;
  maxAttempts: number;
  resendAfterSeconds: number;
  /** False when the server could not actually send the code (no SMTP configured). */
  delivered: boolean;
  /** Development only; absent unless OTP_DEV_ECHO_ENABLED is explicitly on. */
  devCode?: string;
}

export interface StepUpVerifyResult {
  purpose: string;
  verified: boolean;
  expiresAt: string;
}
