import React, { useState } from "react";
import { authLogin } from "../lib/api";

export function Login({ onLogin, onOpenStaff, notice }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const result = await authLogin(email, password);
      onLogin(result);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to sign in");
    }
  };
  return (
    <main className="min-h-screen bg-[#0B0F17] text-slate-100 flex items-center justify-center p-6">
      <form onSubmit={submit} className="w-full max-w-sm rounded-2xl border border-[#28354A] bg-[#161F30] p-6 space-y-4">
        <div>
          <h1 className="font-display text-2xl font-bold">Sign in to JayMax</h1>
          <p className="text-sm text-slate-400 mt-1">Use your collaboration account.</p>
        </div>
        <input className="w-full rounded-lg bg-[#0B0F17] border border-[#334155] p-3" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" autoComplete="email" />
        <input className="w-full rounded-lg bg-[#0B0F17] border border-[#334155] p-3" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" autoComplete="current-password" />
        {notice && !error && <p className="text-sm text-amber-300" data-testid="login-notice">{notice}</p>}
        {error && <p className="text-sm text-red-300">{error}</p>}
        <button className="w-full rounded-lg bg-orange-500 text-slate-950 font-bold p-3" type="submit">Sign in</button>
        {onOpenStaff && (
          <button type="button" onClick={onOpenStaff} className="w-full text-sm text-slate-400 hover:text-white transition">
            Staff sign-in with PIN
          </button>
        )}
      </form>
    </main>
  );
}
