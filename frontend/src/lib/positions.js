// Positions from the JMAX org hierarchy (Jeff 2026-10-30): role code, label and the access class
// it signs in with. backend/positions.py is the source of truth for what each position may do.
export const POSITIONS = [
  { code: "OWN", label: "Owner", role: "owner", group: "Ownership" },
  { code: "OPS", label: "Operations & Integration Lead", role: "owner", group: "Ownership" },
  { code: "GM", label: "General Manager", role: "manager", group: "Managers" },
  { code: "KM", label: "Kitchen Manager", role: "manager", group: "Managers" },
  { code: "FOHM", label: "FOH Manager", role: "manager", group: "Managers" },
  { code: "BPM", label: "Bulk Prep Manager (both stores)", role: "manager", group: "Managers" },
  { code: "SL-BOH", label: "BOH Shift Leader", role: "manager", group: "Shift leaders" },
  { code: "SL-FOH", label: "FOH Shift Leader", role: "manager", group: "Shift leaders" },
  { code: "BPC", label: "Bulk Prep Cook (both stores)", role: "staff", group: "Team" },
  { code: "LC-GRL", label: "Grill Cook", role: "staff", group: "Team" },
  { code: "LC-PZA", label: "Pizza Cook", role: "staff", group: "Team" },
  { code: "LC-APZ", label: "Assistant Pizza Cook", role: "staff", group: "Team" },
  { code: "LC-EXP", label: "Expo", role: "staff", group: "Team" },
  { code: "LC-SLP", label: "Salad/Pasta Cook", role: "staff", group: "Team" },
  { code: "LC-FRY", label: "Fry Cook", role: "staff", group: "Team" },
  { code: "LC-PRP", label: "Prep Cook", role: "staff", group: "Team" },
  { code: "LC-SBA", label: "Salad Bar Attendant", role: "staff", group: "Team" },
  { code: "FOH-SRV", label: "Server", role: "staff", group: "Team" },
  { code: "FOH-HST", label: "Host", role: "staff", group: "Team" },
  { code: "FOH-RUN", label: "Runner", role: "staff", group: "Team" },
  { code: "FOH-BW", label: "Back Window / Take Out", role: "staff", group: "Team" },
  { code: "DSH", label: "Dishwasher", role: "staff", group: "Team" },
];
export const positionLabel = code => POSITIONS.find(p => p.code === code)?.label || code;
export const positionRole = code => POSITIONS.find(p => p.code === code)?.role;
export const POSITION_GROUPS = [...new Set(POSITIONS.map(p => p.group))];
// Analytics is for the General Manager and above (positions.py see_analytics, Jeff 2026-11-06); a login
// with no position keeps its access class, so only owners. The server checks it again.
export const canSeeAnalytics = user => {
  const own = POSITIONS.find(p => p.code === user?.position);
  return own && own.role === user?.role ? ["OWN", "OPS", "GM"].includes(own.code) : user?.role === "owner";
};
