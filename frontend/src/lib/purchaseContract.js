// Client input vocabulary; the server still validates units and location access.
export const PURCHASE_BASE_UNITS = Object.freeze(["lb", "oz", "g", "kg", "fl_oz", "ml", "l", "gal", "each"]);
export const canonicalStoreId = id => id === "papa_leonis" ? "papa" : id;
