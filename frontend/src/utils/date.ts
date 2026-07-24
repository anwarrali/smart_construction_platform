import {
  format,
  formatDistanceToNow,
  parseISO,
  isValid,
  differenceInDays,
  isPast,
  isToday,
  isTomorrow,
  type Locale,
} from "date-fns";
import { ar } from "date-fns/locale";
import {
  DATE_FORMAT,
  DATE_TIME_FORMAT,
  DISPLAY_DATE_FORMAT,
  DISPLAY_DATE_TIME_FORMAT,
} from "./constants";
import { inclusiveDurationDays } from "./scheduleDates";

export const formatDate = (
  date: string | Date,
  formatStr: string = DISPLAY_DATE_FORMAT,
): string => {
  const parsedDate = typeof date === "string" ? parseISO(date) : date;
  if (!isValid(parsedDate)) return "—";
  return format(parsedDate, formatStr);
};

export const formatDateTime = (date: string | Date): string => {
  const parsedDate = typeof date === "string" ? parseISO(date) : date;
  if (!isValid(parsedDate)) return "—";
  return format(parsedDate, DISPLAY_DATE_TIME_FORMAT);
};

export const formatAPIDate = (date: Date): string => {
  return format(date, DATE_FORMAT);
};

export const formatAPIDateTime = (date: Date): string => {
  return format(date, DATE_TIME_FORMAT);
};

export const timeAgo = (
  date: string | Date,
  locale: "en" | "ar" = "en",
): string => {
  const parsedDate = typeof date === "string" ? parseISO(date) : date;
  if (!isValid(parsedDate)) return "—";
  return formatDistanceToNow(parsedDate, {
    addSuffix: true,
    locale: locale === "ar" ? ar : undefined,
  });
};

export const getDaysRemaining = (endDate: string): number => {
  const parsed = parseISO(endDate);
  if (!isValid(parsed)) return 0;
  return differenceInDays(parsed, new Date());
};

export const isOverdue = (date: string): boolean => {
  const parsed = parseISO(date);
  if (!isValid(parsed)) return false;
  return isPast(parsed) && !isToday(parsed);
};

export const isDueToday = (date: string): boolean => {
  const parsed = parseISO(date);
  if (!isValid(parsed)) return false;
  return isToday(parsed);
};

export const isDueTomorrow = (date: string): boolean => {
  const parsed = parseISO(date);
  if (!isValid(parsed)) return false;
  return isTomorrow(parsed);
};

export const getProjectDurationDays = (
  startDate: string,
  endDate: string,
): number => {
  return inclusiveDurationDays(startDate, endDate) ?? 0;
};

export const getDelayStatus = (
  expectedEndDate: string,
  actualEndDate?: string,
  completionPercentage?: number,
): "on_track" | "at_risk" | "delayed" | "completed" => {
  if (actualEndDate) return "completed";

  const expected = parseISO(expectedEndDate);
  if (!isValid(expected)) return "on_track";

  const daysRemaining = differenceInDays(expected, new Date());

  if (daysRemaining < 0) return "delayed";
  if (
    completionPercentage !== undefined &&
    completionPercentage < 50 &&
    daysRemaining < 7
  )
    return "at_risk";
  if (daysRemaining < 3) return "at_risk";
  return "on_track";
};

export const DATE_FNS_LOCALES: Record<string, Locale> = {
  ar,
};
