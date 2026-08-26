/**
 * The engineer-facing home for the voice assistant.
 *
 * Two things live here that the panel deliberately does not own: the project
 * the panel acts within, and the day's accumulated confirmed updates. The
 * second is the hand-off to reporting — it reads the same structured record a
 * future report agent will consume, so what the engineer sees here and what
 * the report is built from cannot drift apart.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Card } from "../../../components/ui/Card";
import { useRealtimeRefresh } from "../../../hooks/useRealtimeRefresh";
import api from "../../../services/api";
import { errorMessage } from "../../../utils/errorMessage";
import type { VoiceReportReadiness } from "../../../types/voice";
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";
import { VoiceAssistantPanel } from "../components/VoiceAssistantPanel";

export const VoiceAssistantPage = () => {
  const { t } = useTranslation();
  const workspace = useProjectWorkspace();
  const [readiness, setReadiness] = useState<VoiceReportReadiness | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!workspace.projectId) return;
    try {
      setReadiness(await api.voice.reportReadiness(workspace.projectId));
      setError("");
    } catch (caught: unknown) {
      setError(errorMessage(caught, t("voiceAssistant.readinessFailed")));
    }
  }, [t, workspace.projectId]);

  useEffect(() => { void load(); }, [load]);

  // The same event a confirmed voice update publishes. No second realtime
  // mechanism, and no polling.
  useRealtimeRefresh(["TASK_UPDATED", "TASK_CREATED", "ISSUE_CREATED"], load, {
    projectId: workspace.projectId,
  });

  if (!workspace.projectId) {
    return <Card>{t("voiceAssistant.selectProject")}</Card>;
  }

  return (
    <div className="space-y-4">
      <VoiceAssistantPanel projectId={workspace.projectId} onExecuted={() => void load()} />

      <Card>
        <h3 className="text-base font-semibold">{t("voiceAssistant.todaySummary")}</h3>
        {error ? <p className="mt-2 text-sm text-red-600">{error}</p> : null}
        {readiness && readiness.updateCount > 0 ? (
          <>
            <p className="mt-1 text-sm opacity-70">
              {t("voiceAssistant.todayCounts", {
                updates: readiness.updateCount,
                tasks: readiness.taskCount,
              })}
            </p>
            <ul className="mt-3 space-y-2">
              {readiness.updates.map((update, index) => (
                <li key={`${update.voiceCommandId}-${index}`} className="rounded-lg border p-2 text-sm">
                  <span className="font-medium">
                    {update.taskCode ? `${update.taskCode} — ${update.taskName}` : update.actionType}
                  </span>
                  {update.afterState ? (
                    <span className="ms-2 text-xs opacity-70">
                      {String(update.afterState.status ?? "")}
                      {typeof update.afterState.progressPercentage === "number"
                        ? ` · ${update.afterState.progressPercentage}%`
                        : ""}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
            {readiness.ready ? (
              <p className="mt-3 text-sm text-emerald-600">{t("voiceAssistant.reportReady")}</p>
            ) : null}
          </>
        ) : (
          <p className="mt-1 text-sm opacity-70">{t("voiceAssistant.noUpdatesToday")}</p>
        )}
      </Card>
    </div>
  );
};
