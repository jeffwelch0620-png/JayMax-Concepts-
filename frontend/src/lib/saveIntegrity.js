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

// Drafts belong to the signed-in App instance, keyed by restaurant and form.
// They survive tab/location navigation, but do not outlive logout or app reload.
export function useRetainedDraft(key, initial, drafts, sync = false) {
  const privateDrafts = useRef(new Map());
  const cache = drafts || privateDrafts.current;
  const [value, setValue] = useState(() => cache.has(key) ? cache.get(key) : initial);
  const current = useRef(value);
  const mounted = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
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
    return true;
  }
  return [value, edit, acknowledge, cache.has(key)];
}
