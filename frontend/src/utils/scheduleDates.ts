import { addDays, differenceInCalendarDays, format, isValid, parseISO, subDays } from "date-fns";

/** Both planned dates are included in a construction task's duration. */
export const inclusiveDurationDays = (startDate: string, endDate: string): number | null => {
  const start = parseISO(startDate);
  const end = parseISO(endDate);
  if (!isValid(start) || !isValid(end)) return null;
  const difference = differenceInCalendarDays(end, start);
  return difference < 0 ? null : difference + 1;
};

/** gantt-task-react draws date intervals with an exclusive end boundary. */
export const inclusiveEndToGanttBoundary = (endDate: string): Date => addDays(parseISO(endDate), 1);

/** Convert the Gantt library's exclusive end boundary back to the API's included end date. */
export const ganttBoundaryToInclusiveEnd = (endBoundary: Date): string =>
  format(subDays(endBoundary, 1), "yyyy-MM-dd");

export const apiDateToLocalDate = (date: string): Date => parseISO(date);
