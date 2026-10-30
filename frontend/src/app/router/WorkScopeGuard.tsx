import { useTranslation } from "react-i18next";
import { Link, Outlet } from "react-router-dom";

import { useProjectWorkspace } from "../../features/projects/context/ProjectWorkspaceContext";
import { ROUTES } from "../../utils/constants";

/**
 * Portfolio pages that gather project *work* — tasks, documents, messages,
 * coordination, the client overview — for somebody who works in no project.
 *
 * Since QA-06B the office administrator sees every project's record but opens
 * the work only of projects they are on. Without this they reached these
 * pages and got empty lists that read as "nothing here", or refusals with no
 * explanation (QA 2026-10-22). They get the reason and the way forward
 * instead. The server enforces the same rule on every endpoint behind these
 * pages; this only decides what the interface says.
 */
export const WorkScopeGuard = () => {
  const { t } = useTranslation();
  const { worksInAProject } = useProjectWorkspace();

  if (worksInAProject) return <Outlet />;

  return (
    <div className="page-container">
      <div role="alert" className="mx-auto max-w-xl rounded-xl border bg-card p-6 text-center">
        <h1 className="text-lg font-semibold">{t("workScope.title")}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{t("workScope.explanation")}</p>
        <Link to={ROUTES.PROJECTS} className="mt-4 inline-flex text-sm font-medium text-primary hover:underline">
          {t("workScope.openProjects")}
        </Link>
      </div>
    </div>
  );
};

export default WorkScopeGuard;
