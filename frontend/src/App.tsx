import { ThemeProvider } from "./app/providers/ThemeProvider";
import { QueryProvider } from "./app/providers/QueryProvider";
import { AuthProvider } from "./app/providers/AuthProvider";
import { Router } from "./app/router";
import { ToastHost } from "./components/shared/ToastHost";
import { AppErrorBoundary } from "./components/shared/AppErrorBoundary";

const App = () => {
  return (
    <ThemeProvider>
      <QueryProvider>
        <AuthProvider>
          {/* Scoped to the routed content, not the providers above it, so a
              render crash still leaves toasts and theme/auth state working. */}
          <AppErrorBoundary>
            <Router />
          </AppErrorBoundary>
          <ToastHost />
        </AuthProvider>
      </QueryProvider>
    </ThemeProvider>
  );
};

export default App;
