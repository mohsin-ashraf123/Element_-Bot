import { useEffect, useState } from "react";
import clsx from "clsx";
import { Avatar } from "../components/ui/Avatar";
import { Icon } from "../components/Icon";
import { getPerformance, type PerformanceScope, type PerformanceRow, type PerformanceView } from "../lib/api";

const SCOPES: { id: PerformanceScope; label: string }[] = [
  { id: "today", label: "Today" },
  { id: "week", label: "This week" },
  { id: "month", label: "This month" },
];

function outcomeLabel(outcome: string, onTime: boolean): string {
  if (outcome === "missed") return "Awaiting";
  if (!onTime) return "Late";
  if (outcome === "clean") return "Clean";
  if (outcome === "has_issues") return "Suggestion";
  return "Submitted";
}

function scopedMeta(scope: PerformanceScope, row: PerformanceRow): string {
  if (scope === "today") {
    const status = outcomeLabel(row.outcome, row.on_time);
    return row.pair_context ? `${status} · Pair: ${row.pair_context}` : status;
  }
  const days = `${row.completed_days ?? 0}/${row.eligible_days ?? 0} days`;
  const onTime = `${row.on_time_rate ?? 0}% on-time`;
  const streak = row.current_streak ? ` · streak ${row.current_streak}` : "";
  return `${days} · ${onTime}${streak}`;
}

function scopedScore(scope: PerformanceScope, row: PerformanceRow): string {
  if (scope === "today") {
    return row.power_score > 0 ? String(row.power_score) : "—";
  }
  const eligible = row.eligible_days ?? 0;
  if (eligible === 0) return "—";
  return `${row.completed_days ?? 0}/${eligible}`;
}

function statsTag(scope: PerformanceScope, stats: PerformanceView["stats"]): string {
  if (scope === "today") {
    return `${stats.completed}/${stats.total} completed`;
  }
  const eligible = stats.eligible ?? 0;
  const completed = stats.completed ?? 0;
  return `${completed}/${eligible} member-days`;
}

export function Performance() {
  const [scope, setScope] = useState<PerformanceScope>("today");
  const [view, setView] = useState<PerformanceView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getPerformance(scope)
      .then((data) => {
        setView(data);
        setError(null);
      })
      .catch((err: unknown) => {
        setView(null);
        const status =
          err && typeof err === "object" && "response" in err
            ? (err as { response?: { status?: number } }).response?.status
            : undefined;
        setError(
          status === 404
            ? "Performance API not available — restart the backend server, then refresh."
            : "Could not load performance data. Check that the backend is running."
        );
      })
      .finally(() => setLoading(false));
  }, [scope]);

  const empty = !loading && !error && !view?.attendance?.length;

  return (
    <div className="card reveal">
      <div className="cap cap-wrap">
        <div className="cap-main">
          <Icon name="chart" size={16} style={{ color: "var(--accent)" }} />
          {view?.period_label ?? "Performance"}
          {view?.stats ? <span className="tag">{statsTag(scope, view.stats)}</span> : null}
        </div>
        <div className="pillbtns perf-scope">
          {SCOPES.map((s) => (
            <button
              key={s.id}
              type="button"
              className={clsx("pillbtn", scope === s.id && "on")}
              onClick={() => setScope(s.id)}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p className="analysis-summary">Loading…</p>
      ) : error ? (
        <p style={{ color: "var(--red)", fontSize: 13, lineHeight: 1.55, margin: 0 }}>{error}</p>
      ) : empty ? (
        <p style={{ color: "var(--text3)", fontSize: 13, lineHeight: 1.55, margin: 0 }}>
          {scope === "today"
            ? "Per-member completion appears here once today's room messages are analyzed."
            : "No performance records for this period yet — data fills in as daily reports are tracked."}
        </p>
      ) : (
        <>
          {view?.summary ? <p className="analysis-summary">{view.summary}</p> : null}
          <div className="rank-list">
            {view?.attendance.map((row) => (
              <div className="rank-row" key={row.member_id}>
                <Avatar name={row.name} seed={row.name} mini />
                <div className="rank-body">
                  <div className="rank-name">{row.name}</div>
                  <div className="rank-meta">{scopedMeta(scope, row)}</div>
                  {row.suggestion_summary ? (
                    <div className="rank-reason">{row.suggestion_summary}</div>
                  ) : null}
                </div>
                <div className="rank-score">{scopedScore(scope, row)}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
