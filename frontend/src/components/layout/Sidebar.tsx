import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import clsx from "clsx";
import { Icon } from "../Icon";
import { useTheme } from "../../lib/theme";
import { useAuth } from "../../lib/auth";
import { GROUPS, NAV_ITEMS } from "./nav";

export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { theme, toggle } = useTheme();
  const { user } = useAuth();
  const initials = (user ?? "A").slice(0, 2).toUpperCase();

  return (
    <>
      <div className="brand">
        <div className="logo">
          <Icon name="logo" />
        </div>
        <div>
          <b>PairFlow</b>
          <small>Automation Control</small>
        </div>
      </div>

      {GROUPS.map((group) => (
        <div key={group}>
          <div className="navlbl">{group}</div>
          {NAV_ITEMS.filter((n) => n.group === group).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              onClick={onNavigate}
              className={({ isActive }) => clsx("nav", isActive && "active")}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </div>
      ))}

      <div className="side-foot">
        <div className="avatar" style={{ background: "var(--grad-a)" }}>
          {initials}
        </div>
        <div className="who">
          {user ?? "Admin"}
          <small>Admin</small>
        </div>
        <button className="theme-btn" onClick={toggle} title="Toggle appearance">
          <Icon name={theme === "dark" ? "sun" : "moon"} />
        </button>
      </div>
    </>
  );
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <aside className="sidebar sidebar--desktop">
      <SidebarContent onNavigate={onNavigate} />
    </aside>
  );
}

/** Track mobile breakpoint for drawer animation. */
export function useIsMobile(breakpoint = 720) {
  const [mobile, setMobile] = useState(
    () => typeof window !== "undefined" && window.innerWidth <= breakpoint
  );
  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${breakpoint}px)`);
    const fn = () => setMobile(mq.matches);
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, [breakpoint]);
  return mobile;
}
