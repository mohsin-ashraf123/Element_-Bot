export type TaskStatusKind =
  | "done"
  | "testing"
  | "in_progress"
  | "today"
  | "tomorrow"
  | "friday"
  | "other";

export type ParsedTaskItem = {
  text: string;
  status?: string;
  statusKind: TaskStatusKind;
  assignee?: string;
};

export type ParsedTaskMember = {
  name: string;
  items: ParsedTaskItem[];
};

export type ParsedTaskMessage = {
  title?: string;
  release?: string;
  members: ParsedTaskMember[];
  unplanned: ParsedTaskItem[];
};

const DASH_LINE = /^-{8,}$/;

function stripMd(s: string): string {
  return s.replace(/\*\*/g, "").trim();
}

function classifyStatus(raw: string): { label: string; kind: TaskStatusKind } {
  const s = raw.toLowerCase().trim();
  if (s === "done") return { label: raw, kind: "done" };
  if (s === "testing") return { label: raw, kind: "testing" };
  if (s.includes("progress")) return { label: raw, kind: "in_progress" };
  if (s === "today") return { label: raw, kind: "today" };
  if (s === "tomorrow") return { label: raw, kind: "tomorrow" };
  if (s === "friday") return { label: raw, kind: "friday" };
  return { label: raw, kind: "other" };
}

function parseItemLine(line: string, unplanned = false): ParsedTaskItem | null {
  const body = line.replace(/^[-•]\s*/, "").trim();
  if (!body) return null;

  if (unplanned) {
    const m = body.match(/^(.+?)\s*\(([^)]+)\)\s*$/);
    if (m) {
      const tail = m[2];
      const parts = tail.split(/\s*-\s*/);
      const assignee = parts.length > 1 ? parts[0].trim() : undefined;
      const statusRaw = parts.length > 1 ? parts.slice(1).join(" - ") : tail;
      const { label, kind } = classifyStatus(statusRaw);
      return { text: m[1].trim(), assignee, status: label, statusKind: kind };
    }
    return { text: body, statusKind: "other" };
  }

  const bracket = body.match(/^(.+?)\s*\[([^\]]+)\]\s*$/);
  if (bracket) {
    const { label, kind } = classifyStatus(bracket[2]);
    return { text: bracket[1].trim(), status: label, statusKind: kind };
  }

  const paren = body.match(/^(.+?)\s*\(([^)]+)\)\s*$/);
  if (paren) {
    const { label, kind } = classifyStatus(paren[2]);
    return { text: paren[1].trim(), status: label, statusKind: kind };
  }

  return { text: body, statusKind: "other" };
}

export function parseTaskMessage(text: string): ParsedTaskMessage | null {
  const raw = (text || "").trim();
  if (!raw) return null;

  const lines = raw.split("\n").map((l) => l.trim()).filter(Boolean);
  if (!lines.some((l) => l.includes("**"))) return null;

  const result: ParsedTaskMessage = { members: [], unplanned: [] };
  let current: ParsedTaskMember | null = null;
  let inUnplanned = false;

  for (const line of lines) {
    if (DASH_LINE.test(line)) continue;

    if (/^\*\*next release\*\*/i.test(line)) {
      result.release = stripMd(line.replace(/^\*\*next release\*\*:\s*/i, ""));
      continue;
    }

    const memberOnly = line.match(/^\*\*([^*]+)\*\*\s*::\s*$/);
    if (memberOnly) {
      current = { name: memberOnly[1].trim(), items: [] };
      result.members.push(current);
      inUnplanned = false;
      continue;
    }

    const memberWithItems = line.match(/^\*\*([^*]+)\*\*\s*::\s*(.+)$/);
    if (memberWithItems) {
      current = { name: memberWithItems[1].trim(), items: [] };
      result.members.push(current);
      inUnplanned = false;
      const rest = memberWithItems[2].trim();
      if (rest.startsWith("-")) {
        const item = parseItemLine(rest, false);
        if (item) current.items.push(item);
      } else if (rest) {
        current.items.push({ text: stripMd(rest), statusKind: "other" });
      }
      continue;
    }

    const section = line.match(/^\*\*([^*]+)\*\*\s*$/);
    if (section) {
      const label = section[1].trim();
      if (/unplanned work/i.test(label)) {
        inUnplanned = true;
        current = null;
        continue;
      }
      if (!current && result.members.length === 0 && !result.title) {
        result.title = label;
        continue;
      }
    }

    if (line.startsWith("-")) {
      const item = parseItemLine(line, inUnplanned);
      if (!item) continue;
      if (inUnplanned) {
        result.unplanned.push(item);
      } else if (current) {
        current.items.push(item);
      }
      continue;
    }

    if (!inUnplanned && current && line) {
      current.items.push({ text: stripMd(line), statusKind: "other" });
    }
  }

  if (!result.title && result.members.length === 0 && result.unplanned.length === 0) {
    return null;
  }
  return result;
}

export function looksLikeTaskAgenda(text: string): boolean {
  return parseTaskMessage(text) !== null;
}
