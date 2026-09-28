import React from "react";
import { CalendarClock, ClipboardCheck, GraduationCap, BookMarked } from "lucide-react";
import { PageTitle, cardCls } from "./common";

const PLANNED = [
  { icon: CalendarClock, title: "Shift Scheduling", desc: "Weekly shift planner per location with labor-cost % tracked against projected sales.", accent: "#F97316" },
  { icon: ClipboardCheck, title: "Checklists & Compliance", desc: "Opening/closing checklists, temp logs, and food-safety compliance sign-offs.", accent: "#10B981" },
  { icon: GraduationCap, title: "Training", desc: "Role-based training modules with completion tracking for every station.", accent: "#3B82F6" },
  { icon: BookMarked, title: "SOP Library", desc: "Searchable standard operating procedures linked to recipes and prep lists.", accent: "#EAB308" },
];

export function SchedulingTab() {
  return (
    <div className="fade-slide-in" data-testid="scheduling-tab">
      <PageTitle>Operations — Coming Next</PageTitle>
      <div className="text-xs text-slate-500 -mt-3 mb-5">
        Scheduling is the next module in the roadmap, followed by checklists/compliance, training, and SOPs. These will plug into this same per-location workspace.
      </div>
      <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))" }}>
        {PLANNED.map((p) => {
          const Icon = p.icon;
          return (
            <div key={p.title} className={`${cardCls} p-5`} data-testid={`planned-${p.title.toLowerCase().replace(/[^a-z]+/g, "-")}`} style={{ borderTopWidth: 2, borderTopColor: p.accent }}>
              <div className="w-9 h-9 rounded-lg flex items-center justify-center mb-3" style={{ background: `${p.accent}22` }}>
                <Icon size={18} style={{ color: p.accent }} />
              </div>
              <div className="font-display font-bold text-slate-100 mb-1">{p.title}</div>
              <div className="text-xs text-slate-400 leading-relaxed">{p.desc}</div>
              <div className="mt-3 text-[10px] uppercase tracking-widest font-bold text-slate-600">In roadmap</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
