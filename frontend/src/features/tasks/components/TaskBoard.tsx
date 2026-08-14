import { TaskCard } from "./TaskCard";
import { Loader } from "../../../components/ui/Loader";
import type { Task, TaskStatus } from "../../../types/task";
import { ChevronLeft, ChevronRight, MoveHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useVocabulary } from "../../../utils/vocabulary";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

interface TaskBoardProps {
  tasks: Task[];
  isLoading: boolean;
  onStatusChange?: (taskId: string, status: TaskStatus) => void;
  onEdit?: (task: Task) => void;
  onDelete?: (task: Task) => void;
}

const COLUMNS: { status: TaskStatus; label: string; color: string }[] = [
  { status: "backlog", label: "Backlog", color: "border-t-gray-400" },
  { status: "todo", label: "To Do", color: "border-t-blue-400" },
  { status: "in_progress", label: "In Progress", color: "border-t-blue-600" },
  { status: "under_review", label: "Review", color: "border-t-yellow-500" },
  { status: "rework_required", label: "Rework", color: "border-t-orange-500" },
  { status: "done", label: "Done", color: "border-t-green-500" },
  { status: "blocked", label: "Blocked", color: "border-t-red-500" },
];

const COLUMN_STEP = 336; // one column (w-80) plus the gap

export const TaskBoard = ({ tasks, isLoading, onEdit, onDelete }: TaskBoardProps) => {
  const { t } = useTranslation();
  const vocabulary = useVocabulary();
  const boardRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ startX: number; startScroll: number } | null>(null);
  const [metrics, setMetrics] = useState({ left: 0, width: 1, scrollWidth: 1 });

  const readMetrics = useCallback(() => {
    const board = boardRef.current;
    if (!board) return;
    setMetrics({ left: board.scrollLeft, width: board.clientWidth, scrollWidth: board.scrollWidth });
  }, []);

  // The board's own scrollbar sits below the fold on a laptop screen, so the
  // sticky bar above mirrors it and stays reachable at any page position.
  useLayoutEffect(() => {
    readMetrics();
    const board = boardRef.current;
    if (!board) return;
    const observer = new ResizeObserver(readMetrics);
    observer.observe(board);
    Array.from(board.children).forEach((child) => observer.observe(child));
    return () => observer.disconnect();
  }, [readMetrics, tasks]);

  useEffect(() => {
    const stop = () => { dragRef.current = null; };
    const drag = (event: PointerEvent) => {
      const state = dragRef.current;
      const board = boardRef.current;
      const track = trackRef.current;
      if (!state || !board || !track) return;
      const ratio = board.scrollWidth / Math.max(1, track.clientWidth);
      board.scrollLeft = state.startScroll + (event.clientX - state.startX) * ratio;
    };
    window.addEventListener("pointermove", drag);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    return () => {
      window.removeEventListener("pointermove", drag);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
    };
  }, []);

  if (isLoading) return <Loader text={t("common.loading")} />;

  const move = (direction: number) => boardRef.current?.scrollBy({ left: direction * COLUMN_STEP, behavior: "smooth" });
  const maxScroll = Math.max(0, metrics.scrollWidth - metrics.width);
  const atStart = metrics.left <= 1;
  const atEnd = metrics.left >= maxScroll - 1;
  const overflowing = maxScroll > 1;
  const thumbWidth = Math.max(12, (metrics.width / metrics.scrollWidth) * 100);
  const thumbLeft = maxScroll ? (metrics.left / maxScroll) * (100 - thumbWidth) : 0;
  const visibleColumn = Math.min(COLUMNS.length, Math.round(metrics.left / COLUMN_STEP) + 1);

  const arrowClass = (disabled: boolean) =>
    `rounded-md border p-1.5 transition-colors ${disabled ? "cursor-not-allowed opacity-40" : "hover:bg-muted"}`;

  return (
    <div className="relative">
      <div className="sticky top-0 z-10 mb-3 space-y-2 rounded-lg border bg-card/95 px-3 py-2 shadow-sm backdrop-blur">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <MoveHorizontal size={15} />
            <span className="hidden sm:inline">{t("task.boardHint")}</span>
            <span className="sm:hidden">{t("task.boardHintShort")}</span>
          </div>
          <div className="flex items-center gap-2">
            {overflowing && <span className="hidden text-xs tabular-nums text-muted-foreground md:inline">{t("task.stageOf", { current: visibleColumn, total: COLUMNS.length })}</span>}
            <div className="flex gap-1">
              <button type="button" aria-label={t("task.scrollLeft")} disabled={atStart} onClick={() => move(-1)} className={arrowClass(atStart)}><ChevronLeft size={17} className="rtl-flip" /></button>
              <button type="button" aria-label={t("task.scrollRight")} disabled={atEnd} onClick={() => move(1)} className={arrowClass(atEnd)}><ChevronRight size={17} className="rtl-flip" /></button>
            </div>
          </div>
        </div>
        {overflowing && (
          <div
            ref={trackRef}
            className="relative h-2 cursor-pointer rounded-full bg-muted"
            role="scrollbar"
            aria-controls="task-board-columns"
            aria-orientation="horizontal"
            aria-valuenow={Math.round(maxScroll ? (metrics.left / maxScroll) * 100 : 0)}
            onPointerDown={(event) => {
              const board = boardRef.current;
              const track = trackRef.current;
              if (!board || !track) return;
              const bounds = track.getBoundingClientRect();
              const thumbStart = bounds.left + (thumbLeft / 100) * bounds.width;
              const thumbEnd = thumbStart + (thumbWidth / 100) * bounds.width;
              // Clicking the empty track jumps there; grabbing the thumb pans.
              if (event.clientX < thumbStart || event.clientX > thumbEnd) {
                const target = ((event.clientX - bounds.left) / bounds.width) * board.scrollWidth - board.clientWidth / 2;
                board.scrollTo({ left: Math.max(0, target), behavior: "smooth" });
                return;
              }
              dragRef.current = { startX: event.clientX, startScroll: board.scrollLeft };
            }}
          >
            <div
              className="absolute top-0 h-2 rounded-full bg-primary/60 transition-[left] duration-75"
              style={{ width: `${thumbWidth}%`, left: `${thumbLeft}%` }}
            />
          </div>
        )}
      </div>
      <div
        id="task-board-columns"
        ref={boardRef}
        onScroll={readMetrics}
        onWheel={(event) => {
          if (event.shiftKey && boardRef.current) {
            event.preventDefault();
            boardRef.current.scrollLeft += event.deltaY;
          }
        }}
        className="flex gap-4 overflow-x-auto pb-4 snap-x scroll-smooth"
      >
        {COLUMNS.map((col) => {
          const columnTasks = (tasks || []).filter((t) => t.status === col.status);
          return (
            <div
              key={vocabulary.taskStatus(col.status)}
              className={`flex-none w-80 snap-start bg-muted/30 rounded-lg border-t-2 ${col.color} min-h-[200px]`}
            >
              <div className="p-3 font-medium text-sm flex items-center justify-between">
                <span>{t("task.status." + col.status, { defaultValue: col.label })}</span>
                <span className="text-muted-foreground">
                  {columnTasks.length}
                </span>
              </div>
              <div className="p-2 space-y-2">
                {columnTasks.map((task) => (
                  <TaskCard key={task.id} task={task} onEdit={onEdit} onDelete={onDelete} />
                ))}
                {columnTasks.length === 0 && (
                  <p className="text-xs text-muted-foreground text-center py-8">
                    {t("empty.noTasks")}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
