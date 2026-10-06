import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as api from "./api";
import { confirmed } from "./saveIntegrity";

export function useStoreState(rid, session, empty, onError) {
  const scope = useMemo(() => ({ rid, session, revision: null, loaded: false, reads: 0 }), [rid, session]);
  const active = useRef(scope); active.current = scope;
  const pending = useRef(new Map());
  const writes = useRef(new Map());
  const alive = useRef(true);
  const errors = useRef(onError); errors.current = onError;
  const [snapshot, setSnapshot] = useState(null);
  const isCurrent = useCallback(() => alive.current && active.current === scope, [scope]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  const refresh = useCallback(async () => {
    if (!session || rid === "owner" || !isCurrent() || pending.current.has(rid)) return;
    const read = ++scope.reads, generation = writes.current.get(rid) || 0;
    try {
      const data = await api.fetchState(rid);
      if (!isCurrent() || read !== scope.reads || generation !== (writes.current.get(rid) || 0) || pending.current.has(rid)) return;
      if (!data || !Number.isSafeInteger(data.revision) || data.revision < 0) throw new Error("Location data was not confirmed.");
      for (const name of ["items", "dishes", "purchases", "areas", "adjustments", "reportingPeriods", "prepStock", "prepLogs"]) {
        if (data[name] !== undefined && !Array.isArray(data[name])) throw new Error("Location collections were not confirmed.");
      }
      if (scope.loaded && data.revision < scope.revision) return;
      scope.revision = data.revision; scope.loaded = true;
      setSnapshot({ scope, data: { ...empty, ...data } });
    } catch (error) {
      if (isCurrent()) errors.current(error?.response?.data?.detail || error.message || "Couldn't load location data.");
    }
  }, [rid, session, scope, isCurrent, empty]);
  const refreshRef = useRef(refresh); refreshRef.current = refresh;
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 15000);
    return () => clearInterval(timer);
  }, [refresh]);

  const save = useCallback(async (name, next, expectedRevision) => {
    if (!isCurrent()) return null;
    if (!scope.loaded || pending.current.has(rid)) {
      errors.current("Another save or location load is pending. Your draft is retained; try again when it finishes.");
      return null;
    }
    if (expectedRevision != null && expectedRevision !== scope.revision) {
      errors.current("This draft is based on older data. Review the latest saved period before replacing it.");
      return null;
    }
    const revision = scope.revision;
    pending.current.set(rid, scope); writes.current.set(rid, (writes.current.get(rid) || 0) + 1);
    try {
      const result = name === "salesPeriod" ? await api.putSalesPeriod(rid, next, revision)
        : await api.putCollection(rid, name, next, revision);
      if (!confirmed(result) || result.revision < revision) throw new Error("Save was not confirmed. Refresh and review before retrying.");
      if (name !== "salesPeriod" && result[name] !== undefined && !Array.isArray(result[name])) throw new Error("Saved collection was not confirmed.");
      if (name === "salesPeriod" && result[name] !== undefined && (!result[name] || typeof result[name] !== "object" || Array.isArray(result[name]))) throw new Error("Saved sales period was not confirmed.");
      if (!isCurrent()) return null;
      scope.revision = result.revision;
      setSnapshot(previous => previous?.scope === scope ? { scope, data: {
        ...previous.data, [name]: result[name] ?? next, revision: result.revision,
      } } : previous);
      return result;
    } catch (error) {
      if (isCurrent()) errors.current(error?.response?.status === 409
        ? "This data changed elsewhere. Your draft is retained; review the latest data before retrying."
        : error?.response?.data?.detail || error.message || "Save failed. Your draft is retained.");
      return null;
    } finally {
      pending.current.delete(rid); writes.current.set(rid, (writes.current.get(rid) || 0) + 1);
      // Returning A -> B -> A creates a new scope. Reload that scope after an
      // older A request finishes; never copy its acknowledgement into the new UI.
      if (alive.current && active.current !== scope && active.current.rid === rid) refreshRef.current();
    }
  }, [rid, scope, isCurrent]);
  const apply = useCallback(update => {
    if (isCurrent()) setSnapshot(previous => previous?.scope === scope
      ? { scope, data: update(previous.data) } : previous);
  }, [scope, isCurrent]);
  return { state: snapshot?.scope === scope ? snapshot.data : null, save, refresh, apply, isCurrent };
}
