import { useEffect, useState } from "react";
import { Icon } from "../components/Icon";
import { getHistory } from "../lib/api";

type Row = {
  date: string;
  combo: string;
  dev_pairs: string;
  team_lead: string | null;
  status: string;
};

export function History() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    getHistory().then(setRows).catch(() => setRows([]));
  }, []);

  return (
    <div className="card reveal">
      <div className="cap">
        <Icon name="hist" size={16} style={{ color: "var(--accent)" }} />
        Recent rounds
      </div>
      {rows.length === 0 ? (
        <div style={{ color: "var(--text3)", fontSize: 13, fontWeight: 500, padding: "18px 4px" }}>
          No rounds recorded yet. Each successful daily send (scheduled or manual) appears here
          with combo, pairs, team lead and send status.
        </div>
      ) : (
        <table>
          <tbody>
            <tr>
              <th>Date</th>
              <th>Combo</th>
              <th>Developer pairs</th>
              <th>Team Lead</th>
              <th>Message</th>
            </tr>
            {rows.map((r, i) => (
              <tr key={i}>
                <td>{r.date}</td>
                <td><span className="combo-badge">{r.combo}</span></td>
                <td>{r.dev_pairs}</td>
                <td>{r.team_lead ?? "—"}</td>
                <td>
                  <span className={`status-badge ${r.status === "sent" ? "sb-ok" : "sb-fail"}`}>
                    <Icon name={r.status === "sent" ? "check" : "warn"} size={12} />
                    {r.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
