export const classNames = (
  ...classes: (string | boolean | undefined | null)[]
): string => {
  return classes.filter(Boolean).join(" ");
};

export const generateId = (): string => {
  return crypto.randomUUID();
};

export const truncateText = (text: string, maxLength: number): string => {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...`;
};

export const capitalize = (text: string): string => {
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
};

export const formatCurrency = (
  amount: number,
  locale: "en" | "ar" = "en",
): string => {
  const currencyLocale = locale === "ar" ? "ar-SA" : "en-US";
  return new Intl.NumberFormat(currencyLocale, {
    style: "currency",
    currency: "ILS",
    maximumFractionDigits: 0,
  }).format(amount);
};

export const formatPercentage = (
  value: number,
  decimals: number = 1,
): string => {
  return `${value.toFixed(decimals)}%`;
};

export const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.floor(Math.log(bytes) / Math.log(1024));
  const size = (bytes / Math.pow(1024, index)).toFixed(index === 0 ? 0 : 1);
  return `${size} ${units[index]}`;
};

export const getFileExtension = (fileName: string): string => {
  return fileName.split(".").pop()?.toLowerCase() || "";
};

export const isImageFile = (fileName: string): boolean => {
  const ext = getFileExtension(fileName);
  return ["jpg", "jpeg", "png", "gif", "webp", "svg", "bmp"].includes(ext);
};

export const isPDFFile = (fileName: string): boolean => {
  return getFileExtension(fileName) === "pdf";
};

export const getInitials = (fullName: string): string => {
  return fullName
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
};

export const getAvatarColor = (name: string): string => {
  const colors = [
    "#2563eb",
    "#dc2626",
    "#16a34a",
    "#f59e0b",
    "#7c3aed",
    "#0891b2",
    "#ea580c",
    "#4f46e5",
    "#059669",
    "#db2777",
  ];
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
};

export const formatAssigneeRole = (role: string, discipline?: string): string => {
  const titleCase = (value: string) => value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
  const disciplineLabel = discipline ? titleCase(discipline) : "";
  if (role === "engineer") return `${disciplineLabel ? `${disciplineLabel} ` : ""}Engineer`;
  if (role === "consultant") return `${disciplineLabel ? `${disciplineLabel} ` : ""}Consultant`;
  return titleCase(role);
};

export const debounce = <T extends (...args: unknown[]) => unknown>(
  fn: T,
  delay: number,
): ((...args: Parameters<T>) => void) => {
  let timeoutId: ReturnType<typeof setTimeout>;
  return (...args: Parameters<T>) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), delay);
  };
};

export const groupBy = <T>(array: T[], key: keyof T): Record<string, T[]> => {
  return array.reduce(
    (acc, item) => {
      const groupKey = String(item[key]);
      if (!acc[groupKey]) acc[groupKey] = [];
      acc[groupKey].push(item);
      return acc;
    },
    {} as Record<string, T[]>,
  );
};

export const sortByDate = <T>(
  array: T[],
  key: keyof T,
  direction: "asc" | "desc" = "desc",
): T[] => {
  return [...array].sort((a, b) => {
    const dateA = new Date(a[key] as string).getTime();
    const dateB = new Date(b[key] as string).getTime();
    return direction === "asc" ? dateA - dateB : dateB - dateA;
  });
};

export const parseQueryParams = (params: object): string => {
  const searchParams = new URLSearchParams();
  const record = params as Record<string, unknown>;
  Object.entries(record).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      const queryKey = key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
      searchParams.append(queryKey, String(value));
    }
  });
  return searchParams.toString();
};

export const clamp = (value: number, min: number, max: number): number => {
  return Math.min(Math.max(value, min), max);
};

export const getStatusColor = (
  status: string,
  colors: Record<string, string>,
): string => {
  return colors[status] || colors["pending"] || "#6b7280";
};

export const toSnakeCase = (
  obj: Record<string, unknown>,
): Record<string, unknown> => {
  if (obj instanceof FormData) return obj;
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    const snakeKey = key.replace(
      /[A-Z]/g,
      (letter) => `_${letter.toLowerCase()}`,
    );
    result[snakeKey] = value;
  }
  return result;
};

export const toCamelCase = <T = unknown>(obj: Record<string, unknown>): T => {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    const camelKey = key.replace(/_([a-z])/g, (_, letter) =>
      letter.toUpperCase(),
    );
    result[camelKey] = value;
  }
  return result as T;
};
