interface LoaderProps {
  size?: "sm" | "md" | "lg";
  variant?: "spinner" | "dots" | "pulse";
  text?: string;
  fullPage?: boolean;
  className?: string;
}

const sizeClasses = {
  sm: "h-4 w-4",
  md: "h-8 w-8",
  lg: "h-12 w-12",
};

export const Loader = ({
  size = "md",
  variant = "spinner",
  text,
  fullPage = false,
  className = "",
}: LoaderProps) => {
  const renderLoader = () => {
    switch (variant) {
      case "spinner":
        return (
          <div
            className={`animate-spin rounded-full border-2 border-current border-t-transparent ${sizeClasses[size]} ${className}`}
            role="status"
            aria-label="Loading"
          />
        );

      case "dots":
        return (
          <div
            className={`flex items-center gap-1 ${className}`}
            role="status"
            aria-label="Loading"
          >
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className={`rounded-full bg-current animate-bounce ${size === "sm" ? "h-1 w-1" : size === "md" ? "h-2 w-2" : "h-3 w-3"}`}
                style={{ animationDelay: `${i * 0.15}s` }}
              />
            ))}
          </div>
        );

      case "pulse":
        return (
          <div
            className={`animate-pulse-soft rounded-full bg-current ${sizeClasses[size]} ${className}`}
            role="status"
            aria-label="Loading"
          />
        );
    }
  };

  const content = (
    <div className="flex flex-col items-center justify-center gap-3">
      {renderLoader()}
      {text && <p className="text-sm text-muted-foreground">{text}</p>}
    </div>
  );

  if (fullPage) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        {content}
      </div>
    );
  }

  return <div className="flex items-center justify-center py-8">{content}</div>;
};
