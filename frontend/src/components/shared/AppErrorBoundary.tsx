import { Component, type ErrorInfo, type ReactNode } from "react";
import { withTranslation, type WithTranslation } from "react-i18next";
import { AlertTriangle, RefreshCw } from "lucide-react";

import { Button } from "../ui/Button";
import { Card } from "../ui/Card";

/**
 * The last line of defense against a blank white screen.
 *
 * Async request failures already funnel through `errorMessage` into a toast;
 * this catches the other kind of failure — an unexpected render-time crash
 * anywhere in the routed app — and shows a translated, actionable message
 * instead of an empty page with nothing in it for the user to act on.
 *
 * Mirrors `IFCTabErrorBoundary` (`features/ifc/components/IFCShared.tsx`),
 * scoped to the whole router instead of one workspace tab.
 */
interface Props extends WithTranslation {
  children: ReactNode;
}
interface State {
  error?: Error;
}

class AppErrorBoundaryBase extends Component<Props, State> {
  state: State = {};

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[App] unhandled render failure", error, info.componentStack);
  }

  private reload = () => {
    window.location.reload();
  };

  render() {
    if (!this.state.error) return this.props.children;
    const { t } = this.props;
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <Card className="max-w-md border-red-200">
          <div className="py-8 text-center">
            <AlertTriangle className="mx-auto mb-3 text-red-500" />
            <h1 className="font-semibold">{t("errors.generic")}</h1>
            <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
              {t("errors.appCrashedHint")}
            </p>
            <Button className="mt-4" variant="outline" onClick={this.reload}>
              <RefreshCw size={15} /> {t("common.reload")}
            </Button>
          </div>
        </Card>
      </div>
    );
  }
}

export const AppErrorBoundary = withTranslation()(AppErrorBoundaryBase);
