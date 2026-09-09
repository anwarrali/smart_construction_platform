import { useEffect, useState } from "react";
import axiosInstance from "../services/axios";

/**
 * Fetching a protected file into something the browser can display or save.
 *
 * Uploaded files used to be served from an unauthenticated `/uploads` mount, so
 * a component could put the stored URL straight into `<img src>` and it worked.
 * The bytes now sit behind a route that requires the caller's bearer token, and
 * `<img src>` cannot send one — the browser issues that request itself, with no
 * headers of our choosing.
 *
 * So the file is fetched through the same axios instance every other request
 * uses (which attaches the token and refreshes it on expiry), and the response
 * blob is turned into an object URL the element can point at. That keeps one
 * credential path for the whole app rather than introducing a second, weaker one
 * — a signed-URL scheme would be a second way to reach a file, and the reason
 * this endpoint exists at all is that a second way to reach a file is what went
 * wrong before.
 */

const fetchBlob = async (url: string): Promise<Blob> => {
  const response = await axiosInstance.get<Blob>(url, { responseType: "blob" });
  return response.data;
};

export interface AuthedFile {
  /** Object URL for `<img src>` / `<a href>`, or null until it resolves. */
  objectUrl: string | null;
  loading: boolean;
  error: boolean;
}

/**
 * Load a protected file and expose it as an object URL.
 *
 * Pass a null `url` to skip the fetch entirely — a component that renders a
 * placeholder when there is no file should not have to branch around the hook.
 */
export const useAuthedFile = (url: string | null | undefined): AuthedFile => {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(url));
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!url) {
      setObjectUrl(null);
      setLoading(false);
      setError(false);
      return;
    }

    // `cancelled` rather than an AbortController on its own: the revoke below
    // must still run for a request that completed just as the component
    // unmounted, or the blob stays in memory for the life of the document.
    let cancelled = false;
    let created: string | null = null;

    setLoading(true);
    setError(false);

    fetchBlob(url)
      .then((blob) => {
        if (cancelled) return;
        created = URL.createObjectURL(blob);
        setObjectUrl(created);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [url]);

  return { objectUrl, loading, error };
};

/**
 * Download a protected file to disk, under its real name.
 *
 * Used by the link affordances that previously pointed at the public URL. The
 * object URL is revoked immediately after the click: it only has to survive
 * long enough for the browser to start the save.
 */
export const downloadAuthedFile = async (
  url: string,
  filename: string,
): Promise<void> => {
  const blob = await fetchBlob(url);
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
};

/**
 * Open a protected file in a new tab, optionally at a fragment.
 *
 * Used by the RAG citation jump, which appends `#page=N` — browsers honour that
 * on a blob URL exactly as they do on an http one, which is what keeps a
 * citation checkable in one click now that the file is no longer public.
 *
 * The object URL is revoked on a timer rather than immediately: the new tab has
 * to finish reading it first, and there is no event that tells us when it has.
 * A minute is far longer than the load needs and still bounds the leak.
 */
export const openAuthedFile = async (
  url: string,
  fragment = "",
): Promise<void> => {
  const blob = await fetchBlob(url);
  const objectUrl = URL.createObjectURL(blob);
  window.open(`${objectUrl}${fragment}`, "_blank", "noopener");
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
};
