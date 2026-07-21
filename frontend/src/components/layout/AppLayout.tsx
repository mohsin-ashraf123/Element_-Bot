import { useEffect, useMemo, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Sidebar, SidebarContent, useIsMobile } from "./Sidebar";
import { Topbar } from "./Topbar";
import { NAV_ITEMS } from "./nav";
import { getMembers, getStatus, sendPairs, type BotStatus } from "../../lib/api";
import { todayLabel } from "../../lib/format";

const STATUS_CACHE_KEY = "pairflow_status_cache";

function readCachedStatus(): BotStatus | undefined {
  try {
    const raw = sessionStorage.getItem(STATUS_CACHE_KEY);
    return raw ? (JSON.parse(raw) as BotStatus) : undefined;
  } catch {
    return undefined;
  }
}

function writeCachedStatus(status: BotStatus) {
  try {
    sessionStorage.setItem(STATUS_CACHE_KEY, JSON.stringify(status));
  } catch {
    /* ignore quota */
  }
}

function isTodayPkt(iso: string): boolean {
  const fmt = (d: Date) => d.toLocaleDateString("en-CA", { timeZone: "Asia/Karachi" });
  return fmt(new Date(iso)) === fmt(new Date());
}

export function AppLayout() {
  const location = useLocation();
  const isMobile = useIsMobile();
  const [navOpen, setNavOpen] = useState(false);
  const [status, setStatus] = useState<BotStatus | undefined>(readCachedStatus);
  const [teamMeta, setTeamMeta] = useState({ devs: 0, qa: 0, members: 0 });
  const [sending, setSending] = useState(false);
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);

  const current = NAV_ITEMS.find((n) => n.to === location.pathname) ?? NAV_ITEMS[0];

  useEffect(() => {
    const load = () =>
      getStatus()
        .then((s) => {
          setStatus(s);
          writeCachedStatus(s);
        })
        .catch(() => undefined);
    load();
    const id = window.setInterval(load, 30_000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    getMembers()
      .then((m) => {
        const active = m.filter((x) => x.active);
        setTeamMeta({
          members: active.length,
          devs: active.filter((x) => x.role === "DEVELOPER").length,
          qa: active.filter((x) => x.role === "QA").length,
        });
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    document.body.style.overflow = navOpen && isMobile ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [navOpen, isMobile]);

  const subtitle = useMemo(() => {
    switch (location.pathname) {
      case "/": {
        const members = status?.active_members ?? teamMeta.members;
        const matrix =
          status?.element_connected && status?.element_joined
            ? "Matrix linked"
            : status?.element_configured
              ? "Matrix configured"
              : "Matrix not linked";
        return `${todayLabel()} · ${members} active · ${matrix}`;
      }
      case "/team":
        return `${teamMeta.devs} developers · ${teamMeta.qa} QA`;
      case "/history":
        return "Recorded daily rounds";
      case "/performance":
        return "Today · this week · this month";
      case "/reports":
        return "Weekly & monthly AI reports — saved in database";
      case "/room":
        return status?.element_connected ? "Matrix linked" : "Configure Matrix in .env";
      case "/schedule":
        return "Asia/Karachi · Mon–Fri";
      case "/jobs":
        return "Scheduled jobs & worker logs";
      case "/settings":
        return "Admin · LLM · appearance";
      default:
        return "";
    }
  }, [location.pathname, status, teamMeta]);

  useEffect(() => {
    if (!toast) return;
    const id = window.setTimeout(() => setToast(null), 4500);
    return () => window.clearTimeout(id);
  }, [toast]);

  const handleSendNow = async () => {
    const alreadySent = status?.last_send_at && isTodayPkt(status.last_send_at);
    const confirmMsg = alreadySent
      ? "Today's pairing was already sent. Send again to the Element room?"
      : "Send today's pairing message to the Element room now?";
    if (!window.confirm(confirmMsg)) return;

    setSending(true);
    setToast(null);
    try {
      const res = await sendPairs();
      if (res.ok) {
        setToast({ ok: true, text: res.message ?? "Pairing message sent." });
        const next = await getStatus();
        setStatus(next);
        writeCachedStatus(next);
      } else {
        setToast({ ok: false, text: res.error ?? "Send failed." });
      }
    } catch (err: unknown) {
      const detail =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : null;
      setToast({
        ok: false,
        text: detail ?? "Send failed — check Matrix connection.",
      });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="app">
      {!isMobile && <Sidebar onNavigate={() => setNavOpen(false)} />}

      <AnimatePresence>
        {isMobile && navOpen && (
          <>
            <motion.div
              className="nav-backdrop nav-backdrop--visible"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.22 }}
              onClick={() => setNavOpen(false)}
            />
            <motion.aside
              className="sidebar sidebar--drawer"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", damping: 32, stiffness: 360 }}
            >
              <SidebarContent onNavigate={() => setNavOpen(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <main className="main">
        <Topbar
          title={current.title}
          subtitle={subtitle}
          status={status}
          onMenu={() => setNavOpen(true)}
          onSendNow={handleSendNow}
          sending={sending}
        />
        {toast ? (
          <div className={`send-toast send-toast-${toast.ok ? "ok" : "err"}`} role="status">
            {toast.text}
          </div>
        ) : null}
        <div className="content">
          <div className="view active">
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  );
}
