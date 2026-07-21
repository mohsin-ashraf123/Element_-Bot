import { useCallback, useEffect, useState } from "react";

import { Icon } from "../components/Icon";

import { getFeed, getRoomStatus, getToday, type DashboardFeed, type RoomStatus, type RoundPreview } from "../lib/api";

import { maskHomeserver } from "../lib/format";

import { RoomPhonePreview } from "../components/RoomPhonePreview";
import { useFeedSocket } from "../lib/useFeedSocket";



export function Room() {

  const [room, setRoom] = useState<RoomStatus>();

  const [feed, setFeed] = useState<DashboardFeed>();

  const [round, setRound] = useState<RoundPreview>();

  const [feedLoading, setFeedLoading] = useState(false);

  const onFeedUpdate = useCallback((f: DashboardFeed) => {
    setFeed(f);
    setFeedLoading(false);
  }, []);
  useFeedSocket(onFeedUpdate);

  useEffect(() => {

    const loadStatus = () => {

      getRoomStatus().then(setRoom).catch(() => undefined);

      getToday().then(setRound).catch(() => undefined);

    };

    const loadFeed = () => {

      setFeedLoading(true);

      getFeed()

        .then((f) => {

          setFeed(f);

          if (f.feed_refreshing) {

            window.setTimeout(loadFeed, 3_000);

          }

        })

        .catch(() => undefined)

        .finally(() => setFeedLoading(false));

    };



    loadStatus();

    loadFeed();

    const statusId = window.setInterval(loadStatus, 30_000);

    const feedId = window.setInterval(loadFeed, 60_000);

    return () => {

      window.clearInterval(statusId);

      window.clearInterval(feedId);

    };

  }, []);



  const healthy = room?.connected && room?.joined;

  const today_messages = feed?.today_messages ?? room?.today_messages ?? [];

  const pairsSentToday = today_messages.some((m) => m.kind === "daily_message");



  return (

    <div className="grid g2">

      <div className="card reveal">

        <div className="cap">

          <Icon name="room" size={16} style={{ color: "var(--accent)" }} />

          Connection

          <span className={`tag ${healthy ? "green" : room?.configured ? "gray" : "red"}`}>

            {healthy ? "Linked" : room?.configured ? "Configured" : "Missing config"}

          </span>

        </div>

        <div className="field">

          <div>

            <div className="fl">Homeserver</div>

            <div className="fd">Matrix server the bot signs in to</div>

          </div>

          <span className="masked">{maskHomeserver(room?.homeserver)}</span>

        </div>

        <div className="field">

          <div>

            <div className="fl">Room</div>

            <div className="fd">The one room the bot may touch</div>

          </div>

          <span className="masked">{room?.room_name ?? room?.room_label ?? "—"}</span>

        </div>

        <div className="field">

          <div>

            <div className="fl">Encryption store</div>

            <div className="fd">E2EE keys persisted on disk</div>

          </div>

          <span className={`status-badge ${room?.e2ee_store_ready ? "sb-ok" : "sb-run"}`}>

            <Icon name="lock" size={12} />

            {room?.e2ee_store_ready ? "Store ready" : "Created on first sync"}

          </span>

        </div>

        <div className="field">

          <div>

            <div className="fl">Bot membership</div>

            <div className="fd">Must be joined to read reports</div>

          </div>

          <span className={`status-badge ${room?.joined ? "sb-ok" : "sb-fail"}`}>

            <Icon name={room?.joined ? "check" : "warn"} size={12} />

            {room?.joined ? "Joined" : room?.connected ? "Not in room" : "Not connected"}

          </span>

        </div>

        {room?.error && (

          <div className="banner" style={{ marginTop: 12 }}>

            <Icon name="warn" />

            {room.error}

          </div>

        )}

        <button className="btn ghost" style={{ marginTop: 16 }} type="button" disabled>

          <Icon name="send" />

          Send test message (Phase 1)

        </button>

      </div>



      <RoomPhonePreview

        roomName={room?.room_name}

        roomLabel={room?.room_label}

        homeserver={room?.homeserver}

        messages={today_messages}

        previewText={round?.rendered_text}

        showPreview={!!round?.rendered_text && !pairsSentToday}

        previewStamp="Preview · daily pairing"

        emptyText={

          feedLoading

            ? "Loading today's messages from Element…"

            : "Room preview shows the next daily pairing message once the roster is configured."

        }

      />

    </div>

  );

}

