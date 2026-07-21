import { EmptyState } from "../components/ui/EmptyState";

export function Jobs() {
  return (
    <EmptyState
      icon="logs"
      title="No job history yet"
      description="Scheduled jobs (daily send, report ingest, weekly/monthly reports) will appear here once Celery workers are running in Phase 2. Failed jobs will be highlighted for manual re-run."
    />
  );
}
