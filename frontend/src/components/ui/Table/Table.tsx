import type { ReactNode } from "react";
import { Inbox } from "lucide-react";

export interface Column<T> {
  key: string;
  header: string;
  render?: (item: T) => ReactNode;
  sortable?: boolean;
  className?: string;
}

interface TableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (item: T) => string;
  isLoading?: boolean;
  emptyMessage?: string;
  onRowClick?: (item: T) => void;
  className?: string;
}

export const Table = <T,>({
  columns,
  data = [],
  keyExtractor,
  isLoading = false,
  emptyMessage = "No data found",
  onRowClick,
  className = "",
}: TableProps<T>) => {
  if (isLoading) {
    return (
      <div className="table-container">
        <div className="divide-rule" role="status" aria-busy="true">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="flex gap-4 px-3 py-2.5">
              <div className="skeleton h-4 w-1/3" />
              <div className="skeleton h-4 flex-1" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="table-container">
        <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
          <Inbox size={22} strokeWidth={1.5} className="empty-state-icon" aria-hidden />
          <p className="empty-state-title">{emptyMessage}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`table-container ${className}`}>
      <div className="table-responsive">
        <table className="schedule-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  scope="col"
                  className={col.className || ""}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((item) => (
              <tr
                key={keyExtractor(item)}
                className={onRowClick ? "cursor-pointer" : ""}
                onClick={() => onRowClick?.(item)}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={col.className || ""}
                  >
                    {col.render
                      ? col.render(item)
                      : String(
                          (item as Record<string, unknown>)[col.key] ?? "",
                        )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
