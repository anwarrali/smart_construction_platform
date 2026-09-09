import { useTranslation } from "react-i18next";
import { Lock, Play, Wrench } from "lucide-react";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import type { AgentDefinition, AgentRunResult } from "../../../types/agent";

/**
 * One agent, and whether this person may run it.
 *
 * The card shows the agent's *declared* contract rather than a marketing
 * description: what it is responsible for, the tools it is allowed to call, and
 * the permission that governs it. That is deliberate. These agents read project
 * data on the caller's behalf, and "which tools does it hold" is the question a
 * reviewer actually needs answered before trusting a finding — the Schedule Risk
 * Agent holding no document tools is the reason it cannot read a contract,
 * whatever it is asked.
 *
 * An agent the caller may not run is shown, disabled, with the permission it
 * needs. Hiding it would make the set of agents look different to different
 * people and leave nobody able to explain why.
 */
export const AgentCard = ({
  agent,
  runnable,
  isRunning,
  lastResult,
  onRun,
}: {
  agent: AgentDefinition;
  runnable: boolean;
  isRunning: boolean;
  lastResult?: AgentRunResult;
  onRun: () => void;
}) => {
  const { t } = useTranslation();

  return (
    <Card className="flex h-full flex-col" data-testid={`agent-${agent.name}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-base font-semibold">
            {t(`agents.name.${agent.name}`, { defaultValue: agent.title })}
          </h3>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            {t(`agents.responsibility.${agent.name}`, {
              defaultValue: agent.responsibility,
            })}
          </p>
        </div>
        {!runnable && (
          <Badge variant="neutral" size="sm">
            <Lock size={11} className="me-1" />
            {t("agents.notPermitted")}
          </Badge>
        )}
      </div>

      <div className="mt-4 rounded-lg bg-muted/40 p-3">
        <p className="flex items-center gap-1.5 text-xs font-semibold">
          <Wrench size={13} />
          {t("agents.toolsItHolds", { count: agent.allowedTools.length })}
        </p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {agent.allowedTools.map((tool) => (
            <code
              key={tool}
              className="rounded bg-background px-1.5 py-0.5 text-[11px] text-muted-foreground"
            >
              {tool}
            </code>
          ))}
        </div>
      </div>

      {lastResult && (
        <p className="mt-3 text-xs text-muted-foreground" role="status">
          {lastResult.ok
            ? t("agents.lastRunFound", {
                count: lastResult.findingCount,
                ms: lastResult.durationMs ?? 0,
              })
            : t("agents.lastRunFailed", {
                reason: lastResult.error ?? lastResult.errorCode ?? "",
              })}
        </p>
      )}

      <div className="mt-auto flex items-center justify-between gap-3 pt-4">
        <span className="text-xs text-muted-foreground">
          {runnable
            ? t("agents.governedBy", { permission: agent.permission })
            : t("agents.requiresPermission", { permission: agent.permission })}
        </span>
        <Button
          size="sm"
          variant={runnable ? "primary" : "outline"}
          disabled={!runnable || isRunning}
          isLoading={isRunning}
          onClick={onRun}
        >
          {!isRunning && <Play size={14} />}
          {isRunning ? t("agents.running") : t("agents.run")}
        </Button>
      </div>
    </Card>
  );
};
