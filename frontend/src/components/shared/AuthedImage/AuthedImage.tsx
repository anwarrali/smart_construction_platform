import { useTranslation } from "react-i18next";
import { ImageOff } from "lucide-react";
import { useAuthedFile } from "../../../hooks/useAuthedFile";

/**
 * An `<img>` for a file that requires the caller's credentials.
 *
 * Every evidence photo in the product used to be `<img src={attachment.fileUrl}>`
 * against a public mount. The bytes are now behind an authenticated route, and
 * the browser will not attach a bearer token to an `<img>` request, so the file
 * is fetched with the app's own client and rendered from an object URL.
 *
 * The three states are rendered rather than collapsed into one: a photo that is
 * still loading and a photo the caller may not see look identical if both render
 * as an empty box, and on a photo archive that difference is the whole message.
 */
export const AuthedImage = ({
  url,
  alt,
  className = "",
  containerClassName = "",
}: {
  url: string | null | undefined;
  alt: string;
  className?: string;
  containerClassName?: string;
}) => {
  const { t } = useTranslation();
  const { objectUrl, loading, error } = useAuthedFile(url);

  if (loading) {
    return (
      <div
        className={`flex items-center justify-center bg-muted/40 ${containerClassName || className}`}
        role="status"
        aria-label={t("common.loading", { defaultValue: "Loading" })}
      >
        <span className="h-4 w-4 animate-pulse rounded-full bg-muted-foreground/40" />
      </div>
    );
  }

  if (error || !objectUrl) {
    return (
      <div
        className={`flex flex-col items-center justify-center gap-1 bg-muted/40 text-muted-foreground ${containerClassName || className}`}
      >
        <ImageOff size={16} />
        <span className="px-2 text-center text-[11px] leading-tight">
          {t("files.unavailable", { defaultValue: "Image unavailable" })}
        </span>
      </div>
    );
  }

  return <img src={objectUrl} alt={alt} className={className} loading="lazy" />;
};
