import { useCallback, useEffect, useState } from "react";
import { Icon } from "../components/Icon";
import { Avatar } from "../components/ui/Avatar";
import {
  getFeed,
  getMembers,
  getStatus,
  getToday,
  type AttendanceRow,
  type BotStatus,
  type DashboardFeed,
  type Member,
  type RoundPreview,
} from "../lib/api";
import {
  countdownTo,
  formatPkt,
  formatPktDateTime,
} from "../lib/format";
import { RoomPhonePreview } from "../components/RoomPhonePreview";
import { useFeedSocket } from "../lib/useFeedSocket";

function attendanceDot(row: AttendanceRow | undefined): string {
  if (!row || !row.completed) return "s-miss";
  if (!row.on_time) return "s-late";
  if (row.outcome === "clean") return "s-ok";
  if (row.outcome === "has_issues") return "s-late";
  return "s-wait";
}

function attendanceLabel(row: AttendanceRow | undefined): string {
  if (!row || !row.completed) return "Awaiting";
  if (!row.on_time) return "Late";
  if (row.outcome === "clean") return "Clean";
  if (row.outcome === "has_issues") return "Suggestion";
  return "Submitted";
}

export function Dashboard() {
  const [status, setStatus] = useState<BotStatus>();
  const [feed, setFeed] = useState<DashboardFeed>();
  const [round, setRound] = useState<RoundPreview>();
  const [members, setMembers] = useState<Member[]>([]);
  const [feedLoading, setFeedLoading] = useState(false);

  const onFeedUpdate = useCallback((f: DashboardFeed) => {
    setFeed(f);
    setFeedLoading(false);
  }, []);
  useFeedSocket(onFeedUpdate);

  useEffect(() => {
    const loadFast = () => {
      getStatus().then(setStatus).catch(() => undefined);
      getToday().then(setRound).catch(() => undefined);
      getMembers()
        .then((m) => setMembers(m.filter((x) => x.active)))
        .catch(() => undefined);
    };
    const loadFeed = (force = false) => {
      setFeedLoading(true);
      getFeed(force)
        .then((f) => {
          setFeed(f);
          if (f.feed_refreshing) {
            window.setTimeout(() => loadFeed(false), 3_000);
          }
        })
        .catch(() => undefined)
        .finally(() => setFeedLoading(false));
    };

    loadFast();
    // Cache-first paint; background Matrix sync is scheduled by the API without
    // force=true so we don't kick off a login storm on every dashboard open.
    loadFeed(false);
    const fastId = window.setInterval(loadFast, 30_000);
    const feedId = window.setInterval(() => loadFeed(false), 45_000);
    return () => {
      window.clearInterval(fastId);
      window.clearInterval(feedId);
    };
  }, []);

  const linked = status?.element_connected && status?.element_joined;
  const configured = status?.element_configured;
  const hasAlerts = (status?.alerts?.length ?? 0) > 0;
  const today_messages = feed?.today_messages ?? [];
  const task_messages = feed?.task_messages ?? [];
  const analysis = feed?.analysis;
  const taskMonthSubtitle = "Live room · recent messages";
  const pairsSentToday = today_messages.some((m) => m.kind === "daily_message");
  const attendanceByName = Object.fromEntries(
    (analysis?.attendance ?? []).map((a) => [a.name, a])
  );

  return (
    <>
      <div className="grid g4" style={{ marginBottom: 18 }}>
        <div className="card stat hover reveal">
          <div className="ico" style={{ background: "var(--grad-c)" }}>
            <Icon name="bolt" />
          </div>
          <div className="lbl">Bot state</div>
          <div className="val" style={{ textTransform: "capitalize" }}>
            {status?.state ?? "—"}
          </div>
          <div className="meta">
            <span className={`cdot ${status?.database_connected ? "s-ok" : "s-wait"}`} />
            {status?.database_connected ? "Database connected" : "Database offline"}
          </div>
        </div>

        <div className="card stat hover reveal">
          <div className="ico" style={{ background: "var(--grad-a)" }}>
            <Icon name="shield" />
          </div>
          <div className="lbl">Element</div>
          <div className="val">
            {linked ? "Linked" : configured ? "Configured" : "Not linked"}
          </div>
          <div className="meta">
            <Icon
              name="lock"
              size={13}
              style={{ color: linked ? "var(--green)" : "var(--text3)" }}
            />
            {linked
              ? status?.e2ee_store_ready
                ? "Joined · E2EE store ready"
                : "Joined · E2EE store pending"
              : status?.element_connected
                ? "Logged in · not in room"
                : configured
                  ? status?.element_error ?? "Login pending"
                  : "Set Matrix env vars"}
          </div>
        </div>

        <div className="card stat hover reveal">
          <div className="ico" style={{ background: "var(--grad-b)" }}>
            <Icon name="check" />
          </div>
          <div className="lbl">Last message</div>
          <div className="val">{status?.last_send_at ? formatPkt(status.last_send_at) : "—"}</div>
          <div className="meta">
            {status?.last_send_at ? "Last successful send" : "No send recorded yet"}
          </div>
        </div>

        <div className="card stat hover reveal">
          <div className="ico" style={{ background: "linear-gradient(135deg,#5E5CE6,#0A84FF)" }}>
            <Icon name="clock" />
          </div>
          <div className="lbl">Next message</div>
          <div className="val">{countdownTo(status?.next_send_at)}</div>
          <div className="meta">{formatPktDateTime(status?.next_send_at)} PKT</div>
        </div>
      </div>

      <div className="grid g2" style={{ marginBottom: 18 }}>
        <div className="card hover reveal">
          <div className="cap">
            <Icon name="team" size={16} style={{ color: "var(--accent)" }} />
            Today's round
            <span className="tag">Combo {round?.combo_label ?? "—"}</span>
          </div>
          {round?.pairs.length ? (
            round.pairs.map((p, i) => (
              <div className="pair" key={i}>
                <div className="who">
                  <Avatar name={p.member_a} seed={p.member_a} mini />
                  {p.member_a}
                  {p.member_b && (
                    <>
                      <span className="plus">+</span>
                      <Avatar name={p.member_b} seed={p.member_b} mini />
                      {p.member_b}
                    </>
                  )}
                  {p.member_c && (
                    <>
                      <span className="plus">+</span>
                      <Avatar name={p.member_c} seed={p.member_c} mini />
                      {p.member_c}
                    </>
                  )}
                </div>
                <span className="rt">
                  {p.pair_type === "QA" ? "QA · fixed" : p.pair_type === "SOLO" ? "Solo" : "Developers"}
                </span>
              </div>
            ))
          ) : (
            <div style={{ color: "var(--text3)", fontSize: 13, padding: "8px 4px" }}>
              No pairing preview available.
            </div>
          )}
          {round?.team_lead && (
            <div className="lead-line">
              <Icon name="star" />
              {round.team_lead} will make sure all above today ·{" "}
              <b style={{ marginLeft: 2 }}>Team Lead</b>
            </div>
          )}
        </div>

        <RoomPhonePreview
          roomName={status?.room_name}
          roomLabel={status?.room_label}
          homeserver={status?.homeserver}
          messages={today_messages}
          previewText={round?.rendered_text}
          showPreview={!!round?.rendered_text && !pairsSentToday}
          emptyText={
            feedLoading
              ? "Loading room messages from Element…"
              : "Room messages will appear here once the Element mirror syncs."
          }
        />
      </div>

      <div className="grid g2" style={{ marginBottom: 18 }}>
        <RoomPhonePreview
          roomName={status?.task_room_name ?? "Scrum / Tasks"}
          roomLabel={status?.task_room_label ?? undefined}
          homeserver={status?.homeserver}
          roomSubtitle={taskMonthSubtitle}
          messages={task_messages}
          taskFormat
          emptyText={
            feedLoading
              ? "Loading room messages from Element…"
              : status?.task_room_joined === false
                ? "Invite the bot to the task room to read developer assignments."
                : "Room messages will appear here once the Element mirror syncs."
          }
        />

        <div className="card hover reveal">
          <div className="cap">
            <Icon name="chart" size={16} style={{ color: "var(--accent)" }} />
            AI analysis
            <span className="tag gray">
              {feedLoading ? "Loading…" : analysis?.source === "llm" ? "LLM" : "Heuristic"}
            </span>
          </div>
          {analysis?.summary ? (
            <div className="analysis-summary">{analysis.summary}</div>
          ) : (
            <div style={{ color: "var(--text3)", fontSize: 13, marginBottom: 12 }}>
              Analyzing room messages…
            </div>
          )}
          {analysis?.suggestion_ranking?.length ? (
            <div className="rank-list">
              {analysis.suggestion_ranking.map((r) => (
                <div className="rank-row" key={r.name}>
                  <div className="rank-num">{r.rank}</div>
                  <div className="rank-body">
                    <div className="rank-name">{r.name}</div>
                    <div className="rank-meta">
                      {r.pair_context ? `Pair: ${r.pair_context}` : null}
                      {r.pair_context && r.task ? " · " : null}
                      {r.task ? `Task: ${r.task.slice(0, 80)}${r.task.length > 80 ? "…" : ""}` : null}
                    </div>
                    <div className="rank-reason">{r.reason}</div>
                  </div>
                  <div className="rank-score">{r.power_score}</div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: "var(--text3)", fontSize: 13 }}>
              No suggestions yet — rankings appear when members post review feedback.
            </div>
          )}
        </div>
      </div>

      <div className="grid g2" style={{ marginBottom: 18 }}>
        <div className="card reveal">
          <div className="cap">
            <Icon name="check" size={16} style={{ color: "var(--accent)" }} />
            Today's attendance
            {analysis?.stats ? (
              <span className="tag">
                {analysis.stats.completed}/{analysis.stats.total} · {analysis.stats.on_time} on-time
              </span>
            ) : null}
          </div>
          <div className="chips">
            {members.map((m) => {
              const row = attendanceByName[m.name];
              return (
                <div className="chip" key={m.id} title={row?.task ?? row?.suggestion_summary ?? undefined}>
                  <Avatar name={m.name} seed={m.name} mini />
                  {m.name}
                  <span className={`cdot ${attendanceDot(row)}`} />
                  <span style={{ fontSize: 11, color: "var(--text3)" }}>{attendanceLabel(row)}</span>
                </div>
              );
            })}
          </div>
          <div
            style={{
              marginTop: 14,
              fontSize: 12.5,
              color: "var(--text3)",
              fontWeight: 500,
              lineHeight: 1.5,
            }}
          >
            Status is inferred from pairing-room reports and task-room context.{" "}
            <b style={{ color: "var(--text2)" }}>Clean</b> = standard message,{" "}
            <b style={{ color: "var(--text2)" }}>Suggestion</b> = issues or improvements shared.
          </div>
        </div>

        <div className="card reveal" style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            className="ico"
            style={{
              width: 34,
              height: 34,
              borderRadius: 10,
              background: "var(--accent-weak)",
              display: "grid",
              placeItems: "center",
            }}
          >
            <Icon name="chart" size={18} style={{ color: "var(--accent)" }} />
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>Performance metrics</div>
            <div style={{ color: "var(--text3)", fontSize: 12.5, fontWeight: 500 }}>
              {analysis?.stats
                ? `${analysis.stats.completed} completed · ${analysis.stats.with_suggestions} with suggestions · ${analysis.stats.missed} awaiting`
                : "Completion and on-time rates update as reports are ingested."}
            </div>
          </div>
        </div>
      </div>

      <div
        className="card reveal"
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 12,
          borderColor: hasAlerts ? "rgba(255,159,10,.35)" : undefined,
        }}
      >
        <div
          className="ico"
          style={{
            width: 34,
            height: 34,
            borderRadius: 10,
            background: hasAlerts ? "rgba(255,159,10,.15)" : "rgba(52,199,89,.15)",
            display: "grid",
            placeItems: "center",
            flexShrink: 0,
          }}
        >
          <Icon
            name={hasAlerts ? "warn" : "check"}
            size={18}
            style={{ color: hasAlerts ? "var(--orange)" : "var(--green)" }}
          />
        </div>
        <div>
          <div style={{ fontWeight: 600, fontSize: 14 }}>
            {hasAlerts ? "Needs attention" : "All systems clear"}
          </div>
          <div style={{ color: "var(--text3)", fontSize: 12.5, fontWeight: 500, marginTop: 4 }}>
            {hasAlerts ? (
              <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                {status!.alerts.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            ) : (
              "Matrix linked, database connected, no config gaps."
            )}
          </div>
        </div>
      </div>
    </>
  );
}
