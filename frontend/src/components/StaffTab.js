import React, { useEffect, useState } from "react";
import { Users, Plus, Trash2 } from "lucide-react";
import { PageTitle, cardCls, inpCls, btnAcc, btnGhost, btnDanger, Pill, EmptyState } from "./common";
import * as api from "../lib/api";

const ROLES = [
  { id: "cook", label: "Cook" },
  { id: "owner_admin", label: "Owner / Admin" },
];

// Named staff roster tied to the shared PIN portal (StaffSheet): after entering the
// restaurant's PIN, staff pick their name from this list. Role determines what that
// identification unlocks — Cook stays in the PIN-only Prep/Counts/Tasks portal, while
// Owner/Admin gets a full manager-equivalent session for this restaurant.
export function StaffTab({ rid, showToast }) {
  const [members, setMembers] = useState(null);
  const [name, setName] = useState("");
  const [role, setRole] = useState("cook");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function refresh() {
    if (!rid) return;
    try { setMembers(await api.listStaffMembers(rid)); } catch { setMembers([]); }
  }
  useEffect(() => { refresh(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [rid]);

  async function add() {
    setErr("");
    if (!name.trim()) { setErr("Enter a name"); return; }
    setBusy(true);
    try {
      await api.createStaffMember(rid, { name: name.trim(), role });
      setName("");
      await refresh();
      showToast?.("Staff member added");
    } catch (e) { setErr(e?.response?.data?.detail || "Couldn't add staff member"); }
    finally { setBusy(false); }
  }

  async function changeRole(m, newRole) {
    await api.updateStaffMember(rid, m.id, { name: m.name, role: newRole, active: m.active });
    await refresh();
  }

  async function toggleActive(m) {
    await api.updateStaffMember(rid, m.id, { name: m.name, role: m.role, active: !m.active });
    await refresh();
  }

  async function remove(m) {
    await api.deleteStaffMember(rid, m.id);
    await refresh();
  }

  return (
    <div className="fade-slide-in" data-testid="staff-tab">
      <PageTitle>Staff</PageTitle>
      <div className="text-xs text-slate-500 -mt-2 mb-5">
        Anyone who taps in with the shared PIN picks their name from this list. Cooks get the Prep/Counts/Tasks
        portal only; Owner/Admin gets full access to this restaurant, same as an email/password owner login.
      </div>

      <div className={`${cardCls} p-5 mb-6`} data-testid="add-staff-panel">
        <div className="font-display font-bold text-slate-100 mb-3">Add Staff Member</div>
        <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))" }}>
          <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Name
            <input className={inpCls} data-testid="staff-add-name" placeholder="e.g. Maria" value={name}
              onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") add(); }} />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Role
            <select className={inpCls} data-testid="staff-add-role" value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select>
          </label>
        </div>
        {err && <div className="text-red-400 text-xs mt-3">{err}</div>}
        <div className="mt-4 flex justify-end">
          <button className={btnAcc} onClick={add} disabled={busy} data-testid="staff-add-submit"><Plus size={14} /> {busy ? "Adding…" : "Add Staff Member"}</button>
        </div>
      </div>

      <div>
        <div className="text-[11px] uppercase tracking-[0.08em] text-slate-500 font-bold mb-2">Roster</div>
        {!members || members.length === 0 ? (
          <EmptyState text="No staff members yet. Add one above." />
        ) : (
          <div className="flex flex-col gap-2" data-testid="staff-member-list">
            {members.map((m) => (
              <div key={m.id} className={`${cardCls} p-3 flex items-center justify-between gap-3`} style={m.active ? {} : { opacity: 0.55 }} data-testid={`staff-member-${m.id}`}>
                <div className="flex items-center gap-2 flex-1">
                  <Users size={15} className="text-slate-500" />
                  <div className="font-bold text-slate-100 text-sm">{m.name}</div>
                  {!m.active && <Pill color="#94A3B8" bg="rgba(148,163,184,0.12)">Inactive</Pill>}
                </div>
                <select className={inpCls} style={{ width: 160 }} data-testid={`staff-member-role-${m.id}`}
                  value={m.role} onChange={(e) => changeRole(m, e.target.value)}>
                  {ROLES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
                </select>
                <button className={btnGhost} onClick={() => toggleActive(m)} data-testid={`staff-member-toggle-${m.id}`}>
                  {m.active ? "Deactivate" : "Reactivate"}
                </button>
                <button className={btnDanger} onClick={() => remove(m)} data-testid={`staff-member-delete-${m.id}`}><Trash2 size={12} /></button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
