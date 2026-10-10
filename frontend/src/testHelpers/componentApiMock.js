// Component suites opt into native panels and configure writes explicitly.
// Cover all exports so adding a panel cannot accidentally call the real API.
const readDefaults = {
  listVendorContacts: () => [],
  sharedCatalog: () => ({ products: [], revision: 1 }),
  nativeOperatingSummary: () => ({ basis: "native_received_purchases_and_explicit_counts", items: [], liveOnHandAvailable: false, countStatus: "scope_missing" }),
  supplierContacts: () => ({ contacts: [], legacy_contacts: [] }),
  nativeUnitSetup: () => ({ items: [], profiles: [], baseUnits: [] }),
};
export function resetComponentApiMock(mock) {
  for (const [name, value] of Object.entries(mock)) {
    if (typeof value === "boolean") mock[name] = false;
    if (jest.isMockFunction(value)) {
      value.mockReset();
      if (readDefaults[name]) value.mockImplementation(async () => readDefaults[name]());
      else value.mockImplementation(() => { throw new Error(`Configure API mock explicitly: ${name}`); });
    }
  }
}
export function createComponentApiMock() {
  const actual = jest.requireActual("../lib/api");
  const mock = Object.fromEntries(Object.entries(actual).map(([name, value]) => [name, typeof value === "function" ? jest.fn() : value]));
  resetComponentApiMock(mock);
  return { ...mock, __esModule: true };
}
