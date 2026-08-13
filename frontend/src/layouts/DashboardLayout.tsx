import { Outlet } from "react-router-dom";
import { Sidebar } from "../components/shared/Sidebar/Sidebar";
import { Topbar } from "../components/shared/Topbar/Topbar";
import { ProjectWorkspaceProvider } from "../features/projects/context/ProjectWorkspaceContext";
import { Breadcrumbs } from "../components/shared/Breadcrumbs/Breadcrumbs";

export const DashboardLayout = () => {
  return (
    <ProjectWorkspaceProvider>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <div className="flex flex-1 flex-col overflow-hidden">
          <Topbar />
          <main className="flex-1 overflow-y-auto bg-muted/20 p-6">
            <Breadcrumbs />
            <Outlet />
          </main>
        </div>
      </div>
    </ProjectWorkspaceProvider>
  );
};
