import type { ReactNode, HTMLAttributes } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  header?: ReactNode;
  footer?: ReactNode;
  isHoverable?: boolean;
  padding?: "none" | "sm" | "md" | "lg";
}

const paddingClasses = {
  none: "p-0",
  sm: "p-3",
  md: "p-6",
  lg: "p-8",
};

export const Card = ({
  children,
  header,
  footer,
  isHoverable = false,
  padding = "md",
  className = "",
  ...props
}: CardProps) => {
  return (
    <div
      className={`${isHoverable ? "card-hover" : "card"} ${className}`}
      {...props}
    >
      {header && (
        <div
          className={`${padding !== "none" ? "px-6 pt-6 pb-4" : "p-0"} border-b mb-4`}
        >
          {header}
        </div>
      )}
      <div className={paddingClasses[padding]}>{children}</div>
      {footer && (
        <div
          className={`${padding !== "none" ? "px-6 pb-6 pt-4" : "p-0"} border-t mt-4`}
        >
          {footer}
        </div>
      )}
    </div>
  );
};
