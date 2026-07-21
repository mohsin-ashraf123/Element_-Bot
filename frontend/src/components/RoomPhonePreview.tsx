import { useEffect, useRef } from "react";
import { Icon } from "./Icon";
import { Avatar } from "./ui/Avatar";
import { formatPkt, maskHomeserver } from "../lib/format";
import type { RoomMessage } from "../lib/api";
import { TaskMessageBody } from "./TaskMessageBody";
import { looksLikeTaskAgenda } from "../lib/parseTaskMessage";

type Props = {
  roomName?: string | null;
  roomLabel?: string | null;
  homeserver?: string | null;
  roomSubtitle?: string | null;
  messages?: RoomMessage[];
  previewText?: string | null;
  showPreview?: boolean;
  previewStamp?: string;
  emptyText?: string;
  /** Render Scrum/task agenda messages with structured layout */
  taskFormat?: boolean;
};

export function RoomPhonePreview({
  roomName,
  roomLabel,
  homeserver,
  roomSubtitle,
  messages = [],
  previewText,
  showPreview = false,
  previewStamp = "Preview · next scheduled send",
  emptyText = "No messages sent today yet.",
  taskFormat = false,
}: Props) {
  const title = roomName?.trim() || roomLabel?.trim() || "Element room";
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = feedRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, showPreview, previewText]);

  return (
    <div className="phone reveal">
      <div className="room-head">
        <Avatar name="#" mini style={{ width: 34, height: 34, background: "var(--grad-a)" }} />
        <div>
          <div className="rname">{title}</div>
          <div className="rmeta">
            <Icon name="lock" size={11} style={{ marginRight: 4, verticalAlign: -1 }} />
            Encrypted · {maskHomeserver(homeserver)}
            {roomSubtitle ? ` · ${roomSubtitle}` : ""}
          </div>
        </div>
      </div>
      <div className="bubbles feed-scroll" ref={feedRef}>
        {messages.map((m) => {
          const useTask = taskFormat && looksLikeTaskAgenda(m.text || "");
          return (
            <div key={String(m.id)} className={`feed-item ${m.is_bot ? "feed-bot" : "feed-member"}`}>
              {!m.is_bot ? <div className="sender">{m.label}</div> : null}
              <div className={`bubble ${m.is_bot ? "" : "them"}${useTask ? " task-bubble" : ""}`}>
                {useTask ? <TaskMessageBody text={m.text || ""} /> : m.text}
              </div>
              <div className={`stamp ${m.is_bot ? "" : "stamp-left"}`}>
                {m.label} · {formatPkt(m.sent_at)}
              </div>
            </div>
          );
        })}
        {showPreview && previewText ? (
          <>
            <div className="bubble">{previewText}</div>
            <div className="stamp">{previewStamp}</div>
          </>
        ) : null}
        {!messages.length && !(showPreview && previewText) ? (
          <div
            style={{
              color: "var(--text3)",
              fontSize: 13,
              fontWeight: 500,
              padding: "12px 4px",
            }}
          >
            {emptyText}
          </div>
        ) : null}
      </div>
    </div>
  );
}
