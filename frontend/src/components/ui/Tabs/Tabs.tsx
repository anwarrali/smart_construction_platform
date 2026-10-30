import { useRef, type KeyboardEvent, type ReactNode } from "react";

export interface TabItem<T extends string> {
  value: T;
  label: ReactNode;
  /** A count shown beside the label, e.g. items awaiting action. */
  count?: number;
}

interface TabsProps<T extends string> {
  items: TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  /** Accessible name of the tab strip. */
  label: string;
  className?: string;
}

/**
 * A ruled tab strip for switching views within one page. The selected tab is
 * marked by a rule beneath it, not a filled pill.
 *
 * Arrow keys move between tabs (mirrored in right-to-left layouts), Home and
 * End jump to the ends — the standard tablist pattern.
 */
export const Tabs = <T extends string>({ items, value, onChange, label, className = "" }: TabsProps<T>) => {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const current = items.findIndex((item) => item.value === value);
    if (current < 0) return;
    const rtl = getComputedStyle(event.currentTarget).direction === "rtl";
    const forward = rtl ? "ArrowLeft" : "ArrowRight";
    const backward = rtl ? "ArrowRight" : "ArrowLeft";
    const next =
      event.key === forward ? (current + 1) % items.length
        : event.key === backward ? (current - 1 + items.length) % items.length
          : event.key === "Home" ? 0
            : event.key === "End" ? items.length - 1
              : -1;
    if (next < 0) return;
    event.preventDefault();
    onChange(items[next].value);
    refs.current[next]?.focus();
  };

  return (
    <div role="tablist" aria-label={label} className={`tab-bar ${className}`} onKeyDown={onKeyDown}>
      {items.map((item, index) => {
        const selected = item.value === value;
        return (
          <button
            key={item.value}
            ref={(node) => { refs.current[index] = node; }}
            type="button"
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.value)}
            className={`tab-link cursor-pointer border-none bg-transparent${selected ? " tab-link-active" : ""}`}
          >
            {item.label}
            {item.count !== undefined && (
              <span className={`text-measured min-w-5 px-1 text-center text-[11px] ${selected ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}>
                {item.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
};
