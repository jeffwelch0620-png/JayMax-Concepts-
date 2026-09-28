import React, { useEffect, useRef, useState } from "react";
import { Sparkles, X, Send, Trash2 } from "lucide-react";
import * as api from "../lib/api";
import { RESTAURANTS } from "../lib/calc";
import { inpCls, btnAcc } from "./common";

const SUGGESTIONS = [
  "Which items are below par right now and what will the order cost?",
  "Which menu items are running above their food-cost target?",
  "What should we prep today based on current prep inventory?",
  "How can I lower my highest-cost dish's food cost by 3%?",
];

export function AiAssistant({ rid, setRid, open, onClose }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    if (open) api.aiHistory(rid).then(setMessages).catch(() => setMessages([]));
  }, [open, rid]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, open]);

  async function send(text) {
    const msg = (text ?? input).trim();
    if (!msg || streaming) return;
    setInput("");
    setStreaming(true);
    setMessages((m) => [...m, { role: "user", content: msg }, { role: "assistant", content: "", pending: true }]);
    let gotError = null;
    await api.streamChat(rid, msg, {
      onDelta: (t) => setMessages((m) => {
        const next = [...m];
        const last = next[next.length - 1];
        if (last?.pending) next[next.length - 1] = { ...last, content: last.content + t };
        return next;
      }),
      onError: (e) => { gotError = e; },
      onDone: () => {
        setMessages((m) => {
          const next = [...m];
          const last = next[next.length - 1];
          if (last?.pending) next[next.length - 1] = { role: "assistant", content: gotError || last.content || "No response — try again." };
          return next;
        });
        setStreaming(false);
      },
    });
  }

  async function clearHistory() {
    await api.aiClear(rid).catch(() => {});
    setMessages([]);
  }

  if (!open) return null;

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-full sm:w-[420px] bg-[#0F1626] border-l border-[#28354A] shadow-2xl flex flex-col fade-slide-in" data-testid="ai-assistant-drawer">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#28354A] bg-[#161F30]">
        <div className="flex items-center gap-2">
          <span className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: "var(--acc)" }}>
            <Sparkles size={15} className="text-[#0B0F17]" />
          </span>
          <div>
            <div className="font-display font-bold text-sm text-slate-100">Sous — AI Kitchen Copilot</div>
            <div className="text-[10px] text-slate-500">Powered by ChatGPT · reads live {RESTAURANTS.find((r) => r.id === rid)?.short || ""} data</div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <select className={`${inpCls} py-1 px-2 text-xs`} data-testid="ai-location-select" value={rid} onChange={(e) => setRid(e.target.value)}>
            {RESTAURANTS.map((r) => <option key={r.id} value={r.id}>{r.short}</option>)}
          </select>
          <button onClick={clearHistory} className="p-1.5 text-slate-500 hover:text-red-400 transition" title="Clear conversation" aria-label="Clear conversation" data-testid="ai-clear-button"><Trash2 size={15} /></button>
          <button onClick={onClose} className="p-1.5 text-slate-400 hover:text-white transition" data-testid="ai-close-button"><X size={17} /></button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="mt-4">
            <div className="text-xs text-slate-500 mb-3">Ask about inventory, food costs, prep, or margins — I can see this location's live data. Try one of these:</div>
            <div className="flex flex-col gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => send(s)} className="text-left text-xs px-3 py-2.5 rounded-lg bg-[#161F30] border border-[#28354A] text-slate-300 hover:border-[var(--acc)] hover:text-white transition" data-testid="ai-suggestion-chip">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`} data-testid={`ai-message-${i}`}>
            <div className={`max-w-[85%] rounded-xl px-3.5 py-2.5 text-[13px] leading-relaxed whitespace-pre-wrap ${m.role === "user" ? "bg-[var(--acc)] text-[#0B0F17] font-medium" : "bg-[#161F30] border border-[#28354A] text-slate-200"}`}>
              {m.content}
              {m.pending && !m.content && <span className="inline-block w-2 h-2 rounded-full bg-slate-400 pulse-dot" />}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="p-3 border-t border-[#28354A] bg-[#161F30]">
        <div className="flex gap-2">
          <input
            className={`${inpCls} flex-1`}
            data-testid="ai-assistant-input-field"
            placeholder="Ask about costs, prep, ordering…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") send(); }}
            disabled={streaming}
          />
          <button className={btnAcc} onClick={() => send()} disabled={streaming || !input.trim()} data-testid="ai-assistant-send-button">
            <Send size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}
