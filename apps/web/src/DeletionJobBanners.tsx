import { RefreshCw } from "lucide-react";
import type { DeletionJob } from "./api";

type DeletionJobBannersProps = {
  failedJobs: DeletionJob[];
  processingJobs: DeletionJob[];
  queuedJobs: DeletionJob[];
  onRetry: () => void;
  isRetrying: boolean;
};

export function DeletionJobBanners({
  failedJobs,
  processingJobs,
  queuedJobs,
  onRetry,
  isRetrying,
}: DeletionJobBannersProps) {
  return (
    <>
      {failedJobs.length ? (
        <div className="telegram-cleanup-banner failed" aria-live="polite" role="status">
          <div>
            <strong>Telegram cleanup failed for {failedJobs.length} file(s)</strong>
            <p>
              Trash is empty in TeleDrive, but these files are still in your Telegram channel.
              Check Telegram credentials in Setup, then retry cleanup.
            </p>
            <ul className="deletion-job-list compact">
              {failedJobs.slice(0, 5).map((job) => (
                <li key={job.id}>{job.lastError ?? job.status}</li>
              ))}
            </ul>
            <button
              className="tool-button"
              type="button"
              aria-label="Retry Telegram cleanup for failed files"
              disabled={isRetrying}
              onClick={onRetry}
            >
              {isRetrying ? "Retrying…" : "Retry Telegram cleanup"}
            </button>
          </div>
        </div>
      ) : null}
      {processingJobs.length ? (
        <div className="telegram-cleanup-banner" aria-live="polite" role="status">
          <RefreshCw size={16} className="spinning" aria-hidden="true" />
          <div>
            <strong>Removing from Telegram storage</strong>
            <p>
              {processingJobs.length} file
              {processingJobs.length === 1 ? "" : "s"} being removed from your storage channel.
            </p>
          </div>
        </div>
      ) : queuedJobs.length ? (
        <div className="telegram-cleanup-banner queued" aria-live="polite" role="status">
          <RefreshCw size={16} aria-hidden="true" />
          <div>
            <strong>Telegram cleanup queued</strong>
            <p>
              {queuedJobs.length} file
              {queuedJobs.length === 1 ? "" : "s"} waiting for background cleanup. The worker
              removes them from your storage channel automatically.
            </p>
          </div>
        </div>
      ) : null}
    </>
  );
}
