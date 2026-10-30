import { create } from "zustand";

/**
 * How this person has arranged the shell: whether the navigation rail is
 * narrowed to icons, and which navigation groups they have folded away.
 *
 * Purely a per-browser convenience, so storage failures (private windows,
 * blocked site data) fall back to the defaults instead of breaking the shell.
 */

const RAIL_KEY = "structiq.rail.collapsed";
const GROUPS_KEY = "structiq.nav.folded";

const read = <T,>(key: string, fallback: T): T => {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
};

const write = (key: string, value: unknown) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* A preference that cannot be saved still applies for this visit. */
  }
};

interface LayoutState {
  railCollapsed: boolean;
  /** Group ids the person has folded. */
  foldedGroups: string[];
  toggleRail: () => void;
  toggleGroup: (id: string) => void;
}

export const useLayoutStore = create<LayoutState>((set, get) => ({
  railCollapsed: read<boolean>(RAIL_KEY, false),
  foldedGroups: read<string[]>(GROUPS_KEY, []),
  toggleRail: () => {
    const railCollapsed = !get().railCollapsed;
    write(RAIL_KEY, railCollapsed);
    set({ railCollapsed });
  },
  toggleGroup: (id) => {
    const folded = get().foldedGroups;
    const foldedGroups = folded.includes(id) ? folded.filter((g) => g !== id) : [...folded, id];
    write(GROUPS_KEY, foldedGroups);
    set({ foldedGroups });
  },
}));
