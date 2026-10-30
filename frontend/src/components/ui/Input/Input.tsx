import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  rightElement?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helperText, rightElement, className = "", id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");
    const messageId = inputId ? `${inputId}-message` : undefined;

    return (
      <div className="form-group">
        {label && (
          <label htmlFor={inputId} className="form-label">
            {label}
          </label>
        )}
        <div className="relative">
          <input
            ref={ref}
            id={inputId}
            aria-invalid={error ? true : undefined}
            aria-describedby={(error || helperText) && messageId ? messageId : undefined}
            className={`input ${rightElement ? "pe-11" : ""} ${error ? "border-destructive" : ""} ${className}`}
            {...props}
          />
          {/* The trailing control sits on the logical end edge, so it follows
              the reading direction in Arabic. */}
          {rightElement && <div className="absolute inset-y-0 end-0 flex items-center pe-3">{rightElement}</div>}
        </div>
        {error && <p id={messageId} className="form-error">{error}</p>}
        {helperText && !error && (
          <p id={messageId} className="mt-1 text-xs text-muted-foreground">{helperText}</p>
        )}
      </div>
    );
  },
);

Input.displayName = "Input";
