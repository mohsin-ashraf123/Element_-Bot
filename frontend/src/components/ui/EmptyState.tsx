import { Icon } from "../Icon";

type Props = {
  title: string;
  description: string;
  icon?: "chart" | "report" | "logs" | "room";
};

export function EmptyState({ title, description, icon = "chart" }: Props) {
  return (
    <div
      className="card reveal"
      style={{
        padding: "28px 22px",
        textAlign: "center",
        color: "var(--text2)",
      }}
    >
      <div
        style={{
          width: 44,
          height: 44,
          borderRadius: 12,
          background: "var(--accent-weak)",
          display: "grid",
          placeItems: "center",
          margin: "0 auto 14px",
        }}
      >
        <Icon name={icon} size={20} style={{ color: "var(--accent)" }} />
      </div>
      <div style={{ fontWeight: 600, fontSize: 15, color: "var(--text)", marginBottom: 6 }}>
        {title}
      </div>
      <div style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.55, maxWidth: 420, margin: "0 auto" }}>
        {description}
      </div>
    </div>
  );
}
