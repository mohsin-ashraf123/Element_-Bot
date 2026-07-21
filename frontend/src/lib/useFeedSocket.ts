import { useEffect } from "react";
import type { DashboardFeed } from "./api";

const TOKEN_KEY = "pairflow_token";

export function useFeedSocket(onFeed: (feed: DashboardFeed) => void) {
  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) return;

    const apiBase = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "")
      || `${window.location.origin}/api`;
    const wsBase = apiBase.replace(/^http/i, "ws");
    const url = `${wsBase}/dashboard/feed/ws?token=${encodeURIComponent(token)}`;
    let ws: WebSocket | null = null;
    let pingId: number | undefined;
    let retryId: number | undefined;
    let closed = false;

    const connect = () => {
      if (closed) return;
      ws = new WebSocket(url);

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data as string) as { type?: string; data?: DashboardFeed };
          if (msg.type === "feed" && msg.data) onFeed(msg.data);
        } catch {
          /* ignore malformed frames */
        }
      };

      ws.onclose = () => {
        if (!closed) retryId = window.setTimeout(connect, 3_000);
      };

      ws.onopen = () => {
        pingId = window.setInterval(() => {
          if (ws?.readyState === WebSocket.OPEN) ws.send("ping");
        }, 25_000);
      };
    };

    connect();

    return () => {
      closed = true;
      if (pingId) window.clearInterval(pingId);
      if (retryId) window.clearTimeout(retryId);
      ws?.close();
    };
  }, [onFeed]);
}
