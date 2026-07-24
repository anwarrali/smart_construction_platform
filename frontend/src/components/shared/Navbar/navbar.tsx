import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Button } from "../../ui/Button";
import { useTheme } from "../../../hooks/useTheme";
import { ROUTES } from "../../../utils/constants";

const navLinks = [
  { to: ROUTES.HOME, label: "Home" },
  { to: "#architecture", label: "Architecture" },
  { to: "#workflow", label: "Workflow" },
  { to: "#mobile-ai", label: "Mobile + AI" },
  { to: "#example", label: "Project Example" },
];

export const Navbar = () => {
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();

  const isActive = (path: string) => {
    if (path.startsWith("#")) return false;
    return location.pathname === path;
  };

  return (
    <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto px-4 h-16 flex items-center justify-between">
        <Link to={ROUTES.HOME} className="text-xl font-bold text-primary">
          Smart Construction
        </Link>

        <nav className="hidden md:flex items-center gap-6">
          {navLinks.map((link) => (
            <a
              key={link.to}
              href={link.to}
              className={`text-sm font-medium transition-colors hover:text-primary ${
                isActive(link.to) ? "text-primary" : "text-muted-foreground"
              }`}
            >
              {link.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={toggleTheme}>
            {theme === "dark" ? "☀️" : "🌙"}
          </Button>

          <div className="hidden md:flex items-center gap-2">
            <Link to={ROUTES.LOGIN}>
              <Button size="sm">
                Sign In
              </Button>
            </Link>
          </div>

          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            onClick={() => setIsMobileOpen(!isMobileOpen)}
          >
            {isMobileOpen ? "✕" : "☰"}
          </Button>
        </div>
      </div>

      {isMobileOpen && (
        <div className="md:hidden border-t bg-background p-4 space-y-3">
          {navLinks.map((link) => (
            <a
              key={link.to}
              href={link.to}
              className="block text-sm font-medium text-muted-foreground hover:text-primary py-2"
              onClick={() => setIsMobileOpen(false)}
            >
              {link.label}
            </a>
          ))}
          <div className="border-t pt-3 space-y-2">
            <Link to={ROUTES.LOGIN} onClick={() => setIsMobileOpen(false)}>
              <Button fullWidth size="sm">
                Sign In
              </Button>
            </Link>
          </div>
        </div>
      )}
    </header>
  );
};
