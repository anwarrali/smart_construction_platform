import { ThemeProvider } from "./app/providers/ThemeProvider";
import { QueryProvider } from "./app/providers/QueryProvider";
import { AuthProvider } from "./app/providers/AuthProvider";
import { RealtimeProvider } from "./app/providers/RealtimeProvider";
import { Router } from "./app/router";
import { ToastHost } from "./components/shared/ToastHost";
import { AppErrorBoundary } from "./components/shared/AppErrorBoundary";

const App = () => {
  return (
    <ThemeProvider>
      <QueryProvider>
        <AuthProvider>
          {/* Inside AuthProvider because the stream needs a session, and above
              the router so one connection serves every route rather than being
              torn down and reopened on each navigation. */}
          <RealtimeProvider>
            {/* Scoped to the routed content, not the providers above it, so a
                render crash still leaves toasts and theme/auth state working. */}
            <AppErrorBoundary>
              <Router />
            </AppErrorBoundary>
            <ToastHost />
          </RealtimeProvider>
        </AuthProvider>
      </QueryProvider>
    </ThemeProvider>
  );
};

export default App;
