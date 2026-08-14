import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "../../../components/ui/Button";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import { Modal, ModalActions } from "../../../components/ui/Modal";
import { useAuth } from "../../../hooks/useAuth";
import type { CreateProjectRequest, Project } from "../../../types/project";

interface ProjectFormProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: CreateProjectRequest) => Promise<void>;
  project?: Project | null;
}

const STATUS_OPTIONS = [
  { value: "planning", label: "Planning" },
  { value: "active", label: "Active" },
  { value: "on_hold", label: "On Hold" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
];

export const ProjectForm = ({
  isOpen,
  onClose,
  onSubmit,
  project,
}: ProjectFormProps) => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [name, setName] = useState(project?.name || "");
  const [description, setDescription] = useState(project?.description || "");
  const [location, setLocation] = useState(project?.location || "");
  const [projectType, setProjectType] = useState(project?.projectType || "");
  const [startDate, setStartDate] = useState(
    project?.startDate?.split("T")[0] || "",
  );
  const [plannedEndDate, setPlannedEndDate] = useState(
    project?.plannedEndDate?.split("T")[0] || "",
  );
  const [budgetTotal, setBudgetTotal] = useState(
    project?.budgetTotal?.toString() || "",
  );
  const [status, setStatus] = useState<string>(project?.status || "planning");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const isEditing = !!project;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!name) {
      setError("Project name is required");
      return;
    }

    setIsLoading(true);
    await onSubmit({
      name,
      description,
      location,
      projectType: projectType || undefined,
      startDate: startDate || undefined,
      plannedEndDate: plannedEndDate || undefined,
      budgetTotal: Number(budgetTotal) || 0,
      ownerId: project?.ownerId || user?.id || "",
      projectManagerId: project?.projectManagerId || undefined,
    });
    setIsLoading(false);
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? "Edit Project" : "Create Project"}
      size="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="bg-red-50 text-red-600 text-sm rounded-md px-4 py-3">
            {error}
          </div>
        )}

        <Input
          label={t("projectForm.project_name")}
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <Input
          label={t("projectForm.description")}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <Input
          label={t("projectForm.location")}
          value={location}
          onChange={(e) => setLocation(e.target.value)}
        />
        <Input
          label={t("projectForm.project_type")}
          value={projectType}
          onChange={(e) => setProjectType(e.target.value)}
          placeholder="residential, commercial..."
        />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            label={t("projectForm.start_date")}
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
          <Input
            label={t("projectForm.planned_end_date")}
            type="date"
            value={plannedEndDate}
            onChange={(e) => setPlannedEndDate(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            label={t("projectForm.budget_total")}
            type="number"
            value={budgetTotal}
            onChange={(e) => setBudgetTotal(e.target.value)}
          />
          <Select
            label={t("projectForm.status")}
            options={STATUS_OPTIONS}
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          />
        </div>

        <ModalActions>
          <Button variant="outline" onClick={onClose} type="button">
            {t("projectForm.cancel")}
          </Button>
          <Button type="submit" isLoading={isLoading}>
            {isEditing ? "Save Changes" : "Create Project"}
          </Button>
        </ModalActions>
      </form>
    </Modal>
  );
};
