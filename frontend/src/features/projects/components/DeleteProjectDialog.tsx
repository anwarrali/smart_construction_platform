import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";

import { Button } from "../../../components/ui/Button";
import { Input } from "../../../components/ui/Input";
import { Modal, ModalActions } from "../../../components/ui/Modal";
import { errorMessage } from "../../../utils/errorMessage";
import { projectsService, type ProjectDeletionImpact } from "../services/projects.service";
import type { Project } from "../../../types/project";

type Props = { project: Project | null; onClose: () => void; onDeleted: (projectId: string) => void };

/**
 * Permanently deleting a project — `project.delete`, checked again by the server.
 *
 * The catalogue's policy is a permanent delete ("…and everything recorded
 * against it"); there is no archive state. So the dialog shows what goes with
 * the project, and asks for its name before the button enables. Cancelling
 * sends nothing. Success is reported only after the server answered 2xx.
 */
export const DeleteProjectDialog = ({ project, onClose, onDeleted }: Props) => {
  const { t } = useTranslation();
  const [impact, setImpact] = useState<ProjectDeletionImpact | null>(null);
  const [loadError, setLoadError] = useState("");
  const [typed, setTyped] = useState("");
  const [deleting, setDeleting] = useState(false);

  // State starts fresh per project: the page mounts the dialog with `key={project.id}`.
  useEffect(() => {
    if (!project) return;
    let current = true;
    projectsService.deletionImpact(project.id)
      .then((value) => { if (current) setImpact(value); })
      .catch((error) => { if (current) setLoadError(errorMessage(error, t("projectsPage.delete.loadFailed"))); });
    return () => { current = false; };
  }, [project, t]);

  if (!project) return null;
  const confirmed = typed.trim() === project.name.trim();

  const remove = async () => {
    setDeleting(true);
    try {
      await projectsService.delete(project.id);
      toast.success(t("projectsPage.delete.done", { name: project.name }));
      onDeleted(project.id);
    } catch (error) {
      toast.error(errorMessage(error, t("projectsPage.delete.failed")));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Modal isOpen onClose={onClose} title={t("projectsPage.delete.title", { name: project.name })}>
      <div className="space-y-4 text-sm">
        <p className="text-destructive">{t("projectsPage.delete.warning")}</p>
        {loadError && <p role="alert" className="text-destructive">{loadError}</p>}
        {!loadError && !impact && <p className="text-muted-foreground">{t("common.loading")}</p>}
        {impact && (
          <ul className="grid grid-cols-2 gap-1" data-testid="deletion-impact">
            {(["tasks", "members", "documents", "issues", "siteReports", "models"] as const).map((key) => (
              <li key={key}>{t(`projectsPage.delete.impact.${key}`, { count: impact[key] })}</li>
            ))}
          </ul>
        )}
        <Input
          label={t("projectsPage.delete.typeName", { name: project.name })}
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          autoComplete="off"
        />
      </div>
      <ModalActions>
        <Button variant="outline" onClick={onClose} disabled={deleting}>{t("common.cancel")}</Button>
        <Button variant="destructive" onClick={() => void remove()} disabled={!confirmed || !impact || deleting} isLoading={deleting}>
          {t("projectsPage.delete.confirm")}
        </Button>
      </ModalActions>
    </Modal>
  );
};

export default DeleteProjectDialog;
