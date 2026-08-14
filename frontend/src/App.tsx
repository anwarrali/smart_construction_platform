import { ThemeProvider } from "./app/providers/ThemeProvider";
import { QueryProvider } from "./app/providers/QueryProvider";
import { AuthProvider } from "./app/providers/AuthProvider";
import { Router } from "./app/router";
import { ToastHost } from "./components/shared/ToastHost";

const App = () => {
  return (
    <ThemeProvider>
      <QueryProvider>
        <AuthProvider>
          <Router />
          <ToastHost />
        </AuthProvider>
      </QueryProvider>
    </ThemeProvider>
  );
};

export default App;
