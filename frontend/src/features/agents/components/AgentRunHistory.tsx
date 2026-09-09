import { useTranslation } from "react-i18next";
import { CircleAlert, CircleCheck, Hand, Zap } from "lucide-react";

import { Badge } from "../../../components/ui/Badge";
import { Card } from "../../../components/ui/Card";
import { timeAgo } from "../../../utils/date";
import type { AgentRunRecord } from "../../../types/agent";

/**
 * The run log: what ran, why, what it looked at, and what it produced.
 *
 * The tool calls are shown, collapsed, because they are the whole basis on
 * which a finding can be judged. An agent that reports "nothing found" having
 * been refused every tool it asked for has not found nothing — it could not
 * look, and only the call list distinguishes the two.
 *
 * Trigger is rendered as a distinct thing from status for the same reason the
 * backend records them separately: a run the system started on a project
 * manager's authority is a different claim from one that person asked for, and
 * a log that blurred them would misattribute every automatic finding.
 */

const STATUS_VARIANT: Record<string, "success" | "danger" | "neutral"> = {
  SUCCEEDED: "success",
  FAILED: "danger",
};

export const AgentRunHistory = ({
  runs,
  agentTitles,
}: {
  runs: AgentRunRecord[];
  agentTitles: Record<string, string>;
}) => {
  const { t, i18n } = useTranslation();
  const locale = i18n.language?.startsWith("ar") ? "ar" : "en";

  if (!runs.length) {
    return (
      <Card>
        <div className="py-8 text-center">
          <p className="font-semibold">{t("agents.noRunsYet")}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("agents.noRunsYetHint")}
          </p>
        </div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {runs.map((run) => {
        const failed = run.status !== "SUCCEEDED";
        const refused = run.toolCalls.filter((call) => !call.ok);
        return (
          <Card key={run.id} padding="sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">
                    {agentTitles[run.agent] ?? run.agent}
                  </span>
                  <Badge variant={STATUS_VARIANT[run.status] ?? "neutral"} size="sm">
                    {failed ? <CircleAlert size={11} className="me-1" /> : <CircleCheck size={11} className="me-1" />}
                    {t(`agents.status.${run.status}`, { defaultValue: run.status })}
                  </Badge>
                  <Badge variant="info" size="sm">
                    {run.triggerType === "EVENT" ? <Zap size={11} className="me-1" /> : <Hand size={11} className="me-1" />}
                    {t(`agents.trigger.${run.triggerType}`, { defaultValue: run.triggerType })}
                  </Badge>
                </div>
                {run.triggerReason && (
                  <p className="mt-1 text-xs text-muted-foreground">{run.triggerReason}</p>
                )}
                {run.error && (
                  <p className="mt-1 text-xs text-state-overdue">{run.error}</p>
                )}
              </div>
              <div className="text-end text-xs text-muted-foreground">
                <p>{run.createdAt ? timeAgo(run.createdAt, locale) : ""}</p>
                <p className="tabular-nums">
                  {t("agents.findingsAndDuration", {
                    count: run.findingCount,
                    ms: run.durationMs ?? 0,
                  })}
                </p>
              </div>
            </div>

            {run.toolCalls.length > 0 && (
              <details className="mt-3 rounded border p-2 text-xs">
                <summary className="cursor-pointer font-medium">
                  {t("agents.toolCallsMade", {
                    count: run.toolCalls.length,
                    refused: refused.length,
                  })}
                </summary>
                <ul className="mt-2 flex flex-col gap-1">
                  {run.toolCalls.map((call, index) => (
                    <li
                      key={`${run.id}-${call.tool}-${index}`}
                      className="flex items-center justify-between gap-2"
                    >
                      <code className="truncate">{call.tool}</code>
                      <span
                        className={
                          call.ok ? "text-muted-foreground" : "text-state-overdue"
                        }
                      >
                        {call.ok ? t("agents.callOk") : call.errorCode}
                      </span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </Card>
        );
      })}
    </div>
  );
};
