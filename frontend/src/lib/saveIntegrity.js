import { useCallback, useEffect, useRef, useState } from "react";

export function confirmed(result) {
  return !!result && typeof result === "object" && result.ok !== false
    && Number.isSafeInteger(result.revision) && result.revision >= 0;
}

export async function confirmSave(save, onError) {
  try {
    if (!confirmed(await save())) throw new Error("Save was not confirmed. Your draft has been retained.");
    return true;
  } catch (error) {
    onError(error?.response?.data?.detail || error.message || "Save failed. Your draft has been retained.");
    return false;
  }
}

// Focus markers share this cache but are navigation metadata, not unsaved forms.
export const hasUnsavedDrafts = cache => [...cache.keys()].some(key => !key.startsWith("recipe-focus:"));

export function useDraftUnloadWarning(drafts) {
  useEffect(() => {
    const warn = event => {
      if (hasUnsavedDrafts(drafts.current)) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [drafts]);
}

// Drafts belong to the signed-in App instance, keyed by restaurant and form.
// They survive tab/location navigation, but do not outlive logout or app reload.
const acknowledgements = new WeakMap();
export function useRetainedDraft(key, initial, drafts, sync = false) {
  const privateDrafts = useRef(new Map());
  const cache = drafts || privateDrafts.current;
  const [value, setValue] = useState(() => cache.has(key) ? cache.get(key) : initial);
  const current = useRef(value);
  const mounted = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    let keys = acknowledgements.get(cache);
    if (!keys) { keys = new Map(); acknowledgements.set(cache, keys); }
    let listeners = keys.get(key);
    if (!listeners) { listeners = new Set(); keys.set(key, listeners); }
    const receive = (submitted, next) => {
      if (current.current === submitted) { current.current = next; setValue(next); }
    };
    listeners.add(receive);
    return () => { listeners.delete(receive); if (!listeners.size) keys.delete(key); };
  }, [cache, key]);
  useEffect(() => {
    if (sync && !cache.has(key)) { current.current = initial; setValue(initial); }
  }, [cache, key, initial, sync]);
  const edit = useCallback(next => {
    const resolved = typeof next === "function" ? next(current.current) : next;
    current.current = resolved; cache.set(key, resolved);
    if (mounted.current) setValue(resolved);
  }, [cache, key]);
  function acknowledge(submitted, next = initial) {
    if (current.current !== submitted || (cache.has(key) && cache.get(key) !== submitted)) return false;
    cache.delete(key); current.current = next;
    if (mounted.current) setValue(next);
    // A -> B -> A may remount the same retained form before its receipt arrives.
    // Only instances still displaying the exact submitted draft accept it.
    acknowledgements.get(cache)?.get(key)?.forEach(receive => receive(submitted, next));
    return true;
  }
  return [value, edit, acknowledge, cache.has(key)];
}
