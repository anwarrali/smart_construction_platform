import { Toaster } from "react-hot-toast";

import { useTheme } from "../../hooks/useTheme";

/**
 * Application-wide host for `react-hot-toast`.
 *
 * Every feature page already called `toast.success` / `toast.error`, but no
 * `<Toaster />` was ever mounted, so none of those messages reached the screen.
 * That is why actions such as scheduling a site visit looked like they did
 * nothing: the request ran, and both the success and the failure were silent.
 *
 * Positioning follows the document direction so the toasts stay on the reading
 * side in Arabic, and the colours are taken from the theme tokens so the host
 * works in light and dark without a second definition.
 */
export const ToastHost = () => {
  const { isRTL } = useTheme();

  return (
    <Toaster
      position={isRTL ? "top-left" : "top-right"}
      gutter={10}
      toastOptions={{
        duration: 4000,
        // Errors are the ones users need time to read and act on.
        error: { duration: 6000 },
        style: {
          background: "hsl(var(--card))",
          color: "hsl(var(--card-foreground))",
          border: "1px solid hsl(var(--border))",
          borderRadius: "0.75rem",
          padding: "0.75rem 1rem",
          fontSize: "0.875rem",
          maxWidth: "min(28rem, calc(100vw - 2rem))",
          boxShadow: "0 10px 30px -12px rgb(0 0 0 / 0.35)",
        },
      }}
    />
  );
};
