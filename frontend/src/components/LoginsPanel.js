import React, { useEffect, useState } from "react";
import { KeyRound, Plus, Trash2 } from "lucide-react";
import { cardCls, inpCls, btnAcc, btnGhost, btnDanger, Pill, EmptyState } from "./common";
import { RESTAURANTS } from "../lib/calc";
import * as api from "../lib/api";

const LOGIN_ROLES = [
  { id: "manager", label: "Manager" },
  { id: "staff", label: "Staff (prep only)" },
  { id: "readonly", label: "Read-only" },
  { id: "owner", label: "Owner (all stores)" },
];
const MIN_PW = 12;

// Email/password accounts (app_users). Owner only. Separate from the PIN roster below:
// a login is for someone who signs in on their own device; the roster is for the shared PIN.
export function LoginsPanel({ showToast }) {
  const me = api.currentSession()?.user;
  const [users, setUsers] = useState(null);
  const [form, setForm] = useState({ email: "", password: "", role: "manager", locations: [] });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function refresh() {
    try { setUsers(await api.listLogins()); } catch (e) { setErr(e?.response?.data?.detail || "Couldn't load logins"); setUsers([]); }
  }
  useEffect(() => { refresh(); }, []);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const toggleLoc = (id) => set("locations", form.locations.includes(id) ? form.locations.filter((l) => l !== id) : [...form.locations, id]);

  async function add() {
    setErr("");
    if (!form.email.trim().includes("@")) { setErr("Enter a valid email"); return; }
    if (form.password.length < MIN_PW) { setErr(`Password must be at least ${MIN_PW} characters`); return; }
    if (form.role !== "owner" && form.locations.length === 0) { setErr("Pick at least one store"); return; }
    setBusy(true);
    try {
      await api.createLogin({ ...form, email: form.email.trim() });
      setForm({ email: "", password: "", role: "manager", locations: [] });
      await refresh();
      showToast?.("Login created");
    } catch (e) { setErr(e?.response?.data?.detail || "Couldn't create login"); }
    finally { setBusy(false); }
  }

  async function resetPassword(u) {
    const pw = window.prompt(`New password for ${u.email} (at least ${MIN_PW} characters):`);
    if (pw == null) return;
    if (pw.length < MIN_PW) { setErr(`Password must be at least ${MIN_PW} characters`); return; }
    try { await api.resetLoginPassword(u.id, pw); showToast?.("Password updated"); }
    catch (e) { setErr(e?.response?.data?.detail || "Couldn't update password"); }
  }

  async function remove(u) {
    if (!window.confirm(`Remove login ${u.email}?`)) return;
    try { await api.deleteLogin(u.id); await refresh(); showToast?.("Login removed"); }
    catch (e) { setErr(e?.response?.data?.detail || "Couldn't remove login"); }
  }

  const storeName = (id) => RESTAURANTS.find((r) => r.id === id)?.short || id;

  return (
    <div className={`${cardCls} p-5 mb-8`} data-testid="logins-panel">
      <div className="font-display font-bold text-slate-100 mb-1">Email / Password Logins</div>
      <div className="text-xs text-slate-500 mb-4">For people who sign in with their own email. Owner only.</div>

      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))" }}>
        <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Email
          <input className={inpCls} data-testid="login-add-email" type="email" autoComplete="off" value={form.email} onChange={(e) => set("email", e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Password ({MIN_PW}+ chars)
          <input className={inpCls} data-testid="login-add-password" type="password" autoComplete="new-password" value={form.password} onChange={(e) => set("password", e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-400 font-semibold">Role
          <select className={inpCls} data-testid="login-add-role" value={form.role} onChange={(e) => set("role", e.target.value)}>
            {LOGIN_ROLES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
          </select>
        </label>
      </div>
      {form.role !== "owner" && (
        <div className="flex flex-wrap gap-4 mt-3 text-xs text-slate-300">
          {RESTAURANTS.map((r) => (
            <label key={r.id} className="flex items-center gap-1.5">
              <input type="checkbox" data-testid={`login-add-loc-${r.id}`} checked={form.locations.includes(r.id)} onChange={() => toggleLoc(r.id)} /> {r.short}
            </label>
          ))}
        </div>
      )}
      {err && <div className="text-red-400 text-xs mt-3" data-testid="login-error">{err}</div>}
      <div className="mt-4 flex justify-end">
        <button className={btnAcc} onClick={add} disabled={busy} data-testid="login-add-submit"><Plus size={14} /> {busy ? "Creating…" : "Create Login"}</button>
      </div>

      <div className="mt-5 flex flex-col gap-2" data-testid="login-list">
        {!users ? null : users.length === 0 ? <EmptyState text="No logins yet." /> : users.map((u) => (
          <div key={u.id} className="bg-[#0F1626] border border-[#28354A] rounded-lg p-3 flex flex-wrap items-center gap-3" data-testid={`login-${u.id}`}>
            <KeyRound size={14} className="text-slate-500" />
            <div className="font-bold text-slate-100 text-sm flex-1 min-w-[160px] break-all">{u.email}</div>
            <Pill>{u.role}</Pill>
            <div className="text-xs text-slate-400">{u.role === "owner" ? "All stores" : u.locations.map(storeName).join(", ") || "No stores"}</div>
            <button className={btnGhost} onClick={() => resetPassword(u)} data-testid={`login-reset-${u.id}`}>Reset password</button>
            <button className={btnDanger} onClick={() => remove(u)} disabled={u.id === me?.id} title={u.id === me?.id ? "You can't remove yourself" : ""} data-testid={`login-delete-${u.id}`}><Trash2 size={12} /></button>
          </div>
        ))}
      </div>
    </div>
  );
}
