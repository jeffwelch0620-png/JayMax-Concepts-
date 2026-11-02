// Store identity colours (JMAX UI Library spec, phase 1). A store's own mark (its header tile, its
// chip in the store switcher, its dot on the owner dashboard) uses its store token, so owner pages can
// show every store at once. Actions and selected states use --jm-accent, which follows the selected
// store. Both are set in theme/tokens.css; phase 4 changes the values there.
const TOKEN = { berts: "berts", rudds: "rudds", papa_leonis: "papa", papa: "papa", owner: "owner" };

export const storeMark = id => `var(--jm-store-${TOKEN[id] || "owner"})`;
