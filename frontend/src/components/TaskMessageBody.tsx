import type { ParsedTaskItem, ParsedTaskMessage } from "../lib/parseTaskMessage";
import { parseTaskMessage } from "../lib/parseTaskMessage";

function StatusBadge({ item }: { item: ParsedTaskItem }) {
  if (!item.status) return null;
  return <span className={`task-status task-status-${item.statusKind}`}>{item.status}</span>;
}

function TaskList({ items }: { items: ParsedTaskItem[] }) {
  if (!items.length) return null;
  return (
    <ul className="task-list">
      {items.map((item, i) => (
        <li key={i} className="task-list-item">
          <span className="task-item-text">{item.text}</span>
          {item.assignee ? <span className="task-assignee">{item.assignee}</span> : null}
          <StatusBadge item={item} />
        </li>
      ))}
    </ul>
  );
}

function TaskCard({ data }: { data: ParsedTaskMessage }) {
  return (
    <div className="task-card">
      {data.title ? <div className="task-card-title">{data.title}</div> : null}
      <div className="task-members">
        {data.members.map((member) => (
          <div key={member.name} className="task-member-block">
            <div className="task-member-name">{member.name}</div>
            <TaskList items={member.items} />
          </div>
        ))}
      </div>
      {data.unplanned.length ? (
        <div className="task-unplanned">
          <div className="task-unplanned-title">Unplanned work</div>
          <TaskList items={data.unplanned} />
        </div>
      ) : null}
      {data.release ? (
        <div className="task-release">
          Next release: <strong>{data.release}</strong>
        </div>
      ) : null}
    </div>
  );
}

type Props = {
  text: string;
};

export function TaskMessageBody({ text }: Props) {
  const parsed = parseTaskMessage(text);
  if (!parsed) {
    return <span className="task-plain">{text}</span>;
  }
  return <TaskCard data={parsed} />;
}
