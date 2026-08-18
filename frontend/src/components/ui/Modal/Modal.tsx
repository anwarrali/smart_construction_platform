import {
  useEffect,
  useId,
  useRef,
  type HTMLAttributes,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { createPortal } from "react-dom";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg" | "xl" | "full";
  closeOnOverlayClick?: boolean;
  showCloseButton?: boolean;
}

const sizeClasses = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-lg",
  xl: "max-w-xl",
  full: "max-w-4xl",
};

export const Modal = ({
  isOpen,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
  closeOnOverlayClick = true,
  showCloseButton = true,
}: ModalProps) => {
  const { t } = useTranslation();
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  // Callers overwhelmingly pass `onClose={() => setOpen(false)}` inline, a
  // new function every render of the parent — and the parent re-renders on
  // every keystroke whenever the open form's field values live in or above
  // that same component (the common pattern here). `onCloseRef` lets the
  // Escape handler always call the *latest* `onClose` without `onClose`
  // itself needing to be a dependency of anything below, which is what used
  // to make this effect re-run on every keystroke — see the effect's own
  // comment for what that re-run actually did to focus.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!isOpen) return undefined;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onCloseRef.current();
        return;
      }

      if (e.key === "Tab" && dialogRef.current) {
        const focusable = Array.from(
          dialogRef.current.querySelectorAll<HTMLElement>(
            'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
          ),
        ).filter((element) => element.getClientRects().length > 0);

        if (!focusable.length) {
          e.preventDefault();
          dialogRef.current.focus();
          return;
        }

        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    // Everything in this effect must run exactly once per open/close cycle —
    // never on a re-render while already open. It used to also depend on
    // `handleKeyDown` (itself a `useCallback([onClose])`), so it re-ran on
    // every keystroke in any field whose value lived in the same component
    // as `onClose`. Each re-run's *cleanup* called `previouslyFocused.focus()`
    // — a stale closure over whatever was focused when that instance of the
    // effect had been set up — which, one keystroke after the modal opened,
    // was still the button that had originally opened it. The net effect on
    // every keystroke: input takes the character correctly (the input DOM
    // node was never destroyed — reconciliation kept it, only focus moved),
    // then focus is yanked out of the dialog entirely back to the trigger
    // button behind it, so the next keystroke lands nowhere useful until the
    // field is clicked again. Depending on `[isOpen]` alone removes the
    // repeated teardown/setup — and therefore the stale refocus — while
    // `onCloseRef` above keeps Escape calling the current `onClose` anyway.
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    const previousPaddingRight = document.body.style.paddingRight;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;

    document.addEventListener("keydown", handleKeyDown);
    document.body.style.overflow = "hidden";
    if (scrollbarWidth > 0) {
      document.body.style.paddingRight = `${scrollbarWidth}px`;
    }

    window.requestAnimationFrame(() => {
      const firstField = dialogRef.current?.querySelector<HTMLElement>(
        '.dialog-body input:not([disabled]), .dialog-body select:not([disabled]), .dialog-body textarea:not([disabled]), .dialog-body button:not([disabled])',
      );
      const firstAction = dialogRef.current?.querySelector<HTMLElement>(
        'input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled])',
      );
      (firstField || firstAction || dialogRef.current)?.focus();
    });

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      document.body.style.paddingRight = previousPaddingRight;
      previouslyFocused?.focus();
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return createPortal(
    <div
      className="dialog-overlay"
      onClick={closeOnOverlayClick ? onClose : undefined}
    >
      <div
        ref={dialogRef}
        className={`dialog-content ${sizeClasses[size]}`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        tabIndex={-1}
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-describedby={description ? descriptionId : undefined}
      >
        {(title || showCloseButton) && (
          <div className="dialog-header">
            {title && (
              <h2 id={titleId} className="min-w-0 pr-3 text-lg font-semibold sm:text-xl">
                {title}
              </h2>
            )}
            {showCloseButton && (
              <button
                onClick={onClose}
                type="button"
                className="btn btn-ghost btn-icon ml-auto shrink-0"
                aria-label={t("modal.close")}
              >
                ✕
              </button>
            )}
          </div>
        )}

        <div className="dialog-body">
          {description && (
            <p id={descriptionId} className="mb-4 text-sm text-muted-foreground">
              {description}
            </p>
          )}
          {children}
        </div>

        {footer && (
          <div className="dialog-footer">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
};

interface ModalActionsProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export const ModalActions = ({ children, className = "", ...props }: ModalActionsProps) => (
  <div className={`modal-actions ${className}`} {...props}>
    {children}
  </div>
);
