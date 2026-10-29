// Selective Package 1 note reader; reading never accepts responsibility.
import { checkedHandoffDay, handoffContext } from "./managerHandoff";
import { readStateWithDeadline } from "./stateRead";
export async function loadManagerTakeover(rid, day, track, user, api) {
  const context = handoffContext(rid, day, track, user);
  if (!context) return { state: "unavailable", reason: "error", message: "Note scope not confirmed." };
  if (api.managerHandoffEnabled !== true) return { state: "unavailable", reason: "disabled", message: "Previous note unavailable: capability is disabled." };
  try {
    const value = checkedHandoffDay(await readStateWithDeadline(options => api.handoffDay(rid, day, track, options), "Note read timed out."), context);
    const yesterday = new Date(`${day}T00:00:00Z`); yesterday.setUTCDate(yesterday.getUTCDate() - 1);
    return { state: "ready", previous: value.previous, currentStatus: value.current?.status || null,
      older: !!value.previous && value.previous.business_date !== yesterday.toISOString().slice(0, 10), readAt: new Date().toISOString() };
  } catch {
    return { state: "unavailable", reason: "error", message: "Previous note not confirmed: read failed or source mismatched. Refresh." };
  }
}
