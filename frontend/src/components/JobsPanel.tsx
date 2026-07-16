import { CheckCircle2, CircleX, Clock3, Download, LoaderCircle, RefreshCw, Trash2 } from "lucide-react";
import type { MessageKey } from "../i18n";
import type { Locale, TrackedJob } from "../types";

interface JobsPanelProps {
  jobs: TrackedJob[];
  locale: Locale;
  busyJob: string | null;
  onDownload: (job: TrackedJob) => void;
  onRefresh: (jobId: string) => void;
  onClearFinished: () => void;
  t: (key: MessageKey) => string;
}

const terminal = new Set(["succeeded", "failed"]);

export function JobsPanel({ jobs, locale, busyJob, onDownload, onRefresh, onClearFinished, t }: JobsPanelProps) {
  const hasFinished = jobs.some((job) => job.status && terminal.has(job.status.status));
  return (
    <section className="jobs-panel" aria-labelledby="jobs-heading">
      <div className="section-heading inline-heading">
        <div>
          <span className="eyebrow">ASYNC</span>
          <h2 id="jobs-heading">{t("jobs")}</h2>
        </div>
        {hasFinished && (
          <button className="button ghost compact" type="button" onClick={onClearFinished}>
            <Trash2 size={15} /> {t("clearFinished")}
          </button>
        )}
      </div>
      {jobs.length === 0 ? (
        <div className="empty-jobs"><Clock3 size={23} /><p>{t("noJobs")}</p></div>
      ) : (
        <div className="job-list">
          {jobs.map((job) => {
            const status = job.status?.status ?? "queued";
            return (
              <article className="job-card" key={job.jobId}>
                <div className={`job-state ${status}`}>
                  {status === "succeeded" ? <CheckCircle2 /> : status === "failed" ? <CircleX /> : <LoaderCircle className={status === "running" ? "spin" : ""} />}
                </div>
                <div className="job-body">
                  <div className="job-title">
                    <strong>{job.taskName === "all" ? t("all") : t("invisible")}</strong>
                    <span className={`pill ${status}`}>{t(status)}</span>
                  </div>
                  <code>{job.jobId}</code>
                  <div className="progress-track" aria-label={`${t("progress")} ${job.status?.progress ?? 0}%`}>
                    <i style={{ width: `${job.status?.progress ?? 0}%` }} />
                  </div>
                  <div className="job-meta">
                    <span>{job.status?.message ?? job.pollingError ?? new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(job.createdAt))}</span>
                    <span>{job.status?.progress ?? 0}%</span>
                  </div>
                  {job.status?.error && <p className="job-error">{String(job.status.error.message ?? job.status.error.code ?? t("requestFailed"))}</p>}
                </div>
                <div className="job-actions">
                  {status === "succeeded" ? (
                    <button className="icon-button" type="button" disabled={busyJob === job.jobId} onClick={() => onDownload(job)} aria-label={t("download")}>
                      <Download size={17} />
                    </button>
                  ) : (
                    <button className="icon-button" type="button" onClick={() => onRefresh(job.jobId)} aria-label={t("retryStatus")}>
                      <RefreshCw size={17} />
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
