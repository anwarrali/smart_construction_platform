import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
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
import "./landing.css";

type IconCardProps = {
  icon: LucideIcon;
  title: string;
  label?: string;
  children?: ReactNode;
  tone?: "navy" | "amber" | "green" | "red" | "blue";
  className?: string;
};

const toneClasses = {
  navy: "bg-primary/10 text-primary",
  amber: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
  green: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  red: "bg-rose-500/10 text-rose-700 dark:text-rose-300",
  blue: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
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
    {vertical ? <ArrowDown size={19} /> : <ArrowRight size={19} />}
  </div>
);

const ArchitectureDiagram = () => (
  <section id="architecture" className="landing-section scroll-mt-20">
    <div className="landing-container">
      <SectionHeading eyebrow="System Architecture" title="Two interfaces. One coordinated system." description="Field data, decisions, documents, and approvals all pass through a shared control layer." />
      <div className="architecture-shell">
        <div className="architecture-interface">
          <div className="browser-mini">
            <div className="browser-bar"><i /><i /><i /><span /></div>
            <div className="grid grid-cols-[72px_1fr] gap-3 p-4">
              <div className="rounded-lg bg-primary/10" />
              <div className="space-y-2"><div className="h-9 rounded-lg bg-muted" /><div className="grid grid-cols-3 gap-2"><i /><i /><i /></div></div>
            </div>
          </div>
          <div><span className="node-label">Management interface</span><h3>Web Platform</h3><p>PM · Consultant · Owner · Admin</p></div>
        </div>
        <FlowArrow vertical label="Secure API" />
        <div className="backend-node">
          <div className="flex items-center justify-center gap-3"><Server size={26} /><h3>Central Backend</h3></div>
          <p>FastAPI + PostgreSQL</p>
          <div className="backend-features"><span>Authentication + RBAC</span><span>Tasks + Reports + Docs</span><span>Notifications + Audit</span></div>
        </div>
        <div className="service-rail" aria-label="Connected backend services">
          <IconCard icon={Sparkles} title="AI Services" label="Voice · Actions · Delays" tone="amber" />
          <IconCard icon={Bell} title="Notifications" label="Event-driven updates" tone="blue" />
          <IconCard icon={Cloud} title="File Storage" label="Photos · Reports · Docs" />
        </div>
        <FlowArrow vertical label="Same data + rules" />
        <div className="architecture-interface">
          <div className="phone-mini"><div className="phone-speaker" /><div className="space-y-2 p-3 pt-5"><div className="h-5 w-2/3 rounded bg-primary/15" /><div className="h-14 rounded-lg bg-muted" /><div className="h-14 rounded-lg bg-muted" /></div></div>
          <div><span className="node-label">Field interface</span><h3>Mobile Application</h3><p>Tasks · Voice · Photos · Reports · Issues</p></div>
        </div>
      </div>
      <div className="architecture-note"><Network size={22} /><strong>Web and Mobile are not separate systems.</strong><span>They share the same backend, database, permissions, and AI services.</span></div>
    </div>
  </section>
);

const hierarchy = {
  consultant: ["Civil Consultant", "Architectural Consultant", "Electrical Consultant", "Mechanical Consultant"],
  contractor: ["Civil Engineer", "Architectural Engineer", "Electrical Engineer", "Mechanical Engineer"],
};

const OrganizationHierarchy = () => {
  const [focus, setFocus] = useState<"consultant" | "contractor">("contractor");
  return (
    <section id="team" className="landing-section bg-muted/25 scroll-mt-20">
      <div className="landing-container">
        <SectionHeading eyebrow="Project Organization" title="Clear authority. Clear accountability." description="Select a side to highlight how responsibility moves through the project team." />
        <div className="hierarchy-root"><Building2 size={19} /> Construction Project</div>
        <div className="hierarchy-split" />
        <div className="grid gap-6 lg:grid-cols-2">
          <button className={`hierarchy-branch text-left ${focus === "consultant" ? "is-active" : ""}`} onClick={() => setFocus("consultant")}>
            <div className="branch-title"><ShieldCheck size={21} /><span><small>Owner side</small>Owner + Consultant Company</span></div>
            <div className="branch-lead"><BriefcaseBusiness size={18} /> Consultant Engineers</div>
            <div className="discipline-grid">{hierarchy.consultant.map((item) => <span key={item}>{item}</span>)}</div>
            <p className="branch-purpose">Reviews, verifies, approves, or rejects work on behalf of the owner.</p>
          </button>
          <button className={`hierarchy-branch text-left ${focus === "contractor" ? "is-active" : ""}`} onClick={() => setFocus("contractor")}>
            <div className="branch-title"><HardHat size={21} /><span><small>Contractor side</small>Contractor Company</span></div>
            <div className="grid gap-3 sm:grid-cols-2"><div className="branch-lead"><CircleUserRound size={18} /> Project Manager</div><div className="branch-lead"><Users size={18} /> Site Engineers</div></div>
            <div className="discipline-grid">{hierarchy.contractor.map((item) => <span key={item}>{item}</span>)}</div>
            <p className="branch-purpose">Executes construction work, records evidence, and reports progress.</p>
          </button>
        </div>
        <div className="communication-bridge"><MessageSquareText size={19} /><span>Contractor engineers</span><div className="bridge-line"><i /></div><strong>Platform communication & review trail</strong><div className="bridge-line reverse"><i /></div><span>Consultant engineers</span></div>
      </div>
    </section>
  );
};

const roleData = [
  { role: "Owner", purpose: "High-level visibility", icon: Building2, items: ["Overall progress & milestones", "Approved documents", "Major delays & project status"] },
  { role: "Project Manager", purpose: "Manage execution", icon: BriefcaseBusiness, items: ["Create, assign & coordinate tasks", "Track deadlines & dependencies", "Monitor issues, teams & reports"] },
  { role: "Contractor Engineer", purpose: "Execute & update work", icon: HardHat, items: ["Update progress & submit work", "Upload evidence & site reports", "Record issues, notes & delays"] },
  { role: "Site Engineer", purpose: "Fast field updates", icon: Smartphone, items: ["Voice updates from site", "Photos, reports & issues", "Tasks & live notifications"], mobile: true },
  { role: "Consultant Engineer", purpose: "Independent review", icon: SearchCheck, items: ["Inspect submitted evidence", "Approve, reject & comment", "Control dependent task gates"] },
  { role: "Administrator", purpose: "Platform configuration", icon: UserCog, items: ["Users, companies & projects", "Roles & project teams", "Access & account status"] },
];

const RoleCard = ({ role, purpose, icon: Icon, items, mobile }: typeof roleData[number]) => (
  <article className={`role-card ${mobile ? "role-card-highlight" : ""}`}>
    <div className="flex items-start justify-between"><span className="role-icon"><Icon size={21} /></span>{mobile && <span className="mobile-chip"><Smartphone size={12} /> Mobile-first</span>}</div>
    <h3 className="mt-4 text-lg font-bold">{role}</h3><p className="text-sm font-medium text-amber-700 dark:text-amber-300">{purpose}</p>
    <ul className="mt-4 space-y-2">{items.map((item) => <li key={item}><Check size={14} />{item}</li>)}</ul>
  </article>
);

const RolesSection = () => (
  <section id="roles" className="landing-section">
    <div className="landing-container">
      <SectionHeading eyebrow="Role Responsibilities" title="The right view for every responsibility" />
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">{roleData.map((role) => <RoleCard key={role.role} {...role} />)}</div>
    </div>
  </section>
);

const lifecycleSteps = ["Task created", "Assigned to contractor", "Work starts", "Progress + evidence updated", "Submitted for review", "Consultant review"];

const TaskLifecycle = () => {
  const [outcome, setOutcome] = useState<"approved" | "rejected">("approved");
  return (
    <section id="workflow" className="landing-section bg-slate-950 text-white scroll-mt-20">
      <div className="landing-container">
        <SectionHeading eyebrow="Task Lifecycle" title="From assignment to controlled approval" description="Every step is traceable. Consultant review decides what happens next." />
        <div className="lifecycle-track">{lifecycleSteps.map((step, index) => <div className="lifecycle-item" key={step}><span>{String(index + 1).padStart(2, "0")}</span><strong>{step}</strong>{index < lifecycleSteps.length - 1 && <ArrowRight size={18} />}</div>)}</div>
        <div className="mt-8 flex justify-center gap-3">
          <button onClick={() => setOutcome("approved")} className={`outcome-button approved ${outcome === "approved" ? "active" : ""}`}><CheckCircle2 size={17} /> Approved path</button>
          <button onClick={() => setOutcome("rejected")} className={`outcome-button rejected ${outcome === "rejected" ? "active" : ""}`}><XCircle size={17} /> Rejected path</button>
        </div>
        <div className={`outcome-path ${outcome}`}>
          {outcome === "approved" ? (
            <>{["Consultant approves", "Task becomes done", "Dependent task unlocks", "Next activity starts"].map((step, i) => <div className="outcome-step" key={step}><CheckCircle2 size={19} /><span>{step}</span>{i < 3 && <ArrowRight size={18} />}</div>)}</>
          ) : (
            <>{["Reject + comment", "Return to engineer", "Rework", "Resubmit", "Review again"].map((step, i) => <div className="outcome-step" key={step}><RefreshCw size={18} /><span>{step}</span>{i < 4 && <ArrowRight size={18} />}</div>)}</>
          )}
        </div>
      </div>
    </section>
  );
};

const DependencyFlow = () => (
  <section className="landing-section">
    <div className="landing-container">
      <SectionHeading eyebrow="Dependency Control" title="Approval is a gate—not a label" />
      <div className="dependency-flow">
        <div className="dependency-task done"><span>Task 01</span><HardHat size={22} /><strong>Foundation Reinforcement</strong><em><Check size={14} /> Approved</em></div>
        <FlowArrow label="Consultant gate" />
        <div className="dependency-task current"><span>Task 02</span><Activity size={22} /><strong>Concrete Pouring</strong><em>Ready to start</em></div>
        <FlowArrow label="Consultant gate" />
        <div className="dependency-task locked"><span>Task 03</span><LockKeyhole size={22} /><strong>Column Construction</strong><em>Blocked</em></div>
      </div>
      <p className="statement-line"><LockKeyhole size={20} /><strong>The system understands dependencies</strong> and prevents work from advancing before required approvals are completed.</p>
    </div>
  </section>
);

const MobileFlow = () => {
  const [recording, setRecording] = useState(false);
  return (
    <section id="mobile-ai" className="landing-section bg-muted/25 scroll-mt-20">
      <div className="landing-container">
        <SectionHeading eyebrow="Mobile Application" title="Built for the construction site" description="Fast input, low friction, and immediate connection to the project record." />
        <div className="grid items-center gap-12 lg:grid-cols-[0.72fr_1.28fr]">
          <div className="phone-mockup">
            <div className="phone-top"><span>9:41</span><i /></div>
            <div className="px-5 pb-6"><p className="text-xs text-muted-foreground">Residential Complex C</p><h3 className="mt-1 text-xl font-extrabold">Good morning, Ahmad</h3>
              <div className="mt-5 grid grid-cols-2 gap-2">{[["My Tasks", ClipboardList], ["Progress", Gauge], ["Upload Photo", Camera], ["Report Issue", TriangleAlert], ["Site Report", FileText], ["Notifications", Bell]].map(([label, Icon]) => { const C = Icon as LucideIcon; return <button className="mobile-action" key={label as string}><C size={17} />{label as string}</button>; })}</div>
              <button className={`voice-button ${recording ? "recording" : ""}`} onClick={() => setRecording(!recording)}><Mic2 size={26} /><span>{recording ? "Recording update…" : "Voice Update"}</span></button>
            </div>
          </div>
          <div>
            <div className="voice-quote"><Mic2 size={22} /><p>“Foundation reinforcement is approximately <strong>80% complete</strong>. We had a <strong>two-hour delay</strong> because the steel delivery arrived late.”</p></div>
            <div className="ai-pipeline">{["Voice", "Speech-to-text", "AI analysis", "Structured update"].map((item, i) => <div key={item}><span>{i + 1}</span>{item}{i < 3 && <ChevronRight size={16} />}</div>)}</div>
            <div className="extraction-grid"><span><small>Task</small>Foundation Reinforcement</span><span><small>Progress</small>80%</span><span><small>Issue</small>Steel delivery delay</span><span><small>Delay</small>2 hours</span></div>
            <div className="validation-flow"><span><Sparkles size={17} /> AI Suggestion</span><ArrowRight size={16} /><span><ShieldCheck size={17} /> Rule Validation</span><ArrowRight size={16} /><span><KeyRound size={17} /> Authorized Action</span></div>
          </div>
        </div>
      </div>
    </section>
  );
};

const AILayer = () => {
  const modules = [
    { icon: Mic2, title: "Voice Intelligence", text: "Voice notes → transcription → extraction" },
    { icon: Zap, title: "Smart Task Updates", text: "Task · percentage · delay · issue · status" },
    { icon: CalendarClock, title: "Delay Intelligence", text: "Overdue · blocked · downstream impact" },
    { icon: FileCheck2, title: "Smart Summaries", text: "Daily site · progress · issues · reviews" },
  ];
  return (
    <section className="landing-section">
      <div className="landing-container">
        <SectionHeading eyebrow="AI Assistance Layer" title="Useful intelligence, controlled authority" />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">{modules.map((item) => <IconCard key={item.title} {...item} tone="amber"><p className="mt-3 text-sm leading-relaxed text-muted-foreground">{item.text}</p></IconCard>)}</div>
        <p className="statement-line"><ShieldCheck size={20} /><strong>AI assists the project team.</strong> It does not replace engineering authority or consultant approval.</p>
      </div>
    </section>
  );
};

const InformationFlow = () => {
  const steps = [
    [HardHat, "Work on site"], [Smartphone, "Engineer records it"], [Camera, "Evidence attached"],
    [Bot, "Checked against the plan"], [ClipboardList, "Task updated"], [Gauge, "Progress visible"],
    [SearchCheck, "Consultant review"], [CheckCircle2, "Approved"], [Bell, "Owner informed"],
  ] as const;
  return (
    <section id="information-flow" className="landing-section bg-primary text-primary-foreground scroll-mt-20">
      <div className="landing-container">
        <SectionHeading eyebrow="Information flow" title="What happens to one update from the site" description="A single field update becomes verified progress, a reviewable record, and an answer for the owner." />
        <div className="information-flow">{steps.map(([Icon, label], i) => <div className="information-node" key={label}><span><Icon size={19} /></span><strong>{label}</strong>{i < steps.length - 1 && <div className="animated-connector"><i /></div>}</div>)}</div>
      </div>
    </section>
  );
};

const ContractorConsultantComparison = () => (
  <section className="landing-section">
    <div className="landing-container">
      <SectionHeading eyebrow="Collaboration Model" title="Execution meets independent verification" />
      <div className="comparison-grid">
        <div className="comparison-side contractor"><HardHat size={28} /><p>Responsible for</p><h3>Execution</h3><ul>{["Perform construction work", "Update progress", "Upload evidence", "Report site conditions", "Resolve and resubmit rejected work"].map((x) => <li key={x}><Check size={15} />{x}</li>)}</ul></div>
        <div className="comparison-middle"><span>Execution</span><ArrowDown /><span>Review</span><ArrowDown /><span>Approval</span><ArrowDown /><span>Next activity</span></div>
        <div className="comparison-side consultant"><SearchCheck size={28} /><p>Responsible for</p><h3>Verification</h3><ul>{["Review contractor work", "Check compliance", "Inspect submitted evidence", "Approve or reject", "Control technical approval gates"].map((x) => <li key={x}><Check size={15} />{x}</li>)}</ul></div>
      </div>
      <div className="communication-loop"><span>Contractor submits</span><ArrowRight /><span>Consultant decides</span><ArrowRight /><span>Engineer notified</span><ArrowRight /><span>PM monitors</span><ArrowRight /><span>Owner sees results</span></div>
    </div>
  </section>
);

const WebApplication = () => (
  <section className="landing-section bg-muted/25">
    <div className="landing-container">
      <SectionHeading eyebrow="Web Application" title="Management, monitoring, and technical review" description="Optimized workspaces for the Project Manager, Consultant, Owner, and Administrator." />
      <div className="dashboard-mockup">
        <div className="dashboard-sidebar"><Layers3 size={23} /><span /><span /><span /><span /></div>
        <div className="dashboard-content">
          <div className="dashboard-toolbar"><div><small>Residential Complex C</small><strong>Project Command Center</strong></div><div className="avatar-stack"><i /><i /><i /></div></div>
          <div className="dashboard-stats">{[["Project Progress", "68%", "green"], ["Active Tasks", "24", "blue"], ["Under Review", "5", "amber"], ["Delayed Tasks", "3", "red"]].map(([label, value, tone]) => <div key={label} className={`stat-${tone}`}><small>{label}</small><strong>{value}</strong></div>)}</div>
          <div className="dashboard-lower"><div><div className="flex items-center justify-between"><strong>Milestone progress</strong><span>68%</span></div><div className="chart-bars">{[38, 60, 48, 78, 68, 88, 72].map((h, i) => <i key={i} style={{ height: `${h}%` }} />)}</div></div><div><strong>Recent site reports</strong>{["Foundation inspection", "Steel delivery delay", "Column reinforcement"].map((x, i) => <p key={x}><span>{i + 1}</span>{x}</p>)}</div></div>
        </div>
      </div>
    </div>
  </section>
);

const SystemViews = () => {
  const views = [[Smartphone, "Mobile Engineer"], [Laptop, "PM Dashboard"], [SearchCheck, "Consultant Portal"], [Building2, "Owner Dashboard"], [UserCog, "Admin Portal"]] as const;
  return (
    <section className="landing-section">
      <div className="landing-container">
        <SectionHeading eyebrow="One System, Different Views" title="Shared data. Role-specific access." />
        <div className="system-orbit">
          <div className="orbit-center"><Database size={30} /><strong>Central Project Data</strong><span><KeyRound size={14} /> Role-Based Access Control</span></div>
          {views.map(([Icon, view], i) => <div key={view} className={`orbit-view orbit-${i + 1}`}><Icon size={19} /><span>{view}</span></div>)}
        </div>
        <p className="mx-auto mt-8 max-w-2xl text-center text-muted-foreground">Every user sees the information and actions appropriate to their role, while everyone works from the same project record.</p>
      </div>
    </section>
  );
};

const ProjectExample = () => {
  const [selected, setSelected] = useState(1);
  const activities = [
    { title: "Foundation", progress: 100, status: "Approved", tone: "green" },
    { title: "Ground Floor Columns", progress: 75, status: "In Progress", tone: "blue" },
    { title: "Electrical Rough-In", progress: 0, status: "Blocked", tone: "amber" },
  ];
  return (
    <section id="example" className="landing-section bg-slate-950 text-white scroll-mt-20">
      <div className="landing-container">
        <SectionHeading eyebrow="Live Project Example" title="Residential Complex C" description="Select an activity to see how status, reviews, and dependencies connect." />
        <div className="example-grid">
          <div className="space-y-3">{activities.map((item, i) => <button className={`project-activity ${selected === i ? "active" : ""}`} onClick={() => setSelected(i)} key={item.title}><span className={`activity-icon ${item.tone}`}>{item.status === "Blocked" ? <LockKeyhole size={18} /> : <CheckCircle2 size={18} />}</span><span><strong>{item.title}</strong><small>{item.status}</small></span><b>{item.progress}%</b></button>)}</div>
          <div className="project-detail">
            <div className="flex items-start justify-between"><div><small>Selected activity</small><h3>{activities[selected].title}</h3></div><span className={`status-pill ${activities[selected].tone}`}>{activities[selected].status}</span></div>
            <div className="progress-track"><i style={{ width: `${activities[selected].progress}%` }} /></div>
            {selected === 2 ? <div className="blocked-reason"><LockKeyhole size={20} /><span><small>Blocked because</small>Waiting for Ground Floor Columns approval</span></div> : <p className="latest-update">Latest update: “Ground floor column reinforcement is 75% complete.”</p>}
            <div className="project-metrics"><span><small>Consultant reviews</small><strong>2 Pending</strong></span><span><small>Open issues</small><strong>3</strong></span></div>
          </div>
        </div>
      </div>
    </section>
  );
};

const WhySection = () => {
  const problems = ["Calls and messages scatter field updates", "Teams may work from different information", "Approval history is difficult to trace", "Delays and dependencies surface too late"];
  const solutions = ["Mobile field updates", "Central project database", "Consultant approvals", "Dashboards + AI assistance"];
  return (
    <section className="landing-section">
      <div className="landing-container">
        <SectionHeading eyebrow="Why This Platform Exists" title="Replace fragmented communication with one workflow" />
        <div className="problem-solution">
          <div><span className="side-label problem"><AlertTriangle size={16} /> Today’s problem</span>{problems.map((x) => <p key={x}><XCircle size={16} />{x}</p>)}</div>
          <div className="transformation-arrow"><ArrowRight size={26} /></div>
          <div><span className="side-label solution"><CheckCircle2 size={16} /> Coordinated solution</span><h3>One digital construction workflow</h3>{solutions.map((x) => <p key={x}><CheckCircle2 size={16} />{x}</p>)}</div>
        </div>
      </div>
    </section>
  );
};

/* ── §23 Problem / Value ── */
const ProblemValue = () => (
  <section id="why" className="landing-section scroll-mt-20">
    <div className="landing-container">
      <SectionHeading
        eyebrow="The problem"
        title="Your project already produces the information. It just lives everywhere."
        description="Progress is agreed in a phone call, proven by a photo on someone's device, tracked in a spreadsheet, and approved in a message thread nobody can find two months later."
      />
      <div className="problem-split">
        <article className="problem-col scattered">
          <div className="section-kicker">Today</div>
          <h3 className="mt-2 text-xl font-extrabold">Scattered across tools</h3>
          <ul>
            {[
              "Progress agreed in WhatsApp messages",
              "Site photos stuck on personal phones",
              "Schedules in spreadsheets nobody updates",
              "Drawings emailed as attachments",
              "Approvals given verbally on site",
              "The owner asks what changed, and nobody can answer",
            ].map((item) => <li key={item}><XCircle size={15} />{item}</li>)}
          </ul>
        </article>
        <div className="comparison-middle"><ArrowRight size={22} /><span>One workspace</span></div>
        <article className="problem-col connected">
          <div className="section-kicker">With the platform</div>
          <h3 className="mt-2 text-xl font-extrabold">Connected and accountable</h3>
          <ul>
            {[
              "Progress recorded against the actual task",
              "Photos filed as evidence on the record they prove",
              "One schedule with real dependencies",
              "Drawings and IFC models versioned in place",
              "Approvals signed by the authorized person",
              "A dated answer to what changed since the last visit",
            ].map((item) => <li key={item}><Check size={15} />{item}</li>)}
          </ul>
        </article>
      </div>
    </div>
  </section>
);

/* ── §23 Core features ── */
const CoreFeatures = () => (
  <section id="features" className="landing-section bg-muted/25 scroll-mt-20">
    <div className="landing-container">
      <SectionHeading
        eyebrow="What you get"
        title="Everything a construction project has to keep track of"
        description="One workspace per project, with the modules your team already needs and the permissions your organization already has."
      />
      <div className="feature-grid">
        {[
          { icon: ClipboardList, title: "Projects & tasks", body: "Task boards per project with disciplines, assignees, priorities and review states." },
          { icon: CalendarClock, title: "Scheduling & Gantt", body: "Planned dates, dependencies, critical path and float, with rescheduling that tells you what moved." },
          { icon: FileText, title: "Site reports", body: "Daily reports with weather, workforce, equipment, delays and issues, prefilled from the scheduled visit." },
          { icon: Camera, title: "Field evidence", body: "Photos and submissions captured on site and attached to the task or issue they prove." },
          { icon: MessageSquareText, title: "Team communication", body: "Project conversations where an action-required message stays open until somebody answers it." },
          { icon: CircleUserRound, title: "Owner requests", body: "A simple form for the client, routed to the right discipline without exposing engineering internals." },
          { icon: CalendarClock, title: "Site visits", body: "Scheduled visits with participants, conflict detection, and a report waiting when the visit ends." },
          { icon: Layers3, title: "Documents & photo archive", body: "Drawings, documents and site photography filed against the project, searchable and filterable." },
          { icon: Building2, title: "IFC / BIM intelligence", body: "Versioned models checked against the tasks, disciplines and floors your project actually has." },
          { icon: TriangleAlert, title: "Issues & design changes", body: "Raise an issue on site; propose a design change that follows the real approval chain." },
          { icon: FileCheck2, title: "Approvals & reviews", body: "Consultant review per discipline or centralized, with the decision recorded against the work." },
          { icon: Bell, title: "Reminders & accountability", body: "Automatic reminders and escalation so waiting work does not quietly go stale." },
        ].map(({ icon, title, body }) => <IconCard key={title} icon={icon} title={title}><p>{body}</p></IconCard>)}
      </div>
    </div>
  </section>
);

/* ── §23 BIM / IFC ── */
const BimSection = () => (
  <section id="bim" className="landing-section scroll-mt-20">
    <div className="landing-container">
      <SectionHeading
        eyebrow="BIM / IFC"
        title="A model is only useful when it is checked against the real project"
        description="Uploading an IFC gives you an element count. Comparing it with your tasks, schedule, disciplines and issues tells you whether the model matches the job."
      />
      <div className="bim-stack">
        {[
          { icon: Layers3, label: "IFC model" },
          { icon: ClipboardList, label: "Tasks" },
          { icon: CalendarClock, label: "Schedule" },
          { icon: Gauge, label: "Progress" },
          { icon: TriangleAlert, label: "Issues" },
        ].map(({ icon: Icon, label }) => <div key={label} className="bim-input"><Icon size={19} />{label}</div>)}
      </div>
      <div className="bim-finding">
        <div className="section-kicker"><SearchCheck size={14} /> Example finding</div>
        <p className="mt-2">
          <strong>4 electrical installation tasks exist, but this IFC contains no electrical elements.</strong>{" "}
          The uploaded revision exposes none of the characteristic IFC classes for that discipline
          (IfcCableCarrierSegment, IfcLightFixture, IfcOutlet, IfcSwitchingDevice).
        </p>
        <small>
          Severity: Critical · Evidence: 4 matched tasks, matched terms “electrical” and “cable” ·
          Suggested action: confirm whether the discipline model was omitted from this export, or whether the wrong model was uploaded.
        </small>
      </div>
      <div className="statement-line"><ShieldCheck size={17} /><span>Findings are <strong>advisory</strong>. An engineer decides what happens next.</span></div>
    </div>
  </section>
);

/* ── §23 Accountability ── */
const AccountabilitySection = () => (
  <section id="accountability" className="landing-section bg-muted/25 scroll-mt-20">
    <div className="landing-container">
      <SectionHeading
        eyebrow="Accountability"
        title="Who did what, when, and who approved it"
        description="Construction disputes are settled with records. Every meaningful action leaves one."
      />
      <div className="accountability-grid">
        {[
          { icon: Activity, title: "Audit history", body: "Every task update, approval, request and model upload is written to an activity trail." },
          { icon: Check, title: "Acknowledgements", body: "Important messages track delivery, reading, acknowledgement and response per recipient." },
          { icon: FileCheck2, title: "Review chains", body: "Consultant decisions stay attached to the work they approved or rejected, with the reason." },
          { icon: Bell, title: "Automatic reminders", body: "Waiting requests escalate on a schedule you configure, with quiet hours and attempt limits." },
          { icon: UserCog, title: "Human authority", body: "Only an authorized person approves engineering work, including when the request arrives by voice." },
          { icon: Workflow, title: "Traceable decisions", body: "An owner request that becomes a design change keeps the link back to who asked and who approved." },
        ].map(({ icon: Icon, title, body }) => (
          <div key={title}><Icon size={19} /><strong className="mt-3">{title}</strong><p>{body}</p></div>
        ))}
      </div>
    </div>
  </section>
);

export const LandingPage = () => (
  <div className="landing-page">
    <section className="hero-section">
      <div className="blueprint-grid" />
      <div className="landing-container relative">
        <div className="hero-copy">
          <div className="section-kicker"><HardHat size={15} /> Built for construction teams</div>
          <h1>One connected workspace for<br /><span>construction execution</span></h1>
          <p>Plan the work, assign it, capture what actually happened on site, review it, approve it, and keep the record. Coordination, evidence, progress and accountability in one place — for contractors, consultants, engineers, project managers and owners.</p>
          <div className="hero-actions">
            <Link to={ROUTES.LOGIN} className="primary-cta">Open the platform <ArrowRight size={17} /></Link>
            <a href="#workflow" className="secondary-cta">See how it works <ArrowDown size={17} /></a>
          </div>
        </div>
        <div className="hero-scene" aria-label="A project floor plan alongside site progress and evidence">
          <div className="hero-panel">
            <h4>Residential Complex C · Floor plan</h4>
            <div className="hero-plan" aria-hidden="true"><i /><i /><i /><b>Ground floor</b></div>
          </div>
          <div className="hero-stack">
            <div className="hero-panel">
              <h4>Verified progress</h4>
              <div className="hero-progress">
                {[["Foundation concrete pour", "100%", 100], ["Structural framing", "62%", 62], ["Electrical rough-in", "18%", 18]].map(([label, value, width]) => (
                  <div key={label as string}><span>{label}</span><span>{value}</span><u><b style={{ width: `${width}%` }} /></u></div>
                ))}
              </div>
            </div>
            <div className="hero-panel">
              <h4>Latest from site</h4>
              <div className="mt-3 grid gap-2">
                <div className="hero-evidence"><Camera size={15} /><span>6 photos attached to <strong>TSK-005 Structural framing</strong></span></div>
                <div className="hero-evidence"><FileCheck2 size={15} /><span>Site report submitted, awaiting consultant review</span></div>
                <div className="hero-evidence"><TriangleAlert size={15} /><span>Issue raised in Zone B — routed to the civil engineer</span></div>
              </div>
            </div>
          </div>
        </div>
        <div className="hero-proof"><span><ShieldCheck size={17} /> Controlled approvals</span><span><Camera size={17} /> Evidence on the record</span><span><Workflow size={17} /> Traceable decisions</span></div>
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
      <div className="landing-container text-center"><div className="section-kicker">One connected workspace</div><h2>Run the project from<br />the site to the handover</h2><div className="final-flow">{["Plan", "Assign", "Execute", "Capture evidence", "Review", "Approve", "Report"].map((x, i, all) => <span key={x}>{x}{i < all.length - 1 && <ArrowRight size={17} />}</span>)}</div><p>For contractors, consultants, engineers, project managers and owners</p><div className="hero-actions"><Link to={ROUTES.LOGIN} className="primary-cta">Open the platform <ArrowRight size={17} /></Link><a href="#features" className="secondary-cta">See the modules <ArrowDown size={17} /></a></div></div>
    </section>
  </div>
);
