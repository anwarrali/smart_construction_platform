import type { ReactNode, HTMLAttributes } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  header?: ReactNode;
  footer?: ReactNode;
  isHoverable?: boolean;
  padding?: "none" | "sm" | "md" | "lg";
}

/* `.card` already pads itself (p-4); only a non-default size needs a utility,
   and utilities win over the component layer, so `className="p-5"` still
   overrides either. */
const paddingClasses = {
  none: "p-0",
  sm: "p-3",
  md: "",
  lg: "p-6",
};

const sectionPadding = {
  none: "",
  sm: "p-3",
  md: "p-4",
  lg: "p-6",
};

/**
 * A ruled panel. With a `header` it becomes a titled panel: the header sits on
 * the sunken title strip and is ruled off from the body, so a panel never needs
 * a second card inside it to look structured.
 *
 * The body used to carry its own padding on top of the panel's, which gave
 * every plain `<Card>` a 44px inset; a panel is now padded exactly once.
 */
export const Card = ({
  children,
  header,
  footer,
  isHoverable = false,
  padding = "md",
  className = "",
  ...props
}: CardProps) => {
  const base = isHoverable ? "card-hover" : "card";
  if (!header && !footer) {
    return (
      <div className={`${base} ${paddingClasses[padding]} ${className}`} {...props}>
        {children}
      </div>
    );
  }
  return (
    <div className={`${base} p-0 ${className}`} {...props}>
      {header && <div className="panel-head">{header}</div>}
      <div className={sectionPadding[padding]}>{children}</div>
      {footer && <div className="border-t px-4 py-3">{footer}</div>}
    </div>
  );
};
