import { Icon } from "../Icon";
import type { BotStatus } from "../../lib/api";

type Props = {
  title: string;
  subtitle: string;
  status?: BotStatus;
  onMenu: () => void;
  onSendNow: () => void;
  sending?: boolean;
};

export function Topbar({ title, subtitle, status, onMenu, onSendNow, sending = false }: Props) {
  const state = status?.state ?? "running";
  const elementLinked = status?.element_connected && status?.element_joined;
  const dotClass =
    state === "error"
      ? "dot error"
      : state === "paused"
        ? "dot paused"
        : elementLinked
          ? "dot"
          : "dot warn";
  const label =
    state === "paused"
      ? "Paused"
      : state === "error"
        ? "Error"
        : elementLinked
          ? "Linked"
          : "Running";

  return (
    <div className="topbar">
      <button className="hamb" onClick={onMenu} title="Menu" type="button">
        <Icon name="menu" />
      </button>
      <div className="topbar-main">
        <h1>{title}</h1>
        <div className="sub">{subtitle}</div>
      </div>
      <div className="topbar-actions">
        <div className="statuspill">
          <span className={dotClass} />
          <span className="status-text">{label}</span>
        </div>
        <button
          className="btn primary btn-send"
          type="button"
          onClick={onSendNow}
          disabled={sending}
        >
          <Icon name="send" />
          <span className="btn-label">{sending ? "Sending…" : "Send"}</span>
        </button>
      </div>
    </div>
  );
}
