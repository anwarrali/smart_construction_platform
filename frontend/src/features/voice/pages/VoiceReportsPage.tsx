import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import toast from "react-hot-toast";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Input } from "../../../components/ui/Input";
import api from "../../../services/api";
import type { FieldSubmission } from "../../../types/fieldSubmission";
import type { Task } from "../../../types/task";
import type { VoiceCommand } from "../../../types/voice";
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";

interface ReportRow {
  submission: FieldSubmission;
  task: Task;
  voice?: VoiceCommand;
}

const voiceAnalysisId = (submission: FieldSubmission) => {
  if (!submission.voiceMetadata) return undefined;
  try {
    const value = JSON.parse(submission.voiceMetadata) as { analysis_id?: string };
    return value.analysis_id;
  } catch {
    return undefined;
  }
};

export const VoiceReportsPage = () => {
  const { t } = useTranslation();
  const workspace = useProjectWorkspace();
  const [rows, setRows] = useState<ReportRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");
  const [query, setQuery] = useState("");
  const [discipline, setDiscipline] = useState("");
  const [intent, setIntent] = useState("");
  const [reviewing, setReviewing] = useState<string>();
  const [progress, setProgress] = useState<Record<string, number>>({});
  const [reason, setReason] = useState<Record<string, string>>({});
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  const [audioUrls, setAudioUrls] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    if (!workspace.projectId) return;
    setLoading(true);
    try {
      const submissions = await api.fieldSubmissions.pending(workspace.projectId);
      const values = await Promise.all(submissions.map(async (submission) => {
        const id = voiceAnalysisId(submission);
        const [task, voice] = await Promise.all([
          api.tasks.getById(submission.taskId),
          id ? api.voice.getCommand(id).catch(() => undefined) : Promise.resolve(undefined),
        ]);
        return { submission, task, voice };
      }));
      setRows(values);
      setProgress(Object.fromEntries(values.map(({ submission, task, voice }) => {
        const suggestion = voice?.actionDrafts.find((item) =>
          item.actionType === "UPDATE_TASK_PROGRESS"
        );
        const payload = suggestion?.userEditedPayload || suggestion?.extractedPayload;
        return [
          submission.id,
          Number(payload?.progressPercentage ?? task.progressPercentage),
        ];
      })));
    } catch (error: any) {
      toast.error(errorMessage(error, "Unable to load pending voice reports."));
    } finally {
      setLoading(false);
    }
  }, [workspace.projectId]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => () => {
    Object.values(audioUrls).forEach((url) => URL.revokeObjectURL(url));
  }, [audioUrls]);

  const visible = useMemo(() => {
    const value = query.trim().toLowerCase();
    if (!value) return rows;
    return rows.filter(({ submission, task, voice }) => {
      const matchesQuery = !value ||
        `${submission.worker.fullName} ${task.taskCode} ${task.name} ${task.discipline || ""}`
          .toLowerCase().includes(value);
      const matchesDiscipline = !discipline || task.discipline === discipline;
      const matchesIntent = !intent || voice?.actionDrafts.some((item) => item.actionType === intent);
      return matchesQuery && matchesDiscipline && matchesIntent;
    });
  }, [query, discipline, intent, rows]);

  const run = async (id: string, action: () => Promise<unknown>, message: string) => {
    setBusyId(id);
    try {
      await action();
      toast.success(message);
      await load();
    } catch (error: any) {
      toast.error(errorMessage(error, "The review could not be saved."));
    } finally {
      setBusyId("");
    }
  };

  const playAudio = async (row: ReportRow) => {
    const id = row.voice?.id;
    if (!id || audioUrls[id]) return;
    try {
      const blob = await api.voice.getAudio(id);
      setAudioUrls((current) => ({ ...current, [id]: URL.createObjectURL(blob) }));
    } catch {
      toast.error("Audio is no longer available or you do not have access.");
    }
  };

  if (!workspace.projectId) return <Card>{t("voiceReports.select_a_project_to_review_voice_reports")}</Card>;

  return <div className="page-container space-y-5">
    <div>
      <h1 className="text-2xl font-bold">{t("voiceReports.voice_assistant_review_inbox")}</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        {t("voiceReports.review_worker_reports_evidence_and")}
      </p>
    </div>
    <Card>
      <div className="grid gap-3 md:grid-cols-3">
        <Input label={t("voiceReports.worker_task_or_code")} value={query}
          onChange={(event) => setQuery(event.target.value)} placeholder={t("voiceReports.search_reports")} />
        <label className="text-sm">{t("voiceReports.discipline")}
          <select className="mt-1 w-full rounded-md border bg-background px-3 py-2" value={discipline}
            onChange={(event) => setDiscipline(event.target.value)}>
            <option value="">{t("voiceReports.all_disciplines")}</option>
            {[...new Set(rows.map((row) => row.task.discipline).filter(Boolean))].map((value) =>
              <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <label className="text-sm">{t("voiceReports.intent")}
          <select className="mt-1 w-full rounded-md border bg-background px-3 py-2" value={intent}
            onChange={(event) => setIntent(event.target.value)}>
            <option value="">{t("voiceReports.all_intents")}</option>
            <option value="CREATE_FIELD_SUBMISSION">{t("voiceReports.worker_field_report")}</option>
            <option value="CREATE_ISSUE">{t("voiceReports.issue")}</option>
            <option value="UPDATE_TASK_PROGRESS">{t("voiceReports.progress_update")}</option>
          </select>
        </label>
      </div>
    </Card>
    {loading && <Card className="p-10 text-center text-muted-foreground">{t("voiceReports.loading_voice_reports")}</Card>}
    {!loading && visible.map((row) => {
      const { submission, task, voice } = row;
      const isReviewing = reviewing === submission.id;
      const suggested = progress[submission.id] ?? task.progressPercentage;
      return <Card key={submission.id} className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-semibold">{submission.worker.fullName}</p>
            <p className="text-sm text-muted-foreground">
              {task.taskCode} · {task.name} · {new Date(submission.createdAt).toLocaleString()}
            </p>
          </div>
          <div className="flex gap-2">
            {voice && <Badge variant="info">{t("voiceReports.voice_report")}</Badge>}
            <Badge variant="warning">{t("voiceReports.needs_review")}</Badge>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("voiceReports.worker_report")}</p>
            <p className="mt-2 whitespace-pre-wrap text-sm">{submission.description || "No written summary."}</p>
            {voice?.rawTranscript && <>
              <p className="mt-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("voiceReports.original_transcript")}</p>
              <p dir="auto" className="mt-2 whitespace-pre-wrap rounded bg-muted/30 p-3 text-sm">{voice.rawTranscript}</p>
            </>}
            {voice?.normalizedTranscript && voice.normalizedTranscript !== voice.rawTranscript && <>
              <p className="mt-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("voiceReports.english_summary")}</p>
              <p className="mt-2 whitespace-pre-wrap text-sm">{voice.normalizedTranscript}</p>
            </>}
            {voice && <div className="mt-3">
              {!audioUrls[voice.id]
                ? <Button variant="outline" onClick={() => playAudio(row)}>{t("voiceReports.load_secure_audio")}</Button>
                : <audio className="w-full" controls src={audioUrls[voice.id]} />}
            </div>}
          </div>
          <div className="rounded-lg border p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("voiceReports.official_task_comparison")}</p>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-muted-foreground">{t("voiceReports.current_status")}</dt><dd className="font-medium">{task.status.replaceAll("_", " ")}</dd></div>
              <div><dt className="text-muted-foreground">{t("voiceReports.current_progress")}</dt><dd className="font-medium">{task.progressPercentage}%</dd></div>
              <div><dt className="text-muted-foreground">{t("voiceReports.suggested_progress")}</dt><dd className="font-medium">{suggested}%</dd></div>
              <div><dt className="text-muted-foreground">{t("voiceReports.ai_confidence")}</dt><dd>{voice?.actionDrafts[0] ? `${Math.round(voice.actionDrafts[0].confidence * 100)}%` : "—"}</dd></div>
            </dl>
            {voice?.actionDrafts.flatMap((item) => item.warnings).map((warning) =>
              <p key={warning} className="mt-2 rounded bg-wash-review p-2 text-xs text-state-review">{warning}</p>
            )}
            {voice?.actionDrafts.flatMap((item) => item.requiredEvidence).map((requirement) =>
              <p key={requirement} className="mt-2 rounded bg-wash-progress p-2 text-xs text-state-progress">Required evidence: {requirement.replaceAll(":", " · ")}</p>
            )}
          </div>
        </div>

        {submission.photos.length > 0 && <div className="grid grid-cols-3 gap-2 md:grid-cols-6">
          {submission.photos.map((photo) =>
            <a key={photo.id} href={photo.attachment.fileUrl} target="_blank" rel="noreferrer">
              <img className="aspect-square w-full rounded border object-cover" src={photo.attachment.fileUrl} alt={photo.attachment.originalFilename} />
            </a>
          )}
        </div>}

        {isReviewing && <div className="rounded-lg border border-primary/30 bg-primary/5 p-4">
          <h2 className="font-semibold">{t("voiceReports.second_confirmation_verify_and_apply")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">The same task permissions, dependency rules, workflow locks, and stale-data check will run again.</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Input label={t("voiceReports.official_progress")} type="number" min="0" max="100"
              value={suggested}
              onChange={(event) => setProgress((current) => ({ ...current, [submission.id]: Number(event.target.value) }))} />
            <Input label={t("voiceReports.engineer_note")} value={reason[submission.id] || ""}
              onChange={(event) => setReason((current) => ({ ...current, [submission.id]: event.target.value }))} />
          </div>
          <label className="mt-3 flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={Boolean(confirmed[submission.id])}
              onChange={(event) => setConfirmed((current) => ({ ...current, [submission.id]: event.target.checked }))} />
            I reviewed the old and new task values and explicitly authorize this official update.
          </label>
          <div className="mt-4 flex gap-2">
            <Button disabled={!confirmed[submission.id] || busyId === submission.id}
              onClick={() => run(
                submission.id,
                () => api.fieldSubmissions.verifyAndApply(submission.id, {
                  progressPercentage: suggested,
                  expectedTaskUpdatedAt: task.updatedAt,
                  comment: reason[submission.id] || undefined,
                  correctionConfirmed: suggested < task.progressPercentage,
                }),
                "Evidence verified and the authorized task update was applied.",
              )}>{t("voiceReports.confirm_and_apply")}</Button>
            <Button variant="outline" onClick={() => setReviewing(undefined)}>{t("voiceReports.cancel")}</Button>
          </div>
        </div>}

        <div className="flex flex-wrap gap-2 border-t pt-4">
          <Button disabled={busyId === submission.id}
            onClick={() => run(submission.id, () => api.fieldSubmissions.verify(submission.id), "Evidence verified. The task was not changed.")}>
            {t("voiceReports.verify_evidence_only")}
          </Button>
          <Button variant="outline" onClick={() => setReviewing(submission.id)}>
            {t("voiceReports.verify_and_apply_suggested_update")}
          </Button>
          <Input className="min-w-64 flex-1" value={reason[submission.id] || ""}
            onChange={(event) => setReason((current) => ({ ...current, [submission.id]: event.target.value }))}
            placeholder={t("voiceReports.required_reason_for_resubmission")} />
          <Button variant="outline" disabled={(reason[submission.id] || "").trim().length < 3 || busyId === submission.id}
            onClick={() => run(submission.id, () => api.fieldSubmissions.reject(submission.id, reason[submission.id].trim()), "Worker was asked to resubmit.")}>
            {t("voiceReports.reject_request_resubmission")}
          </Button>
        </div>
      </Card>;
    })}
    {!loading && !visible.length && <Card className="p-10 text-center text-muted-foreground">{t("voiceReports.no_pending_worker_voice_reports_match")}</Card>}
  </div>;
};
