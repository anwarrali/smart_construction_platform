import { Link, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CalendarRange, ClipboardCheck, HardHat, Users } from "lucide-react";
import { ROUTES } from "../utils/constants";
import { LanguageSwitcher } from "../components/shared/LanguageSwitcher";

const capabilities = [
  { icon: CalendarRange, titleKey: "authAside.planTitle", textKey: "authAside.planText" },
  { icon: ClipboardCheck, titleKey: "authAside.executeTitle", textKey: "authAside.executeText" },
  { icon: Users, titleKey: "authAside.rolesTitle", textKey: "authAside.rolesText" },
];

export const AuthLayout = () => {
  const { t } = useTranslation();
  return (
    <div className="min-h-screen bg-slate-950 md:grid md:grid-cols-[minmax(420px,0.9fr)_minmax(520px,1.1fr)]">
      <div className="flex min-h-screen flex-col bg-background px-6 py-8 sm:px-12 lg:px-20">
        {/* The switcher belongs here too: without it an Arabic speaker cannot
            change the language until after reading an English sign-in form. */}
        <div className="flex w-full items-center justify-between gap-3">
          <Link to={ROUTES.HOME} className="inline-flex w-fit items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground"><HardHat size={21} /></span>
            <div><p className="font-bold leading-tight">{t("brand.name")}</p><p className="text-[11px] text-muted-foreground">{t("brand.tagline")}</p></div>
          </Link>
          <LanguageSwitcher />
        </div>
        <div className="my-auto w-full max-w-md self-center py-12"><Outlet /></div>
        <p className="text-xs text-muted-foreground">© {new Date().getFullYear()} {t("brand.copyright")}</p>
      </div>

      <aside className="relative hidden overflow-hidden border-l border-white/10 md:flex md:flex-col md:justify-between md:p-12 lg:p-16">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff08_1px,transparent_1px),linear-gradient(to_bottom,#ffffff08_1px,transparent_1px)] bg-[size:40px_40px]" />
        <div className="relative">
          <span className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-300">{t("authAside.eyebrow")}</span>
          <h2 className="mt-6 max-w-xl text-4xl font-bold leading-tight text-white lg:text-5xl">{t("authAside.headline")}</h2>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-slate-300">{t("authAside.subtitle")}</p>
        </div>
        <div className="relative space-y-4">{capabilities.map(({ icon: Icon, titleKey, textKey }) => <div key={titleKey} className="flex gap-4 rounded-xl border border-white/10 bg-white/[0.035] p-5"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-amber-300/10 text-amber-300"><Icon size={19} /></span><div><h3 className="font-semibold text-white">{t(titleKey)}</h3><p className="mt-1 text-sm leading-relaxed text-slate-400">{t(textKey)}</p></div></div>)}</div>
      </aside>
    </div>
  );
};
