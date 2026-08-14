import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Activity, AlertTriangle, ArrowDown, ArrowRight, Bell, Bot, BriefcaseBusiness,
  Building2, CalendarClock, Camera, Check, CheckCircle2, ChevronRight, CircleUserRound,
  ClipboardList, Cloud, Database, FileCheck2, FileText, Gauge,
  HardHat, KeyRound, Laptop, Layers3, LockKeyhole, MessageSquareText, Mic2, Network,
  RefreshCw, SearchCheck, Server, ShieldCheck, Smartphone, Sparkles,
  TriangleAlert, UserCog, Users, Workflow, XCircle, Zap,
  type LucideIcon,
} from "lucide-react";
import { ROUTES } from "../../utils/constants";
import { StructIQLogo } from "../../components/brand/StructIQLogo";
import "./landing.css";

/**
 * Every string on this page comes from the catalogue under `landing.*`, so the
 * marketing copy switches with the rest of the application rather than staying
 * English behind an Arabic shell. Lists are stored as arrays and read with
 * `returnObjects`, which keeps the copy editable in one place per language.
 */
const useCopy = () => {
  const { t } = useTranslation();
  const list = (key: string) => t(key, { returnObjects: true }) as unknown as string[];
  return { t, list };
};

type IconCardProps = {
  icon: LucideIcon;
  title: string;
  label?: string;
  children?: ReactNode;
  tone?: "navy" | "amber" | "green" | "red" | "blue";
  className?: string;
};

/* Tones map onto the product's semantic state ramp rather than onto an
   arbitrary set of Tailwind hues, so a colour means the same thing on the
   landing page as it does inside the application. */
const toneClasses = {
  navy: "bg-primary/10 text-primary",
  amber: "bg-accent/10 text-accent",
  green: "bg-wash-verified text-state-verified",
  red: "bg-wash-overdue text-state-overdue",
  blue: "bg-wash-progress text-state-progress",
};

const IconCard = ({ icon: Icon, title, label, children, tone = "navy", className = "" }: IconCardProps) => (
  <article className={`landing-card ${className}`}>
    <div className={`inline-flex rounded-xl p-2.5 ${toneClasses[tone]}`}><Icon size={20} /></div>
    {label && <div className="mt-4 text-[11px] font-bold uppercase tracking-[0.18em] text-muted-foreground">{label}</div>}
    <h3 className="mt-2 text-base font-bold">{title}</h3>
    {children}
  </article>
);

const SectionHeading = ({ eyebrow, title, description }: { eyebrow: string; title: string; description?: string }) => (
  <div className="mx-auto mb-10 max-w-3xl text-center md:mb-14">
    <div className="section-kicker">{eyebrow}</div>
    <h2 className="mt-4 text-3xl font-extrabold tracking-tight md:text-4xl">{title}</h2>
    {description && <p className="mx-auto mt-4 max-w-2xl leading-relaxed text-muted-foreground">{description}</p>}
  </div>
);

const FlowArrow = ({ vertical = false, label }: { vertical?: boolean; label?: string }) => (
  <div className={`flow-arrow ${vertical ? "flow-arrow-vertical" : ""}`}>
    {label && <span>{label}</span>}
    {/* The arrow points along the reading direction. */}
    {vertical ? <ArrowDown size={19} /> : <ArrowRight size={19} className="rtl-flip" />}
  </div>
);

const ArchitectureDiagram = () => {
  const { t, list } = useCopy();
  return (
    <section id="architecture" className="landing-section scroll-mt-20">
      <div className="landing-container">
        <SectionHeading eyebrow={t("landing.architecture.eyebrow")} title={t("landing.architecture.title")} description={t("landing.architecture.description")} />
        <div className="architecture-shell">
          <div className="architecture-interface">
            <div className="browser-mini">
              <div className="browser-bar"><i /><i /><i /><span /></div>
              <div className="grid grid-cols-[72px_1fr] gap-3 p-4">
                <div className="rounded-lg bg-primary/10" />
                <div className="space-y-2"><div className="h-9 rounded-lg bg-muted" /><div className="grid grid-cols-3 gap-2"><i /><i /><i /></div></div>
              </div>
            </div>
            <div><span className="node-label">{t("landing.architecture.managementInterface")}</span><h3>{t("landing.architecture.webPlatform")}</h3><p>{t("landing.architecture.webPlatformRoles")}</p></div>
          </div>
          <FlowArrow vertical label={t("landing.architecture.secureApi")} />
          <div className="backend-node">
            <div className="flex items-center justify-center gap-3"><Server size={26} /><h3>{t("landing.architecture.centralBackend")}</h3></div>
            <p>FastAPI + PostgreSQL</p>
            <div className="backend-features">{list("landing.architecture.backendFeatures").map((item) => <span key={item}>{item}</span>)}</div>
          </div>
          <div className="service-rail" aria-label={t("landing.architecture.servicesAria")}>
            <IconCard icon={Sparkles} title={t("landing.architecture.aiServices")} label={t("landing.architecture.aiServicesLabel")} tone="amber" />
            <IconCard icon={Bell} title={t("landing.architecture.notifications")} label={t("landing.architecture.notificationsLabel")} tone="blue" />
            <IconCard icon={Cloud} title={t("landing.architecture.fileStorage")} label={t("landing.architecture.fileStorageLabel")} />
          </div>
          <FlowArrow vertical label={t("landing.architecture.sameData")} />
          <div className="architecture-interface">
            <div className="phone-mini"><div className="phone-speaker" /><div className="space-y-2 p-3 pt-5"><div className="h-5 w-2/3 rounded bg-primary/15" /><div className="h-14 rounded-lg bg-muted" /><div className="h-14 rounded-lg bg-muted" /></div></div>
            <div><span className="node-label">{t("landing.architecture.fieldInterface")}</span><h3>{t("landing.architecture.mobileApplication")}</h3><p>{t("landing.architecture.mobileFeatures")}</p></div>
          </div>
        </div>
        <div className="architecture-note"><Network size={22} /><strong>{t("landing.architecture.noteStrong")}</strong><span>{t("landing.architecture.noteText")}</span></div>
      </div>
    </section>
  );
};

const OrganizationHierarchy = () => {
  const { t, list } = useCopy();
  const [focus, setFocus] = useState<"consultant" | "contractor">("contractor");
  return (
    <section id="team" className="landing-section bg-muted/25 scroll-mt-20">
      <div className="landing-container">
        <SectionHeading eyebrow={t("landing.org.eyebrow")} title={t("landing.org.title")} description={t("landing.org.description")} />
        <div className="hierarchy-root"><Building2 size={19} /> {t("landing.org.root")}</div>
        <div className="hierarchy-split" />
        <div className="grid gap-6 lg:grid-cols-2">
          <button className={`hierarchy-branch text-start ${focus === "consultant" ? "is-active" : ""}`} onClick={() => setFocus("consultant")}>
            <div className="branch-title"><ShieldCheck size={21} /><span><small>{t("landing.org.ownerSide")}</small>{t("landing.org.ownerCompany")}</span></div>
            <div className="branch-lead"><BriefcaseBusiness size={18} /> {t("landing.org.consultantEngineers")}</div>
            <div className="discipline-grid">{list("landing.org.consultantDisciplines").map((item) => <span key={item}>{item}</span>)}</div>
            <p className="branch-purpose">{t("landing.org.consultantPurpose")}</p>
          </button>
          <button className={`hierarchy-branch text-start ${focus === "contractor" ? "is-active" : ""}`} onClick={() => setFocus("contractor")}>
            <div className="branch-title"><HardHat size={21} /><span><small>{t("landing.org.contractorSide")}</small>{t("landing.org.contractorCompany")}</span></div>
            <div className="grid gap-3 sm:grid-cols-2"><div className="branch-lead"><CircleUserRound size={18} /> {t("landing.org.projectManager")}</div><div className="branch-lead"><Users size={18} /> {t("landing.org.siteEngineers")}</div></div>
            <div className="discipline-grid">{list("landing.org.contractorDisciplines").map((item) => <span key={item}>{item}</span>)}</div>
            <p className="branch-purpose">{t("landing.org.contractorPurpose")}</p>
          </button>
        </div>
        <div className="communication-bridge"><MessageSquareText size={19} /><span>{t("landing.org.contractorEngineers")}</span><div className="bridge-line"><i /></div><strong>{t("landing.org.bridge")}</strong><div className="bridge-line reverse"><i /></div><span>{t("landing.org.consultantEngineersShort")}</span></div>
      </div>
    </section>
  );
};

const ROLE_KEYS = ["owner", "projectManager", "contractorEngineer", "siteEngineer", "consultantEngineer", "administrator"] as const;
const ROLE_ICONS: Record<(typeof ROLE_KEYS)[number], LucideIcon> = {
  owner: Building2, projectManager: BriefcaseBusiness, contractorEngineer: HardHat,
  siteEngineer: Smartphone, consultantEngineer: SearchCheck, administrator: UserCog,
};

const RolesSection = () => {
  const { t, list } = useCopy();
  return (
    <section id="roles" className="landing-section">
      <div className="landing-container">
        <SectionHeading eyebrow={t("landing.roles.eyebrow")} title={t("landing.roles.title")} />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {ROLE_KEYS.map((key) => {
            const Icon = ROLE_ICONS[key];
            const mobile = key === "siteEngineer";
            return (
              <article key={key} className={`role-card ${mobile ? "role-card-highlight" : ""}`}>
                <div className="flex items-start justify-between"><span className="role-icon"><Icon size={21} /></span>{mobile && <span className="mobile-chip"><Smartphone size={12} /> {t("landing.roles.mobileFirst")}</span>}</div>
                <h3 className="mt-4 text-lg font-bold">{t(`landing.roles.${key}.name`)}</h3>
                <p className="text-sm font-medium text-accent">{t(`landing.roles.${key}.purpose`)}</p>
                <ul className="mt-4 space-y-2">{list(`landing.roles.${key}.items`).map((item) => <li key={item}><Check size={14} />{item}</li>)}</ul>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
};

const TaskLifecycle = () => {
  const { t, list } = useCopy();
  const [outcome, setOutcome] = useState<"approved" | "rejected">("approved");
  const steps = list("landing.lifecycle.steps");
  const path = list(outcome === "approved" ? "landing.lifecycle.approvedSteps" : "landing.lifecycle.rejectedSteps");
  return (
    <section id="workflow" className="landing-section landing-ink text-white scroll-mt-20">
      <div className="landing-container">
        <SectionHeading eyebrow={t("landing.lifecycle.eyebrow")} title={t("landing.lifecycle.title")} description={t("landing.lifecycle.description")} />
        <div className="lifecycle-track">{steps.map((step, index) => <div className="lifecycle-item" key={step}><span>{String(index + 1).padStart(2, "0")}</span><strong>{step}</strong>{index < steps.length - 1 && <ArrowRight size={18} className="rtl-flip" />}</div>)}</div>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <button onClick={() => setOutcome("approved")} className={`outcome-button approved ${outcome === "approved" ? "active" : ""}`}><CheckCircle2 size={17} /> {t("landing.lifecycle.approvedPath")}</button>
          <button onClick={() => setOutcome("rejected")} className={`outcome-button rejected ${outcome === "rejected" ? "active" : ""}`}><XCircle size={17} /> {t("landing.lifecycle.rejectedPath")}</button>
        </div>
        <div className={`outcome-path ${outcome}`}>
          {path.map((step, i) => <div className="outcome-step" key={step}>{outcome === "approved" ? <CheckCircle2 size={19} /> : <RefreshCw size={18} />}<span>{step}</span>{i < path.length - 1 && <ArrowRight size={18} className="rtl-flip" />}</div>)}
        </div>
      </div>
    </section>
  );
};

const DependencyFlow = () => {
  const { t } = useCopy();
  return (
    <section className="landing-section">
      <div className="landing-container">
        <SectionHeading eyebrow={t("landing.dependency.eyebrow")} title={t("landing.dependency.title")} />
        <div className="dependency-flow">
          <div className="dependency-task done"><span>{t("landing.dependency.task01")}</span><HardHat size={22} /><strong>{t("landing.dependency.foundation")}</strong><em><Check size={14} /> {t("landing.dependency.approved")}</em></div>
          <FlowArrow label={t("landing.dependency.gate")} />
          <div className="dependency-task current"><span>{t("landing.dependency.task02")}</span><Activity size={22} /><strong>{t("landing.dependency.concrete")}</strong><em>{t("landing.dependency.readyToStart")}</em></div>
          <FlowArrow label={t("landing.dependency.gate")} />
          <div className="dependency-task locked"><span>{t("landing.dependency.task03")}</span><LockKeyhole size={22} /><strong>{t("landing.dependency.columns")}</strong><em>{t("landing.dependency.blocked")}</em></div>
        </div>
        <p className="statement-line"><LockKeyhole size={20} /><strong>{t("landing.dependency.statementStrong")}</strong> {t("landing.dependency.statementRest")}</p>
      </div>
    </section>
  );
};

const MobileFlow = () => {
  const { t, list } = useCopy();
  const [recording, setRecording] = useState(false);
  const actionIcons: LucideIcon[] = [ClipboardList, Gauge, Camera, TriangleAlert, FileText, Bell];
  return (
    <section id="mobile-ai" className="landing-section bg-muted/25 scroll-mt-20">
      <div className="landing-container">
        <SectionHeading eyebrow={t("landing.mobile.eyebrow")} title={t("landing.mobile.title")} description={t("landing.mobile.description")} />
        <div className="grid items-center gap-12 lg:grid-cols-[0.72fr_1.28fr]">
          <div className="phone-mockup">
            <div className="phone-top"><span>9:41</span><i /></div>
            <div className="px-5 pb-6"><p className="text-xs text-muted-foreground">{t("landing.mobile.projectName")}</p><h3 className="mt-1 text-xl font-extrabold">{t("landing.mobile.greeting")}</h3>
              <div className="mt-5 grid grid-cols-2 gap-2">{list("landing.mobile.actions").map((label, i) => { const C = actionIcons[i]; return <button className="mobile-action" key={label}><C size={17} />{label}</button>; })}</div>
              <button className={`voice-button ${recording ? "recording" : ""}`} onClick={() => setRecording(!recording)}><Mic2 size={26} /><span>{recording ? t("landing.mobile.recording") : t("landing.mobile.voiceUpdate")}</span></button>
            </div>
          </div>
          <div>
            <div className="voice-quote"><Mic2 size={22} /><p>{t("landing.mobile.quote")}</p></div>
            <div className="ai-pipeline">{list("landing.mobile.pipeline").map((item, i, all) => <div key={item}><span>{i + 1}</span>{item}{i < all.length - 1 && <ChevronRight size={16} className="rtl-flip" />}</div>)}</div>
            <div className="extraction-grid">
              <span><small>{t("landing.mobile.fieldTask")}</small>{t("landing.dependency.foundation")}</span>
              <span><small>{t("landing.mobile.fieldProgress")}</small>80%</span>
              <span><small>{t("landing.mobile.fieldIssue")}</small>{t("landing.mobile.steelDelay")}</span>
              <span><small>{t("landing.mobile.fieldDelay")}</small>{t("landing.mobile.twoHours")}</span>
            </div>
            <div className="validation-flow"><span><Sparkles size={17} /> {t("landing.mobile.aiSuggestion")}</span><ArrowRight size={16} className="rtl-flip" /><span><ShieldCheck size={17} /> {t("landing.mobile.ruleValidation")}</span><ArrowRight size={16} className="rtl-flip" /><span><KeyRound size={17} /> {t("landing.mobile.authorizedAction")}</span></div>
          </div>
        </div>
      </div>
    </section>
  );
};

const AILayer = () => {
  const { t } = useCopy();
  const modules = [
    { icon: Mic2, key: "voice" }, { icon: Zap, key: "taskUpdates" },
    { icon: CalendarClock, key: "delay" }, { icon: FileCheck2, key: "summaries" },
  ] as const;
  return (
    <section className="landing-section">
      <div className="landing-container">
        <SectionHeading eyebrow={t("landing.ai.eyebrow")} title={t("landing.ai.title")} />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">{modules.map(({ icon, key }) => <IconCard key={key} icon={icon} title={t(`landing.ai.${key}.title`)} tone="amber"><p className="mt-3 text-sm leading-relaxed text-muted-foreground">{t(`landing.ai.${key}.text`)}</p></IconCard>)}</div>
        <p className="statement-line"><ShieldCheck size={20} /><strong>{t("landing.ai.statementStrong")}</strong> {t("landing.ai.statementRest")}</p>
      </div>
    </section>
  );
};

const InformationFlow = () => {
  const { t, list } = useCopy();
  const icons: LucideIcon[] = [HardHat, Smartphone, Camera, Bot, ClipboardList, Gauge, SearchCheck, CheckCircle2, Bell];
  const steps = list("landing.infoFlow.steps");
  return (
    <section id="information-flow" className="landing-section bg-primary text-primary-foreground scroll-mt-20">
      <div className="landing-container">
        <SectionHeading eyebrow={t("landing.infoFlow.eyebrow")} title={t("landing.infoFlow.title")} description={t("landing.infoFlow.description")} />
        <div className="information-flow">{steps.map((label, i) => { const Icon = icons[i]; return <div className="information-node" key={label}><span><Icon size={19} /></span><strong>{label}</strong>{i < steps.length - 1 && <div className="animated-connector"><i /></div>}</div>; })}</div>
      </div>
    </section>
  );
};

const ContractorConsultantComparison = () => {
  const { t, list } = useCopy();
  return (
    <section className="landing-section">
      <div className="landing-container">
        <SectionHeading eyebrow={t("landing.comparison.eyebrow")} title={t("landing.comparison.title")} />
        <div className="comparison-grid">
          <div className="comparison-side contractor"><HardHat size={28} /><p>{t("landing.comparison.responsibleFor")}</p><h3>{t("landing.comparison.execution")}</h3><ul>{list("landing.comparison.contractorItems").map((x) => <li key={x}><Check size={15} />{x}</li>)}</ul></div>
          <div className="comparison-middle">{list("landing.comparison.middle").map((x, i, all) => <span key={x}>{x}{i < all.length - 1 && <ArrowDown />}</span>)}</div>
          <div className="comparison-side consultant"><SearchCheck size={28} /><p>{t("landing.comparison.responsibleFor")}</p><h3>{t("landing.comparison.verification")}</h3><ul>{list("landing.comparison.consultantItems").map((x) => <li key={x}><Check size={15} />{x}</li>)}</ul></div>
        </div>
        <div className="communication-loop">{list("landing.comparison.loop").map((x, i, all) => <span key={x}>{x}{i < all.length - 1 && <ArrowRight className="rtl-flip" />}</span>)}</div>
      </div>
    </section>
  );
};

const WebApplication = () => {
  const { t, list } = useCopy();
  const stats = list("landing.web.stats");
  const tones = ["green", "blue", "amber", "red"];
  const values = ["68%", "24", "5", "3"];
  return (
    <section className="landing-section bg-muted/25">
      <div className="landing-container">
        <SectionHeading eyebrow={t("landing.web.eyebrow")} title={t("landing.web.title")} description={t("landing.web.description")} />
        <div className="dashboard-mockup">
          <div className="dashboard-sidebar"><Layers3 size={23} /><span /><span /><span /><span /></div>
          <div className="dashboard-content">
            <div className="dashboard-toolbar"><div><small>{t("landing.mobile.projectName")}</small><strong>{t("landing.web.commandCenter")}</strong></div><div className="avatar-stack"><i /><i /><i /></div></div>
            <div className="dashboard-stats">{stats.map((label, i) => <div key={label} className={`stat-${tones[i]}`}><small>{label}</small><strong>{values[i]}</strong></div>)}</div>
            <div className="dashboard-lower"><div><div className="flex items-center justify-between"><strong>{t("landing.web.milestoneProgress")}</strong><span>68%</span></div><div className="chart-bars">{[38, 60, 48, 78, 68, 88, 72].map((h, i) => <i key={i} style={{ height: `${h}%` }} />)}</div></div><div><strong>{t("landing.web.recentReports")}</strong>{list("landing.web.reports").map((x, i) => <p key={x}><span>{i + 1}</span>{x}</p>)}</div></div>
          </div>
        </div>
      </div>
    </section>
  );
};

const SystemViews = () => {
  const { t, list } = useCopy();
  const icons: LucideIcon[] = [Smartphone, Laptop, SearchCheck, Building2, UserCog];
  return (
    <section className="landing-section">
      <div className="landing-container">
        <SectionHeading eyebrow={t("landing.views.eyebrow")} title={t("landing.views.title")} />
        <div className="system-orbit">
          <div className="orbit-center"><Database size={30} /><strong>{t("landing.views.centralData")}</strong><span><KeyRound size={14} /> {t("landing.views.rbac")}</span></div>
          {list("landing.views.items").map((view, i) => { const Icon = icons[i]; return <div key={view} className={`orbit-view orbit-${i + 1}`}><Icon size={19} /><span>{view}</span></div>; })}
        </div>
        <p className="mx-auto mt-8 max-w-2xl text-center text-muted-foreground">{t("landing.views.note")}</p>
      </div>
    </section>
  );
};

const ProjectExample = () => {
  const { t, list } = useCopy();
  const [selected, setSelected] = useState(1);
  const titles = list("landing.example.activityTitles");
  const statuses = list("landing.example.activityStatuses");
  const progress = [100, 75, 0];
  const tones = ["green", "blue", "amber"];
  return (
    <section id="example" className="landing-section landing-ink text-white scroll-mt-20">
      <div className="landing-container">
        <SectionHeading eyebrow={t("landing.example.eyebrow")} title={t("landing.mobile.projectName")} description={t("landing.example.description")} />
        <div className="example-grid">
          <div className="space-y-3">{titles.map((title, i) => <button className={`project-activity ${selected === i ? "active" : ""}`} onClick={() => setSelected(i)} key={title}><span className={`activity-icon ${tones[i]}`}>{i === 2 ? <LockKeyhole size={18} /> : <CheckCircle2 size={18} />}</span><span><strong>{title}</strong><small>{statuses[i]}</small></span><b>{progress[i]}%</b></button>)}</div>
          <div className="project-detail">
            <div className="flex items-start justify-between"><div><small>{t("landing.example.selectedActivity")}</small><h3>{titles[selected]}</h3></div><span className={`status-pill ${tones[selected]}`}>{statuses[selected]}</span></div>
            <div className="progress-track"><i style={{ width: `${progress[selected]}%` }} /></div>
            {selected === 2 ? <div className="blocked-reason"><LockKeyhole size={20} /><span><small>{t("landing.example.blockedBecause")}</small>{t("landing.example.blockedReason")}</span></div> : <p className="latest-update">{t("landing.example.latestUpdate")}</p>}
            <div className="project-metrics"><span><small>{t("landing.example.consultantReviews")}</small><strong>{t("landing.example.twoPending")}</strong></span><span><small>{t("landing.example.openIssues")}</small><strong>3</strong></span></div>
          </div>
        </div>
      </div>
    </section>
  );
};

const WhySection = () => {
  const { t, list } = useCopy();
  return (
    <section className="landing-section">
      <div className="landing-container">
        <SectionHeading eyebrow={t("landing.why.eyebrow")} title={t("landing.why.title")} />
        <div className="problem-solution">
          <div><span className="side-label problem"><AlertTriangle size={16} /> {t("landing.why.todayProblem")}</span>{list("landing.why.problems").map((x) => <p key={x}><XCircle size={16} />{x}</p>)}</div>
          <div className="transformation-arrow"><ArrowRight size={26} className="rtl-flip" /></div>
          <div><span className="side-label solution"><CheckCircle2 size={16} /> {t("landing.why.solution")}</span><h3>{t("landing.why.solutionTitle")}</h3>{list("landing.why.solutions").map((x) => <p key={x}><CheckCircle2 size={16} />{x}</p>)}</div>
        </div>
      </div>
    </section>
  );
};

const ProblemValue = () => {
  const { t, list } = useCopy();
  return (
    <section id="why" className="landing-section scroll-mt-20">
      <div className="landing-container">
        <SectionHeading eyebrow={t("landing.problem.eyebrow")} title={t("landing.problem.title")} description={t("landing.problem.description")} />
        <div className="problem-split">
          <article className="problem-col scattered">
            <div className="section-kicker">{t("landing.problem.today")}</div>
            <h3 className="mt-2 text-xl font-extrabold">{t("landing.problem.scattered")}</h3>
            <ul>{list("landing.problem.scatteredItems").map((item) => <li key={item}><XCircle size={15} />{item}</li>)}</ul>
          </article>
          <div className="comparison-middle"><ArrowRight size={22} className="rtl-flip" /><span>{t("landing.problem.oneWorkspace")}</span></div>
          <article className="problem-col connected">
            <div className="section-kicker">{t("landing.problem.withPlatform")}</div>
            <h3 className="mt-2 text-xl font-extrabold">{t("landing.problem.connected")}</h3>
            <ul>{list("landing.problem.connectedItems").map((item) => <li key={item}><Check size={15} />{item}</li>)}</ul>
          </article>
        </div>
      </div>
    </section>
  );
};

const FEATURE_KEYS = [
  "projectsTasks", "scheduling", "siteReports", "fieldEvidence", "communication", "ownerRequests",
  "siteVisits", "documents", "ifc", "issues", "approvals", "reminders",
] as const;
const FEATURE_ICONS: LucideIcon[] = [
  ClipboardList, CalendarClock, FileText, Camera, MessageSquareText, CircleUserRound,
  CalendarClock, Layers3, Building2, TriangleAlert, FileCheck2, Bell,
];

const CoreFeatures = () => {
  const { t } = useCopy();
  return (
    <section id="features" className="landing-section bg-muted/25 scroll-mt-20">
      <div className="landing-container">
        <SectionHeading eyebrow={t("landing.features.eyebrow")} title={t("landing.features.title")} description={t("landing.features.description")} />
        <div className="feature-grid">
          {FEATURE_KEYS.map((key, i) => <IconCard key={key} icon={FEATURE_ICONS[i]} title={t(`landing.features.${key}.title`)}><p>{t(`landing.features.${key}.body`)}</p></IconCard>)}
        </div>
      </div>
    </section>
  );
};

const BimSection = () => {
  const { t, list } = useCopy();
  const icons: LucideIcon[] = [Layers3, ClipboardList, CalendarClock, Gauge, TriangleAlert];
  return (
    <section id="bim" className="landing-section scroll-mt-20">
      <div className="landing-container">
        <SectionHeading eyebrow={t("landing.bim.eyebrow")} title={t("landing.bim.title")} description={t("landing.bim.description")} />
        <div className="bim-stack">
          {list("landing.bim.inputs").map((label, i) => { const Icon = icons[i]; return <div key={label} className="bim-input"><Icon size={19} />{label}</div>; })}
        </div>
        <div className="bim-finding">
          <div className="section-kicker"><SearchCheck size={14} /> {t("landing.bim.exampleFinding")}</div>
          <p className="mt-2"><strong>{t("landing.bim.findingStrong")}</strong>{" "}{t("landing.bim.findingRest")}</p>
          <small>{t("landing.bim.findingMeta")}</small>
        </div>
        <div className="statement-line"><ShieldCheck size={17} /><span>{t("landing.bim.advisory")}</span></div>
      </div>
    </section>
  );
};

const ACCOUNTABILITY_KEYS = ["audit", "acknowledgements", "reviewChains", "reminders", "humanAuthority", "traceable"] as const;
const ACCOUNTABILITY_ICONS: LucideIcon[] = [Activity, Check, FileCheck2, Bell, UserCog, Workflow];

const AccountabilitySection = () => {
  const { t } = useCopy();
  return (
    <section id="accountability" className="landing-section bg-muted/25 scroll-mt-20">
      <div className="landing-container">
        <SectionHeading eyebrow={t("landing.accountability.eyebrow")} title={t("landing.accountability.title")} description={t("landing.accountability.description")} />
        <div className="accountability-grid">
          {ACCOUNTABILITY_KEYS.map((key, i) => { const Icon = ACCOUNTABILITY_ICONS[i]; return (
            <div key={key}><Icon size={19} /><strong className="mt-3">{t(`landing.accountability.${key}.title`)}</strong><p>{t(`landing.accountability.${key}.body`)}</p></div>
          ); })}
        </div>
      </div>
    </section>
  );
};

export const LandingPage = () => {
  const { t, list } = useCopy();
  const finalFlow = list("landing.final.flow");
  return (
    <div className="landing-page">
      <section className="hero-section">
        <div className="blueprint-grid" />
        <div className="landing-container relative">
          <div className="hero-copy">
            {/* The brand stated once, at full strength, before the argument
                begins. Everything below it is the existing messaging. */}
            <div className="mb-7 flex justify-center">
              <StructIQLogo variant="full" size={46} inverted />
            </div>
            <div className="section-kicker"><HardHat size={15} /> {t("landing.hero.kicker")}</div>
            <h1>{t("landing.hero.titleLine1")}<br /><span>{t("landing.hero.titleLine2")}</span></h1>
            <p>{t("landing.hero.description")}</p>
            <div className="hero-actions">
              <Link to={ROUTES.LOGIN} className="primary-cta">{t("landing.hero.openPlatform")} <ArrowRight size={17} className="rtl-flip" /></Link>
              <a href="#workflow" className="secondary-cta">{t("landing.hero.seeHow")} <ArrowDown size={17} /></a>
            </div>
          </div>
          <div className="hero-scene" aria-label={t("landing.hero.sceneAria")}>
            <div className="hero-panel">
              <h4>{t("landing.hero.floorPlan")}</h4>
              <div className="hero-plan" aria-hidden="true"><i /><i /><i /><b>{t("landing.hero.groundFloor")}</b></div>
            </div>
            <div className="hero-stack">
              <div className="hero-panel">
                <h4>{t("landing.hero.verifiedProgress")}</h4>
                <div className="hero-progress">
                  {list("landing.hero.progressItems").map((label, i) => {
                    const width = [100, 62, 18][i];
                    return <div key={label}><span>{label}</span><span>{width}%</span><u><b style={{ width: `${width}%` }} /></u></div>;
                  })}
                </div>
              </div>
              <div className="hero-panel">
                <h4>{t("landing.hero.latestFromSite")}</h4>
                <div className="mt-3 grid gap-2">
                  <div className="hero-evidence"><Camera size={15} /><span>{t("landing.hero.evidencePhotos")}</span></div>
                  <div className="hero-evidence"><FileCheck2 size={15} /><span>{t("landing.hero.evidenceReport")}</span></div>
                  <div className="hero-evidence"><TriangleAlert size={15} /><span>{t("landing.hero.evidenceIssue")}</span></div>
                </div>
              </div>
            </div>
          </div>
          <div className="hero-proof"><span><ShieldCheck size={17} /> {t("landing.hero.proofApprovals")}</span><span><Camera size={17} /> {t("landing.hero.proofEvidence")}</span><span><Workflow size={17} /> {t("landing.hero.proofDecisions")}</span></div>
        </div>
      </section>
      {/* §23 order: problem → workflow → features → AI → roles → BIM → mobile → accountability → CTA */}
      <ProblemValue />
      <TaskLifecycle />
      <DependencyFlow />
      <CoreFeatures />
      <AILayer />
      <RolesSection />
      <OrganizationHierarchy />
      <BimSection />
      <MobileFlow />
      <InformationFlow />
      <AccountabilitySection />
      <ContractorConsultantComparison />
      <WebApplication />
      <SystemViews />
      <ProjectExample />
      <ArchitectureDiagram />
      <WhySection />
      <section className="final-section">
        <div className="landing-container text-center">
          <div className="section-kicker">{t("landing.final.kicker")}</div>
          <h2>{t("landing.final.titleLine1")}<br />{t("landing.final.titleLine2")}</h2>
          <div className="final-flow">{finalFlow.map((x, i) => <span key={x}>{x}{i < finalFlow.length - 1 && <ArrowRight size={17} className="rtl-flip" />}</span>)}</div>
          <p>{t("landing.final.audience")}</p>
          <div className="hero-actions">
            <Link to={ROUTES.LOGIN} className="primary-cta">{t("landing.hero.openPlatform")} <ArrowRight size={17} className="rtl-flip" /></Link>
            <a href="#features" className="secondary-cta">{t("landing.final.seeModules")} <ArrowDown size={17} /></a>
          </div>
        </div>
      </section>
    </div>
  );
};
