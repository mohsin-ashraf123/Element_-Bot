import { useEffect, useState } from "react";
import clsx from "clsx";
import { Icon } from "../components/Icon";
import { Avatar } from "../components/ui/Avatar";
import { Switch } from "../components/ui/Switch";
import { Modal } from "../components/ui/Modal";
import { api, getLeadPreview, getMembers, type Member } from "../lib/api";

type FormState = { name: string; matrix: string; role: "DEVELOPER" | "QA" };
const EMPTY: FormState = { name: "", matrix: "", role: "DEVELOPER" };

export function Team() {
  const [members, setMembers] = useState<Member[]>([]);
  const [nextLeads, setNextLeads] = useState<string[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Member | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY);

  const load = () => {
    getMembers().then(setMembers).catch(() => undefined);
    getLeadPreview().then((d) => setNextLeads(d.next_leads)).catch(() => undefined);
  };
  useEffect(load, []);

  const devs = members.filter((m) => m.role === "DEVELOPER");
  const qa = members.filter((m) => m.role === "QA");

  const openAdd = (role: "DEVELOPER" | "QA") => {
    setEditing(null);
    setForm({ ...EMPTY, role });
    setModalOpen(true);
  };

  const openEdit = (m: Member) => {
    setEditing(m);
    setForm({ name: m.name, matrix: m.matrix_user_id ?? "", role: m.role });
    setModalOpen(true);
  };

  const submit = async () => {
    if (!form.name.trim()) return;
    let matrix = form.matrix.trim();
    if (matrix && !matrix.startsWith("@")) matrix = "@" + matrix;
    const body = {
      name: form.name.trim(),
      matrix_user_id: matrix || null,
      role: form.role,
    };
    if (editing) {
      await api.patch(`/team/members/${editing.id}`, body);
    } else {
      await api.post("/team/members", body);
    }
    setModalOpen(false);
    load();
  };

  const remove = async (m: Member) => {
    if (!window.confirm(`Remove ${m.name}? Past history stays; excluded from future rounds only.`)) return;
    await api.delete(`/team/members/${m.id}`);
    load();
  };

  const MemberRow = ({ m, showSwitch }: { m: Member; showSwitch: boolean }) => (
    <div className="row">
      <Avatar name={m.name} seed={m.name} chars={m.role === "QA" ? 2 : 1} />
      <div>
        <div className="name">{m.name}</div>
        <div className="desc">
          {m.matrix_user_id ?? (
            <span style={{ color: "var(--orange)" }}>— no Matrix ID (config gap)</span>
          )}
        </div>
      </div>
      <span className={clsx("roletag", m.role === "QA" ? "rt-qa" : "rt-dev")}>
        {m.role === "QA" ? "QA" : "Developer"}
      </span>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
        {showSwitch && <Switch defaultOn={m.active} />}
        <button className="remove" title="Edit" onClick={() => openEdit(m)}>
          <Icon name="edit" />
        </button>
        <button className="remove" title="Remove" onClick={() => remove(m)}>
          <Icon name="x" />
        </button>
      </div>
    </div>
  );

  return (
    <>
      <div className="grid g2">
        <div className="card reveal">
          <div className="cap">
            <Icon name="team" size={16} style={{ color: "var(--accent)" }} />
            Developers
            <button className="btn ghost" style={{ marginLeft: "auto", padding: "6px 11px", fontSize: 12.5 }} onClick={() => openAdd("DEVELOPER")}>
              <Icon name="plus" size={14} />
              Add member
            </button>
          </div>
          {devs.map((m) => (
            <MemberRow key={m.id} m={m} showSwitch />
          ))}
        </div>

        <div className="grid" style={{ gridTemplateColumns: "1fr" }}>
          <div className="card reveal">
            <div className="cap">
              <Icon name="lock" size={16} style={{ color: "var(--purple)" }} />
              QA — fixed pair
              <button className="btn ghost" style={{ marginLeft: "auto", padding: "6px 11px", fontSize: 12.5 }} onClick={() => openAdd("QA")}>
                <Icon name="plus" size={14} />
                Add QA
              </button>
            </div>
            {qa.map((m) => (
              <MemberRow key={m.id} m={m} showSwitch={false} />
            ))}
            <div className="banner" style={{ marginTop: 14 }}>
              <Icon name="lock" />
              Habiba &amp; Aqeel stay paired every day. Changing this needs confirmation.
            </div>
          </div>
          <div className="card reveal">
            <div className="cap">
              <Icon name="star" size={16} style={{ color: "var(--orange)" }} />
              Team Lead order
              <span className="tag gray">Round-robin · {members.length}</span>
            </div>
            <div style={{ fontSize: 13, color: "var(--text2)", fontWeight: 500, lineHeight: 1.9 }}>
              Next {nextLeads.length} leads:{" "}
              <b style={{ color: "var(--text)" }}>{nextLeads.join(" → ")}</b>
            </div>
          </div>
        </div>
      </div>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)}>
        <h3>{editing ? `Edit ${editing.name}` : form.role === "QA" ? "Add QA member" : "Add member"}</h3>
        <div className="msub">
          {editing
            ? "Update this member's details. Changes apply from the next round."
            : "They'll join the rotation from the next working day."}
        </div>
        <label className="inp-lbl">Name</label>
        <input className="inp" placeholder="e.g. Bilal" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <label className="inp-lbl">Element username</label>
        <input className="inp" placeholder="@bilal:matrix.org" value={form.matrix} onChange={(e) => setForm({ ...form, matrix: e.target.value })} />
        <label className="inp-lbl">Role</label>
        <div className="pillbtns" style={{ marginBottom: 6 }}>
          {(["DEVELOPER", "QA"] as const).map((r) => (
            <button key={r} className={clsx("pillbtn", form.role === r && "on")} onClick={() => setForm({ ...form, role: r })}>
              {r === "DEVELOPER" ? "Developer" : "QA"}
            </button>
          ))}
        </div>
        <div className="modal-actions">
          <button className="btn ghost" onClick={() => setModalOpen(false)}>Cancel</button>
          <button className="btn primary" onClick={submit}>
            <Icon name={editing ? "check" : "plus"} />
            {editing ? "Save changes" : "Add member"}
          </button>
        </div>
      </Modal>
    </>
  );
}
