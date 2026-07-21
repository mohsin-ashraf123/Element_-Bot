import { useEffect, useState } from "react";
import clsx from "clsx";
import { Icon } from "../components/Icon";
import { Switch } from "../components/ui/Switch";
import { getSettings } from "../lib/api";

const DAYS = ["M", "T", "W", "T", "F", "S", "S"];
const CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

export function Schedule() {
  const [schedule, setSchedule] = useState<{
    send_time: string;
    working_days: string[];
    timeliness_cutoff: string;
    timezone: string;
  }>();

  useEffect(() => {
    getSettings()
      .then((s) => setSchedule(s.schedule))
      .catch(() => undefined);
  }, []);

  const working = new Set(schedule?.working_days ?? ["mon", "tue", "wed", "thu", "fri"]);

  return (
    <>
      <div className="card reveal" style={{ marginBottom: 18 }}>
        <div className="cap">
          <Icon name="cal" size={16} style={{ color: "var(--accent)" }} />
          Daily schedule
        </div>
        <div className="field">
          <div>
            <div className="fl">Send time</div>
            <div className="fd">{schedule?.timezone ?? "Asia/Karachi"} (PKT)</div>
          </div>
          <span className="masked">{schedule?.send_time ?? "11:00"} AM</span>
        </div>
        <div className="field">
          <div>
            <div className="fl">Working days</div>
          </div>
          <div style={{ display: "flex", gap: 7 }}>
            {DAYS.map((d, i) => (
              <span key={i} className={clsx("day", working.has(CODES[i]) ? "on" : "off")}>
                {d}
              </span>
            ))}
          </div>
        </div>
        <div className="field">
          <div>
            <div className="fl">On-time cutoff</div>
            <div className="fd">
              Reports after this count as late{" "}
              <span className="od">
                <Icon name="warn" size={10} />
                OPEN DECISION
              </span>
            </div>
          </div>
          <span className="masked">{schedule?.timeliness_cutoff ?? "23:59"} same day</span>
        </div>
      </div>

      <div className="card reveal">
        <div className="cap">
          <Icon name="gear" size={16} style={{ color: "var(--accent)" }} />
          Rules
        </div>
        <div className="field">
          <div>
            <div className="fl">Report attribution</div>
            <div className="fd">Report-only room — any known member's message = their report</div>
          </div>
          <div className="pillbtns">
            <button className="pillbtn on">Report-only</button>
            <button className="pillbtn">Thread reply</button>
          </div>
        </div>
        <div className="field">
          <div>
            <div className="fl">Team Lead verification</div>
            <div className="fd">System decides from reports · the day's lead is accountable</div>
          </div>
          <div className="pillbtns">
            <button className="pillbtn on">Implicit</button>
          </div>
        </div>
        <div className="field">
          <div>
            <div className="fl">Weekly report</div>
            <div className="fd">Friday after cutoff</div>
          </div>
          <Switch defaultOn />
        </div>
        <div className="field">
          <div>
            <div className="fl">Monthly report</div>
            <div className="fd">Last working day</div>
          </div>
          <Switch defaultOn />
        </div>
      </div>
    </>
  );
}
