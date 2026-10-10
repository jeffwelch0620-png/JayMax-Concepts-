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
  const [messages, setMessages] = useState(null);
  const [capabilities, setCapabilities] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [retry, setRetry] = useState(0);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef(null);
  const generation = useRef(0), operation = useRef(false), controller = useRef(null);

  useEffect(() => {
    const lifecycle = generation, streamController = controller;
    const active = ++generation.current;
    controller.current?.abort(); operation.current = false;
    setMessages(null); setCapabilities(null); setStreaming(false); setClearing(false); setError("");
    if (open) {
      setLoading(true);
      Promise.all([api.aiHistory(rid), api.aiCapabilities(rid)]).then(([history, status]) => {
        if (generation.current !== active) return;
        if (!Array.isArray(history) || history.some(m => m.restaurantId !== rid || !["user", "assistant"].includes(m.role) || typeof m.content !== "string")
            || status?.storeId !== (rid === "papa_leonis" ? "papa" : rid) || status.basis !== "ai_conversation_storage" || status.accounting !== false
            || ["historyAvailable", "chatAvailable", "clearAvailable"].some(key => typeof status[key] !== "boolean") || !status.historyAvailable) {
          throw new Error("Conversation history was not confirmed.");
        }
        setMessages(history); setCapabilities(status);
      }).catch(e => { if (generation.current === active) setError(e?.response?.data?.detail || e.message || "Conversation history unavailable."); })
        .finally(() => { if (generation.current === active) setLoading(false); });
    }
    return () => { ++lifecycle.current; streamController.current?.abort(); };
  }, [open, rid, retry]);
  useEffect(() => { setInput(""); }, [rid]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, open]);

  async function send(text) {
    const msg = (text ?? input).trim();
    if (!msg || operation.current || error || !capabilities?.chatAvailable || messages === null) return;
    const active = generation.current;
    operation.current = true; controller.current = new AbortController(); setError("");
    setStreaming(true);
    setMessages((m) => [...m, { role: "user", content: msg }, { role: "assistant", content: "", pending: true }]);
    let gotError = null, received = "";
    try { await api.streamChat(rid, msg, {
      signal: controller.current.signal,
      onDelta: (t) => { received += t; if (generation.current === active) setMessages((m) => {
        const next = [...m];
        const last = next[next.length - 1];
        if (last?.pending) next[next.length - 1] = { ...last, content: last.content + t };
        return next;
      }); },
      onError: (e) => { gotError = e; },
      onDone: () => {
        if (generation.current !== active) return;
        if (!gotError && !received) gotError = "No response was confirmed.";
        setMessages((m) => {
          const next = [...m];
          const last = next[next.length - 1];
          if (last?.pending) next[next.length - 1] = { role: "assistant", content: last.content, pending: false };
          return next;
        });
        setStreaming(false);
        if (gotError) setError(`${gotError} Your entry is retained. Refresh history before retrying.`);
        else setInput(p => p.trim() === msg ? "" : p);
      },
    }); } catch (e) { if (generation.current === active) setError("Conversation failed. Your entry is retained; refresh history before retrying."); }
    finally { if (generation.current === active) { operation.current = false; setStreaming(false); } }
  }

  async function clearHistory() {
    if (operation.current || !capabilities?.clearAvailable || messages === null) return;
    const active = generation.current; operation.current = true; setClearing(true); setError("");
    try {
      const result = await api.aiClear(rid);
      if (generation.current !== active) return;
      if (result?.ok !== true) throw new Error("Conversation clear was not confirmed.");
      setMessages([]);
    } catch (e) { if (generation.current === active) setError(e?.response?.data?.detail || e.message || "Could not clear conversation. History is retained."); }
    finally { if (generation.current === active) { operation.current = false; setClearing(false); } }
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
            <div className="text-[10px] text-slate-500">{RESTAURANTS.find((r) => r.id === rid)?.short || ""} · Conversation history</div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <select className={`${inpCls} py-1 px-2 text-xs`} data-testid="ai-location-select" value={rid} onChange={(e) => setRid(e.target.value)}>
            {RESTAURANTS.map((r) => <option key={r.id} value={r.id}>{r.short}</option>)}
          </select>
          <button onClick={clearHistory} disabled={streaming || clearing || !capabilities?.clearAvailable || messages === null} className="p-1.5 text-slate-500 hover:text-red-400 transition" title="Clear conversation" aria-label="Clear conversation" data-testid="ai-clear-button"><Trash2 size={15} /></button>
          <button onClick={onClose} className="p-1.5 text-slate-400 hover:text-white transition" data-testid="ai-close-button"><X size={17} /></button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {loading && <p role="status">Loading conversation history…</p>}
        {error && <p role="alert">{error}</p>}
        {capabilities && !capabilities.chatAvailable && <p data-testid="ai-readonly-status">History is available for reference. Chat is unavailable until conversation storage is enabled.</p>}
        <button disabled={streaming || clearing || loading} onClick={() => setRetry(n => n + 1)} data-testid="ai-history-retry">Refresh history</button>
        {messages?.length === 0 && capabilities?.chatAvailable && (
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
        {messages?.map((m, i) => (
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
            disabled={streaming || clearing || !capabilities?.chatAvailable || messages === null}
          />
          <button className={btnAcc} onClick={() => send()} disabled={streaming || clearing || !!error || !capabilities?.chatAvailable || messages === null || !input.trim()} data-testid="ai-assistant-send-button">
            <Send size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}
