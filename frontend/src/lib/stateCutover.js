// Server capabilities keep installed inventory retired even with client flags off.
export const nativeStateMode = (state, requested = false) => requested || state?.legacyStateCapabilities?.inventoryRetired === true;
export const retainedAdjustments = state => state?.legacyStateCapabilities?.adjustmentsAvailable === false;
