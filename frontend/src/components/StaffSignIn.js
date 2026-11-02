import React, { useEffect, useRef, useState } from "react";
import { storeMark } from "../theme/storeMark";
import { Lock } from "lucide-react";
import { RESTAURANTS } from "../lib/calc";
import * as api from "../lib/api";
import { inpCls, btnAcc, btnGhost, cardCls } from "./common";

const PIN = /^[0-9]{4,5}$/;
const detail = (e, fallback) => {
  const d = e?.response?.data?.detail;
  return typeof d === "string" ? d : d?.message || fallback;
};

// Employee sign-in: own name and PIN (Jeff 2026-10-30). The name is typed, with matches from 2
// letters on, so the store's roster is never listed. A first PIN from an owner is replaced here.
export function StaffSignIn({ rid, setRid, onSignedIn }) {
  const remembered = api.rememberedStaff(rid);
  const [member, setMember] = useState(remembered ? { id: remembered.id, name: remembered.name } : null);
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState([]);
  const [pin, setPin] = useState("");
  const [newPin, setNewPin] = useState(null);   // set once the server asks for the employee's own PIN
  const [confirmPin, setConfirmPin] = useState("");
  const [remember, setRemember] = useState(!!remembered);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const lookups = useRef(0);
  const attempts = useRef(0), pinBox = useRef(null);   // a store change, "Not you?" or leaving abandons a pending sign-in
  useEffect(() => () => { attempts.current += 1; }, []);

  useEffect(() => {
    attempts.current += 1; setBusy(false);   // a pending sign-in for the old store is abandoned
    const r = api.rememberedStaff(rid);
    setMember(r ? { id: r.id, name: r.name } : null); setRemember(!!r);
    setQuery(""); setMatches([]); setPin(""); setNewPin(null); setConfirmPin(""); setErr("");
  }, [rid]);

  useEffect(() => {
    const sequence = ++lookups.current;
    if (!rid || member || query.trim().length < 2) { setMatches([]); return undefined; }
    const timer = setTimeout(() => {
      api.staffSignInNames(rid, query.trim())
        .then(names => { if (sequence === lookups.current) setMatches(names); })
        .catch(() => { if (sequence === lookups.current) setMatches([]); });
    }, 200);
    return () => clearTimeout(timer);
  }, [rid, member, query]);

  function notMe() {
    attempts.current += 1; setBusy(false);
    api.rememberStaff(rid, null);
    setMember(null); setRemember(false); setQuery(""); setPin(""); setNewPin(null); setConfirmPin(""); setErr("");
  }

  async function signIn() {
    if (busy) return;
    setErr("");
    if (!rid) { setErr("Pick your restaurant first"); return; }
    if (!member) { setErr("Type your name and pick it from the list"); return; }
    if (!PIN.test(pin)) { setErr("Your PIN is 4 or 5 digits"); return; }
    if (newPin !== null) {
      if (!PIN.test(newPin)) { setErr("Choose a new PIN of 4 or 5 digits"); return; }
      if (newPin !== confirmPin) { setErr("The two new PINs don't match"); return; }
    }
    setBusy(true);
    const attempt = ++attempts.current;
    try {
      const session = await api.staffSignIn(rid, { staff_member_id: member.id, pin, ...(newPin !== null ? { new_pin: newPin } : {}) });
      if (attempt !== attempts.current) return;   // abandoned: never keep or use this session
      api.keepStaffSession(session);
      api.rememberStaff(rid, remember ? member : null);
      setPin(""); setNewPin(null); setConfirmPin("");
      onSignedIn(session);
    } catch (e) {
      if (attempt !== attempts.current) return;
      const status = e?.response?.status;
      if (status === 409 && e?.response?.data?.detail?.code === "pin_change_required") { setNewPin(""); setErr(""); return; }
      setPin("");
      setErr(detail(e, status === 401 ? "Name or PIN not recognised" : "Couldn't sign in. Try again."));
    } finally { if (attempt === attempts.current) setBusy(false); }
  }

  const enter = (e) => { if (e.key === "Enter") signIn(); };
  return (
    <div className={`${cardCls} p-6`} data-testid="staff-sign-in">
      <div className="flex items-center gap-2 mb-4"><Lock size={16} style={{ color: "#F97316" }} /><span className="font-display font-bold text-slate-100">Sign in with your name and PIN</span></div>
      <div className="flex gap-2 mb-4 flex-wrap">
        {RESTAURANTS.map((r) => (
          <button key={r.id} onClick={() => setRid(r.id)} data-testid={`staff-store-${r.id}`}
            className={`rounded-full px-4 py-2 text-sm font-bold border transition ${rid === r.id ? "text-jm-on-accent" : "text-slate-400 bg-jm-surface border-jm-line"}`}
            style={rid === r.id ? { background: storeMark(r.id), borderColor: storeMark(r.id) } : {}}>
            {r.short}
          </button>
        ))}
      </div>
      {member ? (
        <div className="flex items-center gap-3 mb-3" data-testid="staff-sign-in-name">
          <span className="font-bold text-slate-100">{member.name}</span>
          <button className={btnGhost} onClick={notMe} data-testid="staff-not-me">Not you?</button>
        </div>
      ) : (
        <div className="mb-3">
          <input className={`${inpCls} w-full`} aria-label="Your name" placeholder="Start typing your name" autoComplete="off"
            value={query} onChange={(e) => setQuery(e.target.value)} disabled={!rid} data-testid="staff-name-entry" />
          {matches.length > 0 && <div className="flex flex-col gap-1 mt-2" data-testid="staff-name-matches">
            {matches.map((m) => (
              <button key={m.id} className={`${cardCls} p-2 text-left font-bold text-slate-100`} onClick={() => { setMember(m); setMatches([]); setTimeout(() => pinBox.current?.focus(), 0); }}
                data-testid={`staff-name-${m.id}`}>{m.name}</button>
            ))}
          </div>}
        </div>
      )}
      {/* The PIN box appears once a name is picked, with the cursor in it, so nothing moves under a tap (step E). */}
      {member && <input type="password" inputMode="numeric" autoComplete="off" aria-label={newPin === null ? "Your PIN" : "PIN you were given"}
        className={`${inpCls} w-full text-center text-xl tracking-[0.4em] mb-3`} placeholder="••••" maxLength={5} ref={pinBox}
        value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))} onKeyDown={newPin === null ? enter : undefined} data-testid="staff-pin-entry" />}
      {newPin !== null && <div className="flex flex-col gap-2 mb-3" data-testid="staff-new-pin">
        <p className="text-sm text-slate-300">Choose your own PIN (4 or 5 digits). It can match your Toast clock-in code.</p>
        <input type="password" inputMode="numeric" autoComplete="off" aria-label="New PIN" className={`${inpCls} text-center text-xl tracking-[0.4em]`}
          maxLength={5} value={newPin} onChange={(e) => setNewPin(e.target.value.replace(/\D/g, ""))} data-testid="staff-new-pin-entry" />
        <input type="password" inputMode="numeric" autoComplete="off" aria-label="New PIN again" className={`${inpCls} text-center text-xl tracking-[0.4em]`}
          maxLength={5} value={confirmPin} onChange={(e) => setConfirmPin(e.target.value.replace(/\D/g, ""))} onKeyDown={enter} data-testid="staff-new-pin-confirm" />
      </div>}
      <label className="flex items-center gap-2 text-sm text-slate-400 mb-4">
        <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} data-testid="staff-remember-me" />
        Remember my name on this device
      </label>
      <button className={`${btnAcc} w-full justify-center`} onClick={signIn} disabled={busy} data-testid="staff-sign-in-button">{busy ? "Signing in…" : "Sign in"}</button>
      {err && <div className="text-red-400 text-xs mt-3" role="alert" data-testid="staff-error">{err}</div>}
    </div>
  );
}
