import { Outlet } from "react-router-dom";
import { Navbar } from "../components/shared/Navbar";

export const PublicLayout = () => {
  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main>
        <Outlet />
      </main>
      <footer className="border-t py-8">
        <div className="container mx-auto px-4 text-center text-sm text-muted-foreground">
          &copy; {new Date().getFullYear()} Smart Construction Platform. All
          rights reserved.
        </div>
      </footer>
    </div>
  );
};
