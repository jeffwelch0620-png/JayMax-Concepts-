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
