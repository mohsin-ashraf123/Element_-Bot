import type { IconName } from "../Icon";

export type NavItem = {
  to: string;
  label: string;
  icon: IconName;
  group: "Overview" | "Insights" | "System";
  title: string;
};

export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: "dash", group: "Overview", title: "Dashboard" },
  { to: "/team", label: "Team & Roles", icon: "team", group: "Overview", title: "Team & Roles" },
  { to: "/history", label: "Pairing History", icon: "hist", group: "Overview", title: "Pairing History" },
  { to: "/performance", label: "Performance", icon: "chart", group: "Insights", title: "Performance" },
  { to: "/reports", label: "Reports", icon: "report", group: "Insights", title: "Reports" },
  { to: "/room", label: "Element Room", icon: "room", group: "System", title: "Element Room" },
  { to: "/schedule", label: "Schedule & Rules", icon: "cal", group: "System", title: "Schedule & Rules" },
  { to: "/jobs", label: "Jobs & Logs", icon: "logs", group: "System", title: "Jobs & Logs" },
  { to: "/settings", label: "Settings", icon: "gear", group: "System", title: "Settings" },
];

export const GROUPS: NavItem["group"][] = ["Overview", "Insights", "System"];
