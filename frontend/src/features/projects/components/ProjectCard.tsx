import { useNavigate } from "react-router-dom";
import { useVocabulary } from "../../../utils/vocabulary";
import { useTranslation } from "react-i18next";
import { AlertTriangle, ArrowRight, CalendarDays } from "lucide-react";

import { formatDate, getDaysRemaining } from "../../../utils/date";
import type { Project } from "../../../types/project";
import { useRole } from "../../../hooks/useRole";
import { projectModulePath } from "../../../utils/projectRoutes";

interface ProjectCardProps {
  project: Project;
}

/** Status maps onto the site-convention state colours, not onto a chart palette. */
const STATE: Record<string, { chip: string; rule: string }> = {
  planning:  { chip: "chip-idle",     rule: "bg-state-idle" },
  active:    { chip: "chip-progress", rule: "bg-state-progress" },
  on_hold:   { chip: "chip-blocked",  rule: "bg-state-blocked" },
  delayed:   { chip: "chip-overdue",  rule: "bg-state-overdue" },
  completed: { chip: "chip-verified", rule: "bg-state-verified" },
  cancelled: { chip: "chip-idle",     rule: "bg-state-idle" },
};

/**
 * A project as it appears in the portfolio.
 *
 * Set out like a drawing register entry rather than a marketing card: a status
 * rule down the leading edge, the name and reference, then the measured facts
 * — progress against a ticked scale, dates, and anything demanding attention.
 */
export const ProjectCard = ({ project }: ProjectCardProps) => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const vocabulary = useVocabulary();
  const { role, isConsultantEngineer } = useRole();
  const affiliation = isConsultantEngineer ? ("external_consultant" as const) : undefined;
  const daysRemaining = getDaysRemaining(project.plannedEndDate || "");
  const state = STATE[project.status] || STATE.planning;
  const progress = Math.max(0, Math.min(100, Number(project.completionPercentage) || 0));
  const openIssues = project.openIssueCount || 0;
  const isSlipping = project.status === "delayed";
  const isTight = project.status === "active" && daysRemaining <= 7 && daysRemaining > 0;

  return (
    <button
      type="button"
      onClick={() => navigate(projectModulePath(project.id, "dashboard", role, affiliation))}
      className="group panel relative w-full overflow-hidden p-0 text-start transition-[box-shadow,transform] duration-200 hover:-translate-y-px hover:shadow-lift"
    >
      {/* Status carried by a rule on the leading edge. */}
      <span aria-hidden className={`absolute inset-y-0 start-0 w-[3px] ${state.rule}`} />

      <div className="p-5 ps-6">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="truncate text-[15px] font-semibold tracking-heading">{project.name}</h3>
            {project.location && (
              <p className="mt-1 truncate text-xs text-muted-foreground">{project.location}</p>
            )}
          </div>
          <span className={state.chip}>
            {vocabulary.projectStatus(project.status)}
          </span>
        </div>

        {/* Progress as a measured quantity against a ticked scale. */}
        <div className="mt-5">
          <div className="flex items-baseline justify-between">
            <span className="label-caps text-muted-foreground">{t("project.progress")}</span>
            <span className="text-measured text-sm font-semibold">{progress}%</span>
          </div>
          <div className="gauge gauge-ticked mt-2">
            <div className="gauge-fill" style={{ width: `${progress}%` }} />
          </div>
        </div>

        {/* The measured facts, divided from the body by a hairline. */}
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t pt-3 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <CalendarDays size={13} className="shrink-0 opacity-70" />
            <span className="text-measured">
              {formatDate(project.startDate || "")} — {formatDate(project.plannedEndDate || "")}
            </span>
          </span>

          {openIssues > 0 && (
            <span className="inline-flex items-center gap-1.5 text-state-review">
              <AlertTriangle size={13} className="shrink-0" />
              <span className="text-measured">{openIssues}</span>
              <span>{t("project.openIssues")}</span>
            </span>
          )}

          {isSlipping && (
            <span className="chip-overdue ms-auto">
              {t("project.status.delayed")}
            </span>
          )}
          {isTight && (
            <span className="chip-review ms-auto text-measured">
              {t("project.daysRemaining", { count: daysRemaining })}
            </span>
          )}

          <ArrowRight
            size={14}
            className="rtl-flip ms-auto shrink-0 opacity-0 transition-opacity group-hover:opacity-60"
          />
        </div>
      </div>
    </button>
  );
};
