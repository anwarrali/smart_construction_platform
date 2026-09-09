import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import toast from "react-hot-toast";
import { Bot, PlayCircle, RefreshCw, Zap, ZapOff } from "lucide-react";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import api from "../../../services/api";
import { errorMessage } from "../../../utils/errorMessage";
import { ErrorState, LoadingState } from "../../ifc/components/IFCShared";
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";
import type {
  AgentCatalogue,
  AgentRunRecord,
  AgentRunResult,
  AgentSubscriptions,
} from "../../../types/agent";
import { AgentCard } from "../components/AgentCard";
import { AgentRunHistory } from "../components/AgentRunHistory";

/**
 * The five project agents, as a place a person can actually go.
 *
 * The backend has had a complete agent layer — a registry, a tool-gated
 * runtime, an orchestrator, a run log and six endpoints — with no client of any
 * kind. This page is that client and nothing more: it adds no analysis, no
 * second review queue, and no notion of an agent the server does not already
 * declare.
 *
 * ## Three decisions worth stating
 *
 * **Findings are not shown here.** An agent stores its findings as `AIInsight`,
 * which is the same record the AI Intelligence page already lists, filters and
 * promotes into issues and tasks — with the human confirmation step that keeps
 * "no agent silently changes project data" true. Rendering findings again here
 * would split that queue in two and give a reviewer two places to resolve the
 * same row. A run reports how many it produced and links to where they live.
 *
 * **Running is offered per agent and once for all.** The orchestrated pass is
 * the one that matches how the backend actually governs a run: it decides which
 * agents should run, isolates each from the others, and reports ran / skipped /
 * failed separately. Skips are surfaced as their own outcome rather than folded
 * into failures, because "you do not hold this permission" and "the agent
 * broke" are different answers and the API is careful to distinguish them.
 *
 * **The automatic-analysis state is read from the server, not assumed.** Every
 * agent declares the events that would wake it, but whether those events
 * actually trigger anything is one operator switch. A page that showed the
 * subscription map without saying which of the two worlds it is describing
 * would be actively misleading.
 */
export const AgentsPage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const workspace = useProjectWorkspace();
  const params = useParams<{ projectId?: string }>();
  const projectId = workspace.projectId || params.projectId;

  const [catalogue, setCatalogue] = useState<AgentCatalogue | null>(null);
  const [runs, setRuns] = useState<AgentRunRecord[]>([]);
  const [subscriptions, setSubscriptions] = useState<AgentSubscriptions | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  /** Which agent is mid-run; "*" while an orchestrated pass is in flight. */
  const [busy, setBusy] = useState("");
  const [lastResults, setLastResults] = useState<Record<string, AgentRunResult>>({});

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setLoadError("");
    try {
      // The run log and the subscription map are secondary: a failure in either
      // must not cost the page its primary job, which is offering the agents.
      const [catalogueData, runsData, subscriptionData] = await Promise.all([
        api.agents.list(projectId),
        api.agents.runs(projectId).catch(() => [] as AgentRunRecord[]),
        api.agents.subscriptions(projectId).catch(() => null),
      ]);
      setCatalogue(catalogueData);
      setRuns(runsData);
      setSubscriptions(subscriptionData);
    } catch (error) {
      setLoadError(errorMessage(error, t("agents.loadFailed")));
    } finally {
      setLoading(false);
    }
  }, [projectId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const runnableNames = useMemo(
    () => new Set((catalogue?.available ?? []).map((agent) => agent.name)),
    [catalogue],
  );

  const agentTitles = useMemo(() => {
    const titles: Record<string, string> = {};
    for (const agent of catalogue?.catalogue ?? []) {
      titles[agent.name] = t(`agents.name.${agent.name}`, { defaultValue: agent.title });
    }
    return titles;
  }, [catalogue, t]);

  const runOne = async (agentName: string) => {
    if (!projectId) return;
    setBusy(agentName);
    try {
      const result = await api.agents.runOne(projectId, agentName);
      setLastResults((previous) => ({ ...previous, [agentName]: result }));
      toast.success(
        t("agents.runFinished", {
          agent: agentTitles[agentName] ?? agentName,
          count: result.findingCount,
        }),
      );
      setRuns(await api.agents.runs(projectId).catch(() => runs));
    } catch (error) {
      toast.error(errorMessage(error, t("agents.runFailed")));
    } finally {
      setBusy("");
    }
  };

  const runAll = async () => {
    if (!projectId) return;
    setBusy("*");
    try {
      const report = await api.agents.orchestrate(projectId);
      const results: Record<string, AgentRunResult> = {};
      for (const run of report.ran) results[run.agent] = run;
      setLastResults((previous) => ({ ...previous, ...results }));
      toast.success(
        t("agents.passFinished", {
          ran: report.agentsRun,
          skipped: report.agentsSkipped,
          failed: report.agentsFailed,
          count: report.findingCount,
        }),
      );
      // Skips are a normal outcome, but a silent one would leave somebody
      // wondering why an agent they can see did not run.
      for (const skip of report.skipped) {
        toast(`${agentTitles[skip.agent] ?? skip.agent}: ${skip.reason}`, { icon: "⏭️" });
      }
      setRuns(await api.agents.runs(projectId).catch(() => runs));
    } catch (error) {
      toast.error(errorMessage(error, t("agents.passFailed")));
    } finally {
      setBusy("");
    }
  };

  // Same as every other project-scoped page: this route only exists inside a
  // workspace, so there is nothing to pick between here.
  if (!projectId) return <Card>{t("empty.selectProject")}</Card>;
  if (loading) return <LoadingState label={t("agents.loading")} />;
  if (loadError) return <ErrorState message={loadError} onRetry={() => void load()} />;

  const agents = catalogue?.catalogue ?? [];
  const totalFindings = Object.values(lastResults).reduce(
    (sum, result) => sum + (result.findingCount ?? 0),
    0,
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold">
            <Bot /> {t("agents.title")}
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            {t("agents.subtitle")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => void load()} disabled={Boolean(busy)}>
            <RefreshCw size={15} /> {t("agents.refresh")}
          </Button>
          <Button
            onClick={() => void runAll()}
            disabled={Boolean(busy) || runnableNames.size === 0}
            isLoading={busy === "*"}
          >
            {busy !== "*" && <PlayCircle size={15} />}
            {t("agents.runAll", { count: runnableNames.size })}
          </Button>
        </div>
      </div>

      {subscriptions && (
        <Card padding="sm">
          <div className="flex flex-wrap items-center gap-3">
            <Badge variant={subscriptions.automaticAnalysisEnabled ? "success" : "neutral"}>
              {subscriptions.automaticAnalysisEnabled ? <Zap size={12} className="me-1" /> : <ZapOff size={12} className="me-1" />}
              {subscriptions.automaticAnalysisEnabled
                ? t("agents.automaticOn")
                : t("agents.automaticOff")}
            </Badge>
            <p className="text-sm text-muted-foreground">{subscriptions.note}</p>
          </div>
        </Card>
      )}

      {runnableNames.size === 0 && (
        <Card>
          <p className="py-4 text-center text-sm text-muted-foreground">
            {t("agents.noneRunnable")}
          </p>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {agents.map((agent) => (
          <AgentCard
            key={agent.name}
            agent={agent}
            runnable={runnableNames.has(agent.name)}
            isRunning={busy === agent.name || busy === "*"}
            lastResult={lastResults[agent.name]}
            onRun={() => void runOne(agent.name)}
          />
        ))}
      </div>

      {totalFindings > 0 && (
        <Card padding="sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm">
              {t("agents.findingsStored", { count: totalFindings })}
            </p>
            <Button
              size="sm"
              variant="outline"
              onClick={() => navigate(workspace.path("ai-intelligence"))}
            >
              {t("agents.openReviewQueue")}
            </Button>
          </div>
        </Card>
      )}

      <section>
        <h2 className="mb-3 text-lg font-semibold">{t("agents.runHistory")}</h2>
        <AgentRunHistory runs={runs} agentTitles={agentTitles} />
      </section>
    </div>
  );
};

export default AgentsPage;
