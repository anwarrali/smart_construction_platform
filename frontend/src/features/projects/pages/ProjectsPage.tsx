import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Input } from "../../../components/ui/Input";
import { Modal, ModalActions } from "../../../components/ui/Modal";
import { Select } from "../../../components/ui/Select";
import { Table } from "../../../components/ui/Table";
import type { Column } from "../../../components/ui/Table/Table";
import { projectsService } from "../services/projects.service";
import { usersService } from "../../users/services/users.service";
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
  consultantId: string;
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
  consultantId: "",
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
  const { isAdmin, isProjectManager, isEngineer, checkPermission } = useRole();
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
  const canCreate = checkPermission("create_project");

  const owners = useMemo(() => users.filter((user) => user.role === "owner" && user.status === "active"), [users]);
  const projectManagers = useMemo(
    () => users.filter((user) => user.role === "project_manager" && user.status === "active"),
    [users],
  );
  const consultants = useMemo(
    () => users.filter((user) => user.role === "engineer" && user.engineerAffiliation === "external_consultant" && user.status === "active"),
    [users],
  );

  const userById = useMemo(() => new Map(users.map((user) => [user.id, user])), [users]);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    try {
      const projectResponse = await projectsService.list({ limit: 100 });
      setProjects(normalizeProjects(projectResponse));
      if (isAdmin) {
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
  }, [isAdmin, t]);

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
    const consultantMember = project.members?.find((member) => member.roleOnProject === "consultant" && member.isActive);
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
      consultantId: consultantMember?.userId || "",
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
      toast.error(errorMessage(err, t("projectsPage.loadMembersFailed")));
      setSelectedMembers(project.members || []);
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

      const savedProject = selectedProject
        ? await projectsService.update(selectedProject.id, payload)
        : await projectsService.create(payload);

      if (form.consultantId) {
        await projectsService.addMember(savedProject.id, form.consultantId, "consultant");
      }

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
          {!isEngineer && <Button variant="outline" size="sm" onClick={() => openMembers(project)}>
            {t("projectsPage.view_members")}
          </Button>}
          {isAdmin && <Button variant="outline" size="sm" onClick={() => navigate(`/admin/projects/${project.id}/team`)}>
            {t("projectsPage.manage_team")}
          </Button>}
          <Button size="sm" onClick={() => navigate(
            isProjectManager
              ? `/project-manager/projects/${project.id}/dashboard`
              : isEngineer
                ? (isEngineer && window.location.pathname.startsWith("/consultant-engineer")
                  ? `/consultant-engineer/projects/${project.id}/dashboard`
                  : `/engineer/projects/${project.id}/dashboard`)
                : `/projects/${project.id}`
          )}>
            {t("projectsPage.open")}
          </Button>
          {isAdmin && (
            <Button variant="ghost" size="sm" onClick={() => openEdit(project)}>
              {t("projectsPage.edit")}
            </Button>
          )}
        </div>
      ),
      className: "text-right",
    },
  ];
  const visibleColumns = isAdmin ? columns : columns.filter(column => !["ownerId", "projectManagerId"].includes(String(column.key)));

  return (
    <div className="page-container space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t("projectsPage.projects")}</h1>
          <p className="text-muted-foreground">{
            isProjectManager
              ? t("projectsPage.subtitlePm")
              : isEngineer
                ? t("projectsPage.subtitleEngineer")
                : t("projectsPage.subtitleDefault")
          }</p>
        </div>
        {canCreate && (
          <Button onClick={openCreate}>+ {t("projectsPage.addProject")}</Button>
        )}
      </div>

      <Card>
        <div className="grid gap-3 mb-4 md:grid-cols-[1fr_220px]">
          <Input
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
          />
        </div>

        <Table
          columns={visibleColumns}
          data={filteredProjects}
          keyExtractor={(project) => project.id}
          isLoading={isLoading}
          emptyMessage={t("projectsPage.no_projects_found")}
        />
      </Card>

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
            <Select
              label={t("projectsPage.initial_consultant")}
              value={form.consultantId}
              onChange={(e) => setForm({ ...form, consultantId: e.target.value })}
              options={[
                { value: "", label: t("projectsPage.noConsultantSelected") },
                ...consultants.map((consultant) => ({ value: consultant.id, label: consultant.fullName })),
              ]}
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
                <Badge variant="info">{vocabulary.projectRole(member.roleOnProject)}</Badge>
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
