import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy } from "lucide-react";

/**
 * A block of text meant to leave this page and land in a configuration file.
 *
 * Always `dir="ltr"`, whatever the interface language: the contents are a URL,
 * a token or JSON, and bidirectional reordering of those is not a
 * presentational difference — it changes what somebody copies by hand when the
 * button is unavailable.
 *
 * The direction is set on the *wrapper*, not on the `<pre>` alone. With it on
 * the `<pre>`, its `padding-inline-end` resolved to the right while the
 * button's `inset-inline-end` resolved against the RTL parent and put the
 * button on the left — so on an Arabic page the button sat squarely on top of
 * the first characters of the token. One direction for the whole positioned
 * box is what keeps the padding and the button on the same side.
 *
 * The copy button reports back rather than firing a toast. A toast for
 * "copied" is noise on a page where copying is the main verb, and the same
 * three seconds of a changed icon says it where the eye already is. A
 * *failure* does need saying, because the clipboard API is refused outright in
 * some browsers and over plain HTTP — hence `onError`, which the caller turns
 * into a message telling the person to select the text instead.
 */

const RESET_AFTER_MS = 2500;

interface CopyableBlockProps {
  value: string;
  /** Shown above the block. */
  label?: ReactNode;
  /** True for JSON and other multi-line content: keeps line breaks. */
  multiline?: boolean;
  onError?: () => void;
  className?: string;
}

export const CopyableBlock = ({
  value,
  label,
  multiline = false,
  onError,
  className = "",
}: CopyableBlockProps) => {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), RESET_AFTER_MS);
    } catch {
      // Refused by the browser (no permission, or an insecure origin). The
      // text is on screen and selectable, so this is recoverable — say so.
      onError?.();
    }
  };

  return (
    <div className={className}>
      {label && (
        <div className="mb-1.5 text-xs font-medium text-muted-foreground">
          {label}
        </div>
      )}
      <div className="relative" dir="ltr">
        <pre
          className={`rounded-md border bg-muted/50 p-3 pe-12 text-xs font-mono text-foreground ${
            multiline ? "overflow-x-auto" : "overflow-x-auto whitespace-nowrap"
          }`}
        >
          {value}
        </pre>
        <button
          type="button"
          onClick={handleCopy}
          aria-label={copied ? t("mcpClients.copied") : t("mcpClients.copy")}
          title={copied ? t("mcpClients.copied") : t("mcpClients.copy")}
          className="absolute end-2 top-2 rounded-md border bg-background p-1.5 text-muted-foreground transition hover:text-foreground"
        >
          {copied ? (
            <Check size={14} className="text-green-600" />
          ) : (
            <Copy size={14} />
          )}
        </button>
      </div>
    </div>
  );
};
