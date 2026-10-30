import type { ElementType, ReactNode } from "react";
import { Inbox } from "lucide-react";

interface EmptyStateProps {
  title: ReactNode;
  description?: ReactNode;
  icon?: ElementType;
  /** The action that would fill this space, when the person may take it. */
  action?: ReactNode;
  className?: string;
}

/** A drawn placeholder for a list with nothing in it — no illustration, no emoji. */
export const EmptyState = ({ title, description, icon: Icon = Inbox, action, className = "" }: EmptyStateProps) => (
  <div className={`empty-state ${className}`}>
    <Icon size={22} strokeWidth={1.5} className="empty-state-icon" aria-hidden />
    <p className="empty-state-title">{title}</p>
    {description && <p className="empty-state-description">{description}</p>}
    {action && <div className="mt-4">{action}</div>}
  </div>
);
