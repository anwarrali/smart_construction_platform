import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import organizationService from "../features/admin/services/organization.service";
import { useVocabulary } from "../utils/vocabulary";

export interface DisciplineOption {
  value: string;
  label: string;
}

/* What the form can still offer if the catalogue cannot be read: the four
   disciplines every deployment has always had. The server validates either way. */
const FALLBACK_CODES = ["architectural", "civil", "electrical", "mechanical"];

/**
 * The disciplines a task (or a filter) can be filed under, from the office's
 * own catalogue — the list managed under Roles & disciplines and the one the
 * task API validates against. Create and edit share this, so they can never
 * offer different lists again.
 *
 * `include` keeps a value that is no longer in the catalogue selectable, so a
 * task saved under a since-retired discipline still shows what it was saved as.
 */
export const useDisciplineOptions = (include?: string | null) => {
  const { i18n } = useTranslation();
  const vocabulary = useVocabulary();
  const arabic = (i18n.resolvedLanguage || i18n.language || "en").startsWith("ar");
  const query = useQuery({
    queryKey: ["organization", "disciplines"],
    queryFn: organizationService.disciplines,
    staleTime: 10 * 60 * 1000,
  });

  const options: DisciplineOption[] = query.data
    ? query.data
      .filter((item) => item.isActive)
      .sort((a, b) => a.rank - b.rank || a.nameEn.localeCompare(b.nameEn))
      .map((item) => ({ value: item.code, label: (arabic && item.nameAr) || item.nameEn }))
    : FALLBACK_CODES.map((code) => ({ value: code, label: vocabulary.discipline(code) }));

  if (include && !options.some((option) => option.value === include)) {
    options.push({ value: include, label: vocabulary.discipline(include) });
  }
  return { options, isLoading: query.isLoading, isFallback: !query.data };
};

export default useDisciplineOptions;
