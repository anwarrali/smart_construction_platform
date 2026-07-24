import {
  useState,
  useRef,
  useCallback,
  useEffect,
  type KeyboardEvent,
} from "react";
import { useNavigate } from "react-router-dom";
import { useDebounce } from "../../../hooks/useDebounce";

interface SearchResult {
  id: string;
  title: string;
  type: "project" | "task" | "document" | "report";
  url: string;
}

interface SearchBarProps {
  placeholder?: string;
  className?: string;
  onSearch?: (query: string) => Promise<SearchResult[]>;
}

export const SearchBar = ({
  placeholder = "Search projects, tasks, documents...",
  className = "",
  onSearch,
}: SearchBarProps) => {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const debouncedQuery = useDebounce(query, 300);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const prevQueryRef = useRef("");

  const performSearch = useCallback(
    async (searchQuery: string) => {
      if (!searchQuery.trim() || !onSearch) {
        setResults([]);
        setIsOpen(false);
        return;
      }

      setIsLoading(true);
      setSelectedIndex(-1);
      const data = await onSearch(searchQuery);
      setResults(data);
      setIsLoading(false);
      setIsOpen(true);
      prevQueryRef.current = searchQuery;
    },
    [onSearch],
  );

  useEffect(() => {
    if (debouncedQuery !== prevQueryRef.current) {
      performSearch(debouncedQuery);
    }
  }, [debouncedQuery, performSearch]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.min(prev + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.max(prev - 1, -1));
    } else if (
      e.key === "Enter" &&
      selectedIndex >= 0 &&
      results[selectedIndex]
    ) {
      navigate(results[selectedIndex].url);
      setIsOpen(false);
      setQuery("");
    } else if (e.key === "Escape") {
      setIsOpen(false);
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case "project":
        return "📁";
      case "task":
        return "✅";
      case "document":
        return "📄";
      case "report":
        return "📝";
      default:
        return "🔍";
    }
  };

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <div className="relative">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">
          🔍
        </span>
        <input
          ref={inputRef}
          type="text"
          className="input pl-10 pr-4"
          placeholder={placeholder}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSelectedIndex(-1);
          }}
          onFocus={() => {
            if (results.length > 0) {
              setIsOpen(true);
            }
          }}
          onKeyDown={handleKeyDown}
        />
        {isLoading && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm animate-spin">
            ⏳
          </span>
        )}
      </div>

      {isOpen && results.length > 0 && (
        <div className="absolute top-full mt-1 w-full rounded-md border bg-popover shadow-lg z-50">
          <div className="p-1">
            {results.map((result, index) => (
              <button
                key={result.id}
                className={`w-full text-left px-3 py-2 rounded-sm text-sm flex items-center gap-3 transition-colors ${
                  index === selectedIndex
                    ? "bg-accent text-accent-foreground"
                    : "hover:bg-accent hover:text-accent-foreground"
                }`}
                onClick={() => {
                  navigate(result.url);
                  setIsOpen(false);
                  setQuery("");
                  setResults([]);
                }}
              >
                <span>{getTypeIcon(result.type)}</span>
                <span className="flex-1 truncate">{result.title}</span>
                <span className="text-xs text-muted-foreground">
                  {result.type}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {isOpen && query && !isLoading && results.length === 0 && (
        <div className="absolute top-full mt-1 w-full rounded-md border bg-popover shadow-lg z-50 p-4 text-center text-sm text-muted-foreground">
          No results found for "{query}"
        </div>
      )}
    </div>
  );
};
