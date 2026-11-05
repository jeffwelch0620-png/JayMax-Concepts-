// Native prep tracks. Salad Bar runs only at Bert's; backend/prep_tracks.py and
// migrations/20261029_salad_prep_track.sql enforce the same rule.
const ALL = [
  { id: "daily", label: "Daily Prep" },
  { id: "bulk", label: "Bulk Prep" },
  { id: "salad", label: "Salad Bar Prep" },
];
export const prepTracks = rid => ALL.filter(t => t.id !== "salad" || rid === "berts");
export const validPrepTrack = (rid, track) => prepTracks(rid).some(t => t.id === track);
export const prepTrackLabel = track => ALL.find(t => t.id === track)?.label || track;
// Bulk runs on Monday (weekday pars, covering Monday to Wednesday) and Thursday (weekend pars,
// Thursday to Sunday); null on other days. backend/prep_day_tasks.py bulk_day_group and
// migrations/20261104_bulk_run_days.sql enforce the same.
export const bulkDayGroup = iso => ({ 1: "weekday", 4: "weekend" })[new Date(`${iso}T12:00:00Z`).getUTCDay()] || null;
export const bulkDayGroupLabel = iso => ({ weekday: "Monday run: weekday pars", weekend: "Thursday run: weekend pars" })[bulkDayGroup(iso)] || "Bulk runs are on Monday or Thursday";
