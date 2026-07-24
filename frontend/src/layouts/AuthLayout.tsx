import { Link, Outlet } from "react-router-dom";
import { CalendarRange, ClipboardCheck, HardHat, Users } from "lucide-react";
import { ROUTES } from "../utils/constants";

const capabilities = [
  { icon: CalendarRange, title: "Plan the work", text: "Coordinate milestones, Gantt schedules, dependencies, and critical paths." },
  { icon: ClipboardCheck, title: "Control execution", text: "Track tasks, site reports, issues, documents, and review decisions." },
  { icon: Users, title: "Align every role", text: "Give owners, managers, consultants, and engineers the right workspace." },
];

export const AuthLayout = () => (
  <div className="min-h-screen bg-slate-950 md:grid md:grid-cols-[minmax(420px,0.9fr)_minmax(520px,1.1fr)]">
    <div className="flex min-h-screen flex-col bg-background px-6 py-8 sm:px-12 lg:px-20">
      <Link to={ROUTES.HOME} className="inline-flex w-fit items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground"><HardHat size={21} /></span>
        <div><p className="font-bold leading-tight">Smart Construction</p><p className="text-[11px] text-muted-foreground">Project Management Platform</p></div>
      </Link>
      <div className="my-auto w-full max-w-md self-center py-12"><Outlet /></div>
      <p className="text-xs text-muted-foreground">© {new Date().getFullYear()} Smart Construction Platform</p>
    </div>

    <aside className="relative hidden overflow-hidden border-l border-white/10 md:flex md:flex-col md:justify-between md:p-12 lg:p-16">
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff08_1px,transparent_1px),linear-gradient(to_bottom,#ffffff08_1px,transparent_1px)] bg-[size:40px_40px]" />
      <div className="relative">
        <span className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-300">Built for construction teams</span>
        <h2 className="mt-6 max-w-xl text-4xl font-bold leading-tight text-white lg:text-5xl">Keep the project clear from planning through handover.</h2>
        <p className="mt-5 max-w-xl text-base leading-relaxed text-slate-300">A structured workspace for field execution, technical review, project leadership, and executive visibility.</p>
      </div>
      <div className="relative space-y-4">{capabilities.map(({ icon: Icon, title, text }) => <div key={title} className="flex gap-4 rounded-xl border border-white/10 bg-white/[0.035] p-5"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-amber-300/10 text-amber-300"><Icon size={19} /></span><div><h3 className="font-semibold text-white">{title}</h3><p className="mt-1 text-sm leading-relaxed text-slate-400">{text}</p></div></div>)}</div>
      <p className="relative text-xs text-slate-500">AI automation and Telegram delivery will build on this verified core in the next phase.</p>
    </aside>
  </div>
);
