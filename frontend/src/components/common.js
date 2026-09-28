import React from "react";

export const cardCls = "bg-[#161F30] border border-[#28354A] rounded-xl";
export const inpCls = "bg-[#0F1626] border border-[#334155] rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-[var(--acc)] placeholder:text-slate-600 transition-colors";
export const btnAcc = "inline-flex items-center justify-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold bg-[var(--acc)] text-[#0B0F17] hover:brightness-110 active:scale-[0.98] transition disabled:opacity-40 disabled:cursor-not-allowed";
export const btnGhost = "inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-semibold bg-[#1E293B] text-slate-300 border border-[#334155] hover:border-[var(--acc)] hover:text-white active:scale-[0.98] transition disabled:opacity-40 disabled:cursor-not-allowed";
export const btnDanger = "inline-flex items-center justify-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-semibold bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20 transition disabled:opacity-40";

export function Field({ label, children, className = "" }) {
  return (
    <label className={`flex flex-col gap-1 text-xs text-slate-400 font-semibold ${className}`}>
      {label}{children}
    </label>
  );
}

export function SectionLabel({ children, className = "" }) {
  return (
    <div className={`text-[11px] uppercase tracking-[0.08em] text-slate-500 font-bold mb-2 ${className}`}>{children}</div>
  );
}

export function EmptyState({ text, good }) {
  return (
    <div className={`text-center py-14 px-5 rounded-xl border border-dashed text-sm ${good ? "text-emerald-400 border-emerald-500/40 bg-emerald-500/5" : "text-slate-500 border-[#334155] bg-[#161F30]"}`}>
      {text}
    </div>
  );
}

const TONES = {
  normal: { border: "#28354A", color: "#F8FAFC" },
  warn: { border: "#F59E0B", color: "#F59E0B" },
  good: { border: "#10B981", color: "#10B981" },
  bad: { border: "#EF4444", color: "#EF4444" },
};
export function MetricCard({ label, value, sub, tone = "normal", testId }) {
  const t = TONES[tone] || TONES.normal;
  return (
    <div data-testid={testId} className={`${cardCls} p-4 border-t-2`} style={{ borderTopColor: t.border }}>
      <div className="text-[10.5px] uppercase tracking-[0.06em] font-bold text-slate-500">{label}</div>
      <div className="text-[22px] font-extrabold mt-1 num" style={{ color: t.color }}>{value}</div>
      {sub && <div className="text-[11.5px] text-slate-500 mt-0.5">{sub}</div>}
    </div>
  );
}

export function PageTitle({ children, right }) {
  return (
    <div className="flex items-end justify-between gap-3 flex-wrap pb-3 mb-5 border-b border-[#28354A]">
      <div className="flex items-center gap-3">
        <span className="w-1.5 h-6 rounded-full" style={{ background: "var(--acc)" }} />
        <h2 className="font-display text-xl font-bold text-slate-100 tracking-tight">{children}</h2>
      </div>
      {right}
    </div>
  );
}

export function Banner({ title, right }) {
  return (
    <div className="flex items-center justify-between gap-3 flex-wrap px-4 py-2.5 rounded-lg mb-2 border-l-4 bg-[#1A2438] border border-[#28354A]" style={{ borderLeftColor: "var(--acc)" }}>
      <div className="font-display text-sm font-bold text-slate-100">{title}</div>
      <div className="flex items-center gap-2">{right}</div>
    </div>
  );
}

export function Pill({ children, color = "#94A3B8", bg = "rgba(148,163,184,0.12)", testId }) {
  return (
    <span data-testid={testId} className="text-[11px] px-2 py-0.5 rounded-full font-bold inline-block" style={{ color, background: bg }}>
      {children}
    </span>
  );
}
