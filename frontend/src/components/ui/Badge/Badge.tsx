import type { ReactNode } from "react";

type BadgeVariant =
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "neutral"
  | "primary";
type BadgeSize = "sm" | "md" | "lg";

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  size?: BadgeSize;
  dot?: boolean;
  className?: string;
}

/* Every variant is a status chip from the shared vocabulary: square, edged in
   its own colour, with a leading square so the state does not rest on hue
   alone. `primary` is the one non-status tag — a solid steel label. */
const variantClasses: Record<BadgeVariant, string> = {
  success: "badge-success",
  warning: "badge-warning",
  danger: "badge-danger",
  info: "badge-info",
  neutral: "badge-neutral",
  primary: "inline-flex items-center border border-primary bg-primary text-primary-foreground",
};

const sizeClasses: Record<BadgeSize, string> = {
  sm: "text-[10px] leading-4",
  md: "",
  lg: "text-xs px-2 py-0.5",
};

export const Badge = ({
  children,
  variant = "neutral",
  size = "md",
  dot = false,
  className = "",
}: BadgeProps) => {
  return (
    <span
      className={`${variantClasses[variant]} ${sizeClasses[size]} font-semibold ${variant === "primary" ? "px-1.5 py-px text-[11px]" : ""} ${className}`}
    >
      {dot && variant === "primary" && <span className="me-1.5 h-1.5 w-1.5 bg-current" />}
      {children}
    </span>
  );
};
