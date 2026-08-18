import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../../utils/errorMessage";
import {
  Briefcase,
  CheckCircle2,
  Clock,
  FolderKanban,
  Loader2,
  Settings,
  UserCheck,
  UserMinus,
  Users,
} from "lucide-react";
import { Link } from "react-router-dom";
import api from "../../../../services/api";
import { Badge } from "../../../../components/ui/Badge";
import { getRoleLabel } from "../../../../utils/roleMapper";
import { useVocabulary } from "../../../../utils/vocabulary";
import { formatDate } from "../../../../utils/date";
import { ROUTES } from "../../../../utils/constants";
import type { Project } from "../../../../types/project";
import type { UserProfile } from "../../../../types/user";

const normalizeUsers = (response: unknown): UserProfile[] => {
  if (Array.isArray(response)) return response as UserProfile[];
  const data = response as { data?: UserProfile[]; items?: UserProfile[] };
  return data.data || data.items || [];
};

const normalizeProjects = (response: unknown): Project[] => {
  if (Array.isArray(response)) return response as Project[];
  const data = response as { data?: Project[]; items?: Project[] };
  return data.data || data.items || [];
};

const byCreatedDateDesc = <T extends { createdAt?: string }>(items: T[]) =>
  [...items].sort((a, b) => {
    const aTime = a.createdAt ? new Date(a.createdAt).getTime() : 0;
    const bTime = b.createdAt ? new Date(b.createdAt).getTime() : 0;
    return bTime - aTime;
  });

export const AdminDashboard = () => {
  const { t } = useTranslation();
  const vocabulary = useVocabulary();
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchAdminData = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const [usersResponse, projectsResponse] = await Promise.all([
        api.users.list(),
        api.projects.list({ limit: 100 }),
      ]);
      setUsers(normalizeUsers(usersResponse));
      setProjects(normalizeProjects(projectsResponse));
    } catch (err: any) {
      setError(errorMessage(err, "Failed to load administrator dashboard data."));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAdminData();
  }, [fetchAdminData]);

  const summary = useMemo(() => {
    const activeUsers = users.filter((user) => user.status === "active").length;
    const inactiveUsers = users.filter((user) => user.status === "inactive").length;
    const activeProjects = projects.filter((project) => project.status === "active").length;

    return {
      totalUsers: users.length,
      activeUsers,
      inactiveUsers,
      totalProjects: projects.length,
      activeProjects,
    };
  }, [projects, users]);

  const recentUsers = useMemo(() => byCreatedDateDesc(users).slice(0, 5), [users]);
  const recentProjects = useMemo(() => byCreatedDateDesc(projects).slice(0, 5), [projects]);

  const roleDistribution = useMemo(() => {
    const counts = users.reduce<Record<string, number>>((acc, user) => {
      acc[user.role] = (acc[user.role] || 0) + 1;
      return acc;
    }, {});

    return Object.entries(counts)
      .map(([role, count]) => ({
        role,
        count,
        percentage: users.length ? Math.round((count / users.length) * 100) : 0,
      }))
      .sort((a, b) => b.count - a.count);
  }, [users]);

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        Loading administrator dashboard...
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t("adminDash.administrator_dashboard")}</h1>
          <p className="text-muted-foreground mt-1">
            {t("adminDash.company_users_project_registry_access")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to={ROUTES.USERS} className="btn-outline">
            {t("adminDash.manage_users")}
          </Link>
          <Link to={ROUTES.PROJECTS} className="btn-primary">
            {t("adminDash.manage_projects")}
          </Link>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {[
          { label: t("adminDash.totalUsers"), value: summary.totalUsers, icon: Users },
          { label: t("adminDash.activeUsers"), value: summary.activeUsers, icon: UserCheck },
          { label: t("adminDash.inactiveUsers"), value: summary.inactiveUsers, icon: UserMinus },
          { label: t("adminDash.totalProjects"), value: summary.totalProjects, icon: Briefcase },
          { label: t("adminDash.activeProjects"), value: summary.activeProjects, icon: CheckCircle2 },
        ].map(({ label, value, icon: Icon }, index) => (
          <div key={index} className="bg-card border rounded-lg p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground">{label}</span>
              <span className="rounded-md bg-primary/10 p-2 text-primary">
                <Icon size={17} />
              </span>
            </div>
            <p className="mt-3 text-3xl font-bold">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <section className="bg-card border rounded-lg shadow-sm xl:col-span-2">
          <div className="flex items-center justify-between border-b px-5 py-4">
            <div className="flex items-center gap-2">
              <Clock size={18} className="text-primary" />
              <h2 className="text-base font-semibold">{t("adminDash.recently_created_users")}</h2>
            </div>
            <Link to={ROUTES.USERS} className="text-sm font-medium text-primary hover:underline">
              {t("adminDash.view_all")}
            </Link>
          </div>
          <div className="divide-y">
            {recentUsers.map((user) => (
              <div key={user.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                <div>
                  <p className="font-medium">{user.fullName}</p>
                  <p className="text-xs text-muted-foreground">{user.email}</p>
                </div>
                <div className="flex items-center gap-3">
                  <Badge variant="info">{getRoleLabel(user.role)}</Badge>
                  <Badge variant={user.status === "active" ? "success" : "neutral"}>
                    {user.status || "unknown"}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {user.createdAt ? formatDate(user.createdAt) : "-"}
                  </span>
                </div>
              </div>
            ))}
            {recentUsers.length === 0 && (
              <div className="px-5 py-10 text-center text-sm text-muted-foreground">{t("adminDash.no_users_found")}</div>
            )}
          </div>
        </section>

        <section className="bg-card border rounded-lg p-5 shadow-sm">
          <div className="flex items-center gap-2">
            <Users size={18} className="text-primary" />
            <h2 className="text-base font-semibold">{t("adminDash.user_role_distribution")}</h2>
          </div>
          <div className="mt-5 space-y-4">
            {roleDistribution.map(({ role, count, percentage }) => (
              <div key={role} className="space-y-1.5">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">{getRoleLabel(role as any)}</span>
                  <span className="text-muted-foreground">{count}</span>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div className="h-full rounded-full bg-primary" style={{ width: `${percentage}%` }} />
                </div>
              </div>
            ))}
            {roleDistribution.length === 0 && (
              <p className="py-8 text-center text-sm text-muted-foreground">{t("adminDash.no_role_data_available")}</p>
            )}
          </div>
        </section>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <section className="bg-card border rounded-lg shadow-sm xl:col-span-2">
          <div className="flex items-center justify-between border-b px-5 py-4">
            <div className="flex items-center gap-2">
              <FolderKanban size={18} className="text-primary" />
              <h2 className="text-base font-semibold">{t("adminDash.recently_created_projects")}</h2>
            </div>
            <Link to={ROUTES.PROJECTS} className="text-sm font-medium text-primary hover:underline">
              {t("adminDash.view_all")}
            </Link>
          </div>
          <div className="divide-y">
            {recentProjects.map((project) => (
              <div key={project.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                <div>
                  <p className="font-medium">{project.name}</p>
                  <p className="text-xs text-muted-foreground">{project.location || t("adminDash.no_location_set")}</p>
                </div>
                <div className="flex items-center gap-3">
                  <Badge variant={project.status === "active" ? "success" : "info"}>
                    {vocabulary.projectStatus(project.status)}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {project.createdAt ? formatDate(project.createdAt) : "-"}
                  </span>
                </div>
              </div>
            ))}
            {recentProjects.length === 0 && (
              <div className="px-5 py-10 text-center text-sm text-muted-foreground">{t("adminDash.no_projects_found")}</div>
            )}
          </div>
        </section>

        <section className="bg-card border rounded-lg p-5 shadow-sm">
          <div className="flex items-center gap-2">
            <Settings size={18} className="text-primary" />
            <h2 className="text-base font-semibold">{t("adminDash.system_administration")}</h2>
          </div>
          <div className="mt-5 space-y-3">
            <Link className="block rounded-md border px-4 py-3 text-sm font-medium hover:bg-muted/40" to={ROUTES.USERS}>
              {t("adminDash.manage_company_users_and_access")}
            </Link>
            <Link className="block rounded-md border px-4 py-3 text-sm font-medium hover:bg-muted/40" to={ROUTES.PROJECTS}>
              {t("adminDash.manage_project_registry")}
            </Link>
            <Link className="block rounded-md border px-4 py-3 text-sm font-medium hover:bg-muted/40" to={ROUTES.SETTINGS}>
              {t("adminDash.open_system_settings")}
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
};
