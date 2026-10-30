import type { ReactNode } from "react";

interface PageHeaderProps {
  title: ReactNode;
  /** A short line above the title — usually the project or the workspace. */
  context?: ReactNode;
  /** One sentence on what this page is for. */
  description?: ReactNode;
  /** Measured facts about the page's subject, set as a metadata strip. */
  meta?: { label: ReactNode; value: ReactNode }[];
  /** The page's primary action, and at most a secondary one or two. */
  actions?: ReactNode;
  className?: string;
}

/**
 * The title block every working page opens with: what this is, the facts that
 * qualify it, and the action that belongs to it — ruled off from the work
 * below, the way a drawing's title block is.
 */
export const PageHeader = ({ title, context, description, meta, actions, className = "" }: PageHeaderProps) => (
  <header className={`page-header ${className}`}>
    <div className="min-w-0">
      {context && <p className="page-kicker">{context}</p>}
      <h1 className="page-title">{title}</h1>
      {description && <p className="page-intro">{description}</p>}
      {meta && meta.length > 0 && (
        <dl className="title-block-meta">
          {meta.map((item, index) => (
            <div key={index} className="flex items-baseline gap-2">
              <dt>{item.label}</dt>
              <dd>{item.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
    {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
  </header>
);
