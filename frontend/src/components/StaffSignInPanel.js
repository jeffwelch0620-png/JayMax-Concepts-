import React, { useCallback, useEffect, useState } from "react";
import { KeyRound, Unlock } from "lucide-react";
import { cardCls, inpCls, btnGhost, Pill, EmptyState } from "./common";
import * as api from "../lib/api";

const PIN = /^[0-9]{4,5}$/;
const when = (iso) => iso ? new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "never";

// Staff sign-in for managers (Jeff 2026-10-31): an owner or the Ops Lead issues each employee's
// first PIN (and any reset), which the employee replaces at first sign-in; a manager or above
// unlocks someone after 5 wrong PINs. Shift Leaders see the list but can't unlock.
export function StaffSignInPanel({ rid, showToast, rosterKey }) {
  const user = api.currentSession()?.user || {};
  const canIssue = user.role === "owner";
  const canUnlock = user.role === "owner" || (user.role === "manager" && !String(user.position || "").startsWith("SL-"));
  const [staff, setStaff] = useState(null);
  const [switchedOn, setSwitchedOn] = useState(false);
  const [installed, setInstalled] = useState(true);
  const [issuing, setIssuing] = useState(null);   // { id, pin, key }
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const refresh = useCallback(async () => {
    if (!rid) return;
    try { const r = await api.staffSignInRoster(rid); setStaff(r.staff); setSwitchedOn(!!r.switched_on); setInstalled(true); setErr(""); }
    catch (e) {
      if (e?.response?.status === 503) { setInstalled(false); return; }   // not set up on this server yet
      setStaff([]); setErr(e?.response?.data?.detail || "Couldn't load staff sign-in");
    }
  }, [rid]);
  // The roster below changes who is listed here (added, deactivated, reactivated).
  useEffect(() => { refresh(); }, [refresh, rosterKey]);

  async function issue() {
    if (!PIN.test(issuing.pin)) { setErr("A PIN is 4 or 5 digits"); return; }
    setBusy(true); setErr("");
    try {
      await api.issueStaffPin(rid, issuing.id, issuing.pin, issuing.key);
      showToast?.("PIN issued. Give it to them in person; they choose their own at first sign-in.");
      setIssuing(null);
      await refresh();
    } catch (e) { setErr(e?.response?.data?.detail || "Couldn't issue the PIN"); }
    finally { setBusy(false); }
  }

  async function unlock(member) {
    setBusy(true); setErr("");
    try { await api.unlockStaffSignIn(rid, member.staff_member_id); showToast?.(`${member.name} can sign in again`); await refresh(); }
    catch (e) { setErr(e?.response?.data?.detail || "Couldn't unlock"); }
    finally { setBusy(false); }
  }

  if (!installed) return null;
  return (
    <div className="mb-8" data-testid="staff-sign-in-panel">
      <div className="font-display font-bold text-slate-100 mb-1">Staff sign-in</div>
      <div className="text-xs text-slate-500 mb-4">
        Each employee signs in with their own name and a 4–5 digit PIN. {canIssue ? "Issue a first PIN and give it to them in person; they replace it the first time they sign in." : "An owner or the Ops Lead issues PINs."}
      </div>
      {!switchedOn && <div className="text-xs text-amber-300 mb-4" data-testid="staff-sign-in-not-on">Personal sign-in isn't switched on yet: staff still use the store PIN. Issue everyone a PIN first; switching on retires the store PIN at every store at once.</div>}
      {err && <div className="text-red-400 text-xs mb-3" role="alert">{err}</div>}
      {!staff ? null : staff.length === 0 ? <EmptyState text="No active staff yet. Add them to the roster below." /> : (
        <div className="flex flex-col gap-2">
          {staff.map((m) => (
            <div key={m.staff_member_id} className={`${cardCls} p-3 flex items-center gap-3 flex-wrap`} data-testid={`staff-sign-in-${m.staff_member_id}`}>
              <div className="font-bold text-slate-100 text-sm flex-1 min-w-[140px]">{m.name}</div>
              {!m.has_pin ? <Pill color="#F59E0B" bg="rgba(245,158,11,0.12)">No PIN</Pill>
                : m.temporary_pin ? <Pill color="#38BDF8" bg="rgba(56,189,248,0.12)">First PIN issued</Pill>
                : <Pill color="#22C55E" bg="rgba(34,197,94,0.12)">PIN set</Pill>}
              {m.locked_until && <Pill color="#F87171" bg="rgba(248,113,113,0.12)">Locked until {new Date(m.locked_until).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</Pill>}
              {m.signed_in && <Pill color="#22C55E" bg="rgba(34,197,94,0.12)">Signed in</Pill>}
              <span className="text-xs text-slate-500">Last sign-in: {when(m.last_signed_in_at)}</span>
              {m.locked_until && canUnlock && <button className={btnGhost} disabled={busy} onClick={() => unlock(m)} data-testid={`staff-unlock-${m.staff_member_id}`}><Unlock size={13} /> Unlock</button>}
              {canIssue && (issuing?.id === m.staff_member_id ? (
                <span className="flex items-center gap-2">
                  <input className={`${inpCls} w-24 text-center`} inputMode="numeric" aria-label={`New PIN for ${m.name}`} maxLength={5} value={issuing.pin}
                    onChange={(e) => setIssuing({ ...issuing, pin: e.target.value.replace(/\D/g, ""), key: crypto.randomUUID() })} data-testid={`staff-issue-pin-${m.staff_member_id}`} />
                  <button className={btnGhost} disabled={busy} onClick={issue} data-testid={`staff-issue-save-${m.staff_member_id}`}>{busy ? "Saving…" : "Issue"}</button>
                  <button className={btnGhost} disabled={busy} onClick={() => setIssuing(null)}>Cancel</button>
                </span>
              ) : (
                <button className={btnGhost} disabled={busy} onClick={() => setIssuing({ id: m.staff_member_id, pin: "", key: crypto.randomUUID() })}
                  data-testid={`staff-issue-${m.staff_member_id}`}><KeyRound size={13} /> {m.has_pin ? "Reset PIN" : "Issue first PIN"}</button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
