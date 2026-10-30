import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { PageHeader } from "../../../components/ui/PageHeader";
import { Plus } from "lucide-react";
import { Input } from "../../../components/ui/Input";
import { Modal, ModalActions } from "../../../components/ui/Modal";
import { Select } from "../../../components/ui/Select";
import { Table } from "../../../components/ui/Table";
import type { Column } from "../../../components/ui/Table/Table";
import { projectsService } from "../services/projects.service";
import { DeleteProjectDialog } from "../components/DeleteProjectDialog";
import { usersService } from "../../users/services/users.service";
import api from "../../../services/api";
import { projectEntryPath } from "../../../utils/projectRoutes";
import { formatDate } from "../../../utils/date";
import { useRole } from "../../../hooks/useRole";
import { useVocabulary } from "../../../utils/vocabulary";
import type { CreateProjectRequest, Project, ProjectMember, ProjectStatus } from "../../../types/project";
import type { UserProfile } from "../../../types/user";

type ProjectFormState = {
  id?: string;
  name: string;
  description: string;
  location: string;
  projectType: string;
  startDate: string;
  plannedEndDate: string;
  budgetTotal: string;
  status: ProjectStatus;
  ownerId: string;
  projectManagerId: string;
};

const emptyProjectForm: ProjectFormState = {
  name: "",
  description: "",
  location: "",
  projectType: "",
  startDate: "",
  plannedEndDate: "",
  budgetTotal: "",
  status: "planning",
  ownerId: "",
  projectManagerId: "",
};

const normalizeUsers = (response: unknown): UserProfile[] => {
  if (Array.isArray(response)) return response as UserProfile[];
  const data = response as { data?: UserProfile[]; items?: UserProfile[] };
  return data.data || data.items || [];
};

const normalizeProjects = (response: unknown): Project[] => {
  const data = response as { data?: Project[]; items?: Project[] };
  return data.data || data.items || [];
};

const statusVariant: Record<string, "neutral" | "success" | "warning" | "danger" | "info"> = {
  planning: "info",
  active: "success",
  on_hold: "warning",
  delayed: "danger",
  completed: "neutral",
  cancelled: "neutral",
};

const PROJECT_STATUSES: ProjectStatus[] = ["planning", "active", "on_hold", "delayed", "completed", "cancelled"];

export const ProjectsPage = () => {
  const { t } = useTranslation();
  const { hasCapability } = useRole();
  const vocabulary = useVocabulary();
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isMembersOpen, setIsMembersOpen] = useState(false);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [selectedMembers, setSelectedMembers] = useState<ProjectMember[]>([]);
  const [form, setForm] = useState<ProjectFormState>(emptyProjectForm);
  const [isSaving, setIsSaving] = useState(false);
  const [deleting, setDeleting] = useState<Project | null>(null);
  const canCreate = hasCapability("platform.create_project");
  /** Project setup: owner, manager, dates, budget. */
  const canEditSetup = hasCapability("project.edit");
  const canStaff = hasCapability("project.manage_members");
  const seesPortfolio = hasCapability("platform.view_all_projects");
  const choosesPrincipals = canCreate || canEditSetup;

  /* Candidates come from the server, by the same rule it applies when the
     project is saved — never from a role name the interface would have to
     guess at. */
  const [owners, setOwners] = useState<UserProfile[]>([]);
  const [projectManagers, setProjectManagers] = useState<UserProfile[]>([]);

  const userById = useMemo(
    () => new Map([...users, ...owners, ...projectManagers].map((user) => [user.id, user])),
    [users, owners, projectManagers],
  );

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    try {
      const projectResponse = await projectsService.list({ limit: 100 });
      setProjects(normalizeProjects(projectResponse));
      if (choosesPrincipals) {
        const [eligibleOwners, eligibleManagers] = await Promise.all([
          api.users.eligible("project_owner"), api.users.eligible("project_manager"),
        ]);
        setOwners(eligibleOwners);
        setProjectManagers(eligibleManagers);
      }
      if (seesPortfolio && hasCapability("platform.manage_users")) {
        const userResponse = await usersService.list();
        setUsers(normalizeUsers(userResponse));
      } else {
        setUsers([]);
      }
    } catch (err: any) {
      toast.error(errorMessage(err, t("projectsPage.loadFailed")));
    } finally {
      setIsLoading(false);
    }
  }, [choosesPrincipals, seesPortfolio, hasCapability, t]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const filteredProjects = useMemo(() => {
    const q = search.trim().toLowerCase();
    return projects.filter((project) => {
      const matchesSearch = !q || [project.name, project.description, project.location]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(q));
      const matchesStatus = !statusFilter || project.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [projects, search, statusFilter]);

  const openCreate = () => {
    setSelectedProject(null);
    setForm(emptyProjectForm);
    setIsFormOpen(true);
  };

  const openEdit = (project: Project) => {
    setSelectedProject(project);
    setForm({
      id: project.id,
      name: project.name || "",
      description: project.description || "",
      location: project.location || "",
      projectType: project.projectType || "",
      startDate: project.startDate?.split("T")[0] || "",
      plannedEndDate: project.plannedEndDate?.split("T")[0] || "",
      budgetTotal: project.budgetTotal?.toString() || "",
      status: project.status,
      ownerId: project.ownerId || "",
      projectManagerId: project.projectManagerId || "",
    });
    setIsFormOpen(true);
  };

  const openMembers = async (project: Project) => {
    setSelectedProject(project);
    setIsMembersOpen(true);
    try {
      const members = await projectsService.getMembers(project.id);
      setSelectedMembers(members);
    } catch (err: any) {
      // Never fall back to another copy of the team: a refusal here is the
      // server saying this person may not see it. Showing the list embedded in
      // the project anyway is how a "not authorized" toast appeared beside
      // the full team (QA 2026-10-22).
      toast.error(errorMessage(err, t("projectsPage.loadMembersFailed")));
      setSelectedMembers([]);
      setIsMembersOpen(false);
    }
  };

  const saveProject = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!form.name.trim()) {
      toast.error(t("projectsPage.nameRequired"));
      return;
    }
    if (!form.ownerId) {
      toast.error(t("projectsPage.ownerRequired"));
      return;
    }
    if (!form.projectManagerId) {
      toast.error(t("projectsPage.projectManagerRequired"));
      return;
    }

    setIsSaving(true);
    try {
      const payload: CreateProjectRequest = {
        name: form.name.trim(),
        description: form.description.trim() || undefined,
        location: form.location.trim() || undefined,
        projectType: form.projectType.trim() || undefined,
        startDate: form.startDate || undefined,
        plannedEndDate: form.plannedEndDate || undefined,
        budgetTotal: Number(form.budgetTotal) || undefined,
        status: form.status,
        ownerId: form.ownerId,
        projectManagerId: form.projectManagerId,
      };

      if (selectedProject) await projectsService.update(selectedProject.id, payload);
      else await projectsService.create(payload);

      toast.success(selectedProject ? t("projectsPage.projectUpdated") : t("projectsPage.projectCreated"));
      setIsFormOpen(false);
      setSelectedProject(null);
      setForm(emptyProjectForm);
      fetchData();
    } catch (err: any) {
      toast.error(errorMessage(err, t("projectsPage.saveFailed")));
    } finally {
      setIsSaving(false);
    }
  };

  const columns: Column<Project>[] = [
    {
      key: "name",
      header: t("projectsPage.columnProject"),
      render: (project) => (
        <div>
          <p className="font-medium">{project.name}</p>
          <p className="text-xs text-muted-foreground line-clamp-1">{project.description || t("projectsPage.noDescription")}</p>
        </div>
      ),
    },
    {
      key: "location",
      header: t("projectsPage.columnLocation"),
      render: (project) => <span className="text-sm text-muted-foreground">{project.location || "-"}</span>,
    },
    {
      key: "status",
      header: t("projectsPage.columnStatus"),
      render: (project) => (
        <Badge variant={statusVariant[project.status] || "neutral"}>
          {vocabulary.projectStatus(project.status)}
        </Badge>
      ),
    },
    {
      key: "completionPercentage",
      header: t("projectsPage.columnProgress"),
      render: (project) => <div className="min-w-28"><div className="flex justify-between text-xs"><span>{project.completionPercentage}%</span><span>{t("projectsPage.openIssuesCount", { count: project.openIssueCount || 0 })}</span></div><div className="mt-1 h-1.5 rounded bg-muted"><div className="h-full rounded bg-primary" style={{width:`${project.completionPercentage}%`}} /></div></div>,
    },
    {
      key: "ownerId",
      header: t("projectsPage.columnOwner"),
      render: (project) => <span>{userById.get(project.ownerId)?.fullName || "-"}</span>,
    },
    {
      key: "projectManagerId",
      header: t("projectsPage.columnProjectManager"),
      render: (project) => <span>{userById.get(project.projectManagerId || "")?.fullName || "-"}</span>,
    },
    {
      key: "plannedEndDate",
      header: t("projectsPage.columnDates"),
      render: (project) => (
        <span className="text-sm text-muted-foreground">
          {t("projectsPage.dateRange", {
            start: project.startDate ? formatDate(project.startDate) : "-",
            end: project.plannedEndDate ? formatDate(project.plannedEndDate) : "-",
          })}
        </span>
      ),
    },
    {
      key: "actions",
      header: "",
      render: (project) => (
        <div className="flex justify-end gap-2">
          {/* The team list is `project.manage_members`, as on the server. */}
          {canStaff && <Button variant="outline" size="sm" onClick={() => openMembers(project)}>
            {t("projectsPage.view_members")}
          </Button>}
          {canStaff && <Button variant="outline" size="sm" onClick={() => navigate(`/admin/projects/${project.id}/team`)}>
            {t("projectsPage.manage_team")}
          </Button>}
          <Button size="sm" onClick={() => navigate(projectEntryPath(project, hasCapability))}>
            {t("projectsPage.open")}
          </Button>
          {canEditSetup && (
            <Button variant="ghost" size="sm" onClick={() => openEdit(project)}>
              {t("projectsPage.edit")}
            </Button>
          )}
          {/* Per project, from the server: `project.delete` may be granted for one project only. */}
          {project.canDelete && (
            <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setDeleting(project)}>
              {t("projectsPage.delete.action")}
            </Button>
          )}
        </div>
      ),
      className: "text-right",
    },
  ];
  const visibleColumns = seesPortfolio ? columns : columns.filter(column => !["ownerId", "projectManagerId"].includes(String(column.key)));

  return (
    <div className="page-container space-y-6">
      <PageHeader
        title={t("projectsPage.projects")}
        description={
          seesPortfolio
            ? t("projectsPage.subtitleDefault")
            : canStaff
              ? t("projectsPage.subtitlePm")
              : t("projectsPage.subtitleEngineer")
        }
        actions={canCreate && (
          <Button leftIcon={<Plus size={15} />} onClick={openCreate}>{t("projectsPage.addProject")}</Button>
        )}
      />

      <div className="space-y-0">
        {/* Filters sit on a toolbar ruled onto the register below, not in a
            second card around it. */}
        <div className="toolbar grid border-b-0 md:grid-cols-[1fr_220px] [&_.form-group]:mb-0">
          <Input
            aria-label={t("projectsPage.search_projects")}
            placeholder={t("projectsPage.search_projects")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Select
            options={[
              { value: "", label: t("projectsPage.allStatuses") },
              ...PROJECT_STATUSES.map((status) => ({ value: status, label: vocabulary.projectStatus(status) })),
            ]}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label={t("projectsPage.allStatuses")}
          />
        </div>

        <Table
          columns={visibleColumns}
          data={filteredProjects}
          keyExtractor={(project) => project.id}
          isLoading={isLoading}
          emptyMessage={t("projectsPage.no_projects_found")}
        />
      </div>

      <Modal
        isOpen={isFormOpen}
        onClose={() => setIsFormOpen(false)}
        title={selectedProject ? t("projectsPage.editProject") : t("projectsPage.addProject")}
        size="xl"
      >
        <form onSubmit={saveProject} className="space-y-4">
          <Input
            label={t("projectsPage.project_name")}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label={t("projectsPage.description")}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
            <Input
              label={t("projectsPage.location")}
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
            />
            <Input
              label={t("projectsPage.project_type")}
              value={form.projectType}
              onChange={(e) => setForm({ ...form, projectType: e.target.value })}
              placeholder={t("projectsPage.projectTypePlaceholder")}
            />
            <Select
              label={t("projectsPage.status")}
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value as ProjectStatus })}
              options={PROJECT_STATUSES.map((status) => ({ value: status, label: vocabulary.projectStatus(status) }))}
            />
            <Input
              label={t("projectsPage.start_date")}
              type="date"
              value={form.startDate}
              onChange={(e) => setForm({ ...form, startDate: e.target.value })}
            />
            <Input
              label={t("projectsPage.expected_end_date")}
              type="date"
              value={form.plannedEndDate}
              onChange={(e) => setForm({ ...form, plannedEndDate: e.target.value })}
            />
            <Input
              label={t("projectsPage.budget_total")}
              type="number"
              min="0"
              value={form.budgetTotal}
              onChange={(e) => setForm({ ...form, budgetTotal: e.target.value })}
            />
            <Select
              label={t("projectsPage.owner")}
              value={form.ownerId}
              onChange={(e) => setForm({ ...form, ownerId: e.target.value })}
              options={[
                { value: "", label: t("projectsPage.selectOwner") },
                ...owners.map((owner) => ({ value: owner.id, label: owner.fullName })),
              ]}
              required
            />
            <Select
              label={t("projectsPage.project_manager")}
              value={form.projectManagerId}
              onChange={(e) => setForm({ ...form, projectManagerId: e.target.value })}
              options={[
                { value: "", label: t("projectsPage.selectProjectManager") },
                ...projectManagers.map((pm) => ({ value: pm.id, label: pm.fullName })),
              ]}
              required
            />
          </div>
          <ModalActions>
            <Button variant="outline" type="button" onClick={() => setIsFormOpen(false)}>
              {t("projectsPage.cancel")}
            </Button>
            <Button type="submit" isLoading={isSaving}>
              {selectedProject ? t("projectsPage.saveChanges") : t("projectsPage.createProject")}
            </Button>
          </ModalActions>
        </form>
      </Modal>

      <DeleteProjectDialog
        key={deleting?.id ?? "none"}
        project={deleting}
        onClose={() => setDeleting(null)}
        onDeleted={(projectId) => {
          setDeleting(null);
          setProjects((rows) => rows.filter((row) => row.id !== projectId));
        }}
      />

      <Modal
        isOpen={isMembersOpen}
        onClose={() => setIsMembersOpen(false)}
        title={selectedProject ? t("projectsPage.membersTitle", { name: selectedProject.name }) : t("projectsPage.membersTitleDefault")}
        size="lg"
      >
        <div className="space-y-3">
          {selectedMembers.map((member) => (
            <div key={member.id} className="flex items-center justify-between rounded-md border px-4 py-3">
              <div>
                <p className="font-medium">{member.user?.fullName || userById.get(member.userId)?.fullName || t("projectsPage.unknownUser")}</p>
                <p className="text-xs text-muted-foreground">{member.user?.email || userById.get(member.userId)?.email || ""}</p>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant="info">{member.projectRoleName || vocabulary.orgRole(member.user?.orgRole)}</Badge>
                <Badge variant={member.isActive ? "success" : "neutral"}>
                  {member.isActive ? t("projectsPage.active") : t("projectsPage.inactive")}
                </Badge>
              </div>
            </div>
          ))}
          {selectedMembers.length === 0 && (
            <div className="py-8 text-center text-sm text-muted-foreground">{t("projectsPage.no_members_assigned")}</div>
          )}
        </div>
      </Modal>
    </div>
  );
};
