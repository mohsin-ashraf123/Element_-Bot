import { useEffect, useState } from "react";
import { Icon } from "../components/Icon";
import {
  generateReport,
  getReports,
  type SavedReport,
} from "../lib/api";

export function Reports() {
  const [rows, setRows] = useState<SavedReport[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState<"weekly" | "monthly" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  const load = () => {
    setLoading(true);
    getReports()
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const runGenerate = async (period: "weekly" | "monthly") => {
    setGenerating(period);
    setError(null);
    try {
      const report = await generateReport(period);
      setRows((prev) => {
        const rest = prev.filter((r) => r.id !== report.id);
        return [report, ...rest];
      });
      setExpanded(report.id);
    } catch (e: unknown) {
      const msg =
        e && typeof e === "object" && "response" in e
          ? String((e as { response?: { data?: { detail?: string } } }).response?.data?.detail)
          : "Report generation failed";
      setError(msg || "Report generation failed");
    } finally {
      setGenerating(null);
    }
  };

  return (
    <div className="grid g2">
      <div className="card reveal">
        <div className="cap">
          <Icon name="report" size={16} style={{ color: "var(--accent)" }} />
          Generate scoped report
        </div>
        <p style={{ color: "var(--text2)", fontSize: 13, lineHeight: 1.55, margin: "0 0 16px" }}>
          AI reads pre-computed metrics and member suggestions from the database — scoped weekly
          or monthly — then saves the structured analysis. Set your OpenRouter key in Settings
          first.
        </p>
        {error ? (
          <div className="auth-error" style={{ marginBottom: 12 }}>
            <Icon name="warn" size={14} />
            {error}
          </div>
        ) : null}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button
            className="btn primary"
            type="button"
            disabled={!!generating}
            onClick={() => runGenerate("weekly")}
          >
            {generating === "weekly" ? "Generating…" : "Generate weekly"}
          </button>
          <button
            className="btn ghost"
            type="button"
            disabled={!!generating}
            onClick={() => runGenerate("monthly")}
          >
            {generating === "monthly" ? "Generating…" : "Generate monthly"}
          </button>
        </div>
      </div>

      <div className="card reveal">
        <div className="cap">
          <Icon name="hist" size={16} style={{ color: "var(--accent)" }} />
          Saved reports
          <span className="tag gray">{rows.length}</span>
        </div>
        {loading ? (
          <div style={{ color: "var(--text3)", fontSize: 13, padding: "12px 4px" }}>Loading…</div>
        ) : rows.length === 0 ? (
          <div style={{ color: "var(--text3)", fontSize: 13, padding: "12px 4px" }}>
            No reports yet. Generate a weekly or monthly report above — it will be saved here with
            AI analysis.
          </div>
        ) : (
          <div className="rank-list">
            {rows.map((r) => {
              const ai = r.ai_analysis || {};
              const open = expanded === r.id;
              return (
                <div className="rank-row" key={r.id} style={{ flexDirection: "column" }}>
                  <div
                    style={{ display: "flex", alignItems: "flex-start", gap: 12, width: "100%" }}
                  >
                    <div className="rank-num">{r.period_type === "weekly" ? "W" : "M"}</div>
                    <div className="rank-body" style={{ cursor: "pointer" }} onClick={() => setExpanded(open ? null : r.id)}>
                      <div className="rank-name">
                        {r.period_label}
                        <span className="tag gray" style={{ marginLeft: 8 }}>
                          {r.narrative_source === "llm" ? "AI" : "Template"}
                        </span>
                      </div>
                      <div className="rank-meta">
                        {r.period_type} · {r.generated_at ? new Date(r.generated_at).toLocaleString() : "—"}
                        {r.ingestion_live ? " · live metrics" : " · limited data"}
                      </div>
                      <div className="rank-reason">{r.narrative}</div>
                      {r.narrative_source === "template" && r.llm_error ? (
                        <div
                          style={{
                            marginTop: 8,
                            fontSize: 12,
                            color: "var(--orange)",
                            fontWeight: 500,
                          }}
                        >
                          {r.llm_error}
                        </div>
                      ) : null}
                    </div>
                  </div>
                  {open && ai.executive_summary ? (
                    <div style={{ paddingLeft: 38, width: "100%" }}>
                      {ai.team_highlights?.length ? (
                        <div style={{ marginTop: 10 }}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--green)" }}>
                            Highlights
                          </div>
                          <ul style={{ margin: "6px 0", paddingLeft: 18, fontSize: 12.5 }}>
                            {ai.team_highlights.map((h: string) => (
                              <li key={h}>{h}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                      {ai.top_suggestions?.length ? (
                        <div style={{ marginTop: 10 }}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--orange)" }}>
                            Top suggestions
                          </div>
                          {ai.top_suggestions.map((s: { rank: number; member: string; summary: string; why_powerful?: string }) => (
                            <div key={s.rank} style={{ fontSize: 12.5, marginTop: 6 }}>
                              <b>#{s.rank} {s.member}</b> — {s.summary}
                              {s.why_powerful ? (
                                <div style={{ color: "var(--text3)" }}>{s.why_powerful}</div>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      ) : null}
                      {ai.recommendations?.length ? (
                        <div style={{ marginTop: 10 }}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--accent)" }}>
                            Recommendations
                          </div>
                          <ul style={{ margin: "6px 0", paddingLeft: 18, fontSize: 12.5 }}>
                            {ai.recommendations.map((rec: string) => (
                              <li key={rec}>{rec}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
