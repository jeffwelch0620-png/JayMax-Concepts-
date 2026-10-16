let pgItemToMongoItem, mongoItemToPgBody, catalogPrice;
const flags = ["REACT_APP_USE_PG", "REACT_APP_NATIVE_PURCHASES", "REACT_APP_ACTUAL_INVENTORY", "REACT_APP_CATALOG_MAPPING"];
const original = Object.fromEntries(flags.map(flag => [flag, process.env[flag]]));
function load(native = true) {
  jest.resetModules();
  process.env.REACT_APP_USE_PG = "true";
  for (const flag of flags.slice(1)) process.env[flag] = native ? "true" : "false";
  ({ pgItemToMongoItem, mongoItemToPgBody, catalogPrice } = require("./api"));
}
beforeEach(() => load());
afterAll(() => {
  for (const flag of flags) {
    if (original[flag] === undefined) delete process.env[flag];
    else process.env[flag] = original[flag];
  }
});

const item = { code: "papa_food", name: "Purchased food", baseUnit: "lb", countUnit: "case", basePerCountUnit: 20, active: true, countActive: false,
  packCount: 4, unitQty: 5, unitUOM: "lb", portionSize: 4, portionUOM: "oz", vendorSkus: [{ id: "sku", vendor: "special_supplier", vendorName: "Special supplier", vendorSku: "00001", purchaseUnit: "case", packCount: 4, unitQty: 5, unitUOM: "lb", basePerPurchaseUnit: 20 }] };

test.each([true, false])("unrelated item edits preserve all retained decimal digits (native %s)", native => {
  load(native);
  const exact = "1.123456789012345678";
  const source = { ...item, packCount: exact, unitQty: exact, portionSize: exact, basePerCountUnit: exact,
    par: "0.000000000000000001", vendorSkus: [{ ...item.vendorSkus[0], packCount: exact, unitQty: exact, basePerPurchaseUnit: exact }] };
  const saved = mongoItemToPgBody({ ...pgItemToMongoItem(source, "berts"), name: "Changed name only" }, "berts");
  for (const key of ["pack_count", "unit_qty", "portion_size", "base_per_count_unit"]) expect(saved[key]).toBe(exact);
  expect(saved.par).toBe(source.par);
  for (const key of ["pack_count", "unit_qty", "base_per_purchase_unit"]) expect(saved.vendor_skus[0][key]).toBe(exact);
});

test.each([true, false, "NaN", "Infinity", "bad", "-1"])("invalid catalog metadata %p is held rather than changed to zero/null", value => {
  expect(() => mongoItemToPgBody({ ...pgItemToMongoItem(item, "berts"), par: value }, "berts")).toThrow("catalog decimal");
});

test("catalog blank metadata remains null and an explicit zero remains text zero", () => {
  const ui = { ...pgItemToMongoItem(item, "berts"), packCount: "", unitQty: "0", portionSize: null, par: "0" };
  const saved = mongoItemToPgBody(ui, "berts");
  expect(saved.pack_count).toBeNull(); expect(saved.portion_size).toBeNull();
  expect(saved.unit_qty).toBe("0"); expect(saved.par).toBe("0");
});

test.each(["1E+400", "1E-400"])("retained finite decimal %s is not rejected or rounded through a planning Number", exact => {
  const saved = mongoItemToPgBody({ ...pgItemToMongoItem(item, "berts"), basePerCountUnit: exact, packCount: exact, par: exact }, "berts");
  expect(saved.base_per_count_unit).toBe(exact); expect(saved.pack_count).toBe(exact); expect(saved.par).toBe(exact);
});
test("catalog round trip retains canonical IDs, physical units and independent count activation", () => {
  const ui = pgItemToMongoItem(item, "papa_leonis"), saved = mongoItemToPgBody(ui, "papa_leonis");
  expect(saved.code).toBe("papa_food"); expect(saved.base_unit).toBe("lb"); expect(saved.base_per_count_unit).toBe("20");
  expect(saved.vendor_skus[0].vendor_id).toBe("special_supplier"); expect(saved.vendor_skus[0].base_per_purchase_unit).toBe("20");
  expect(ui.countActive).toBe(false);
});
test("editing recipe portions cannot rewrite physical case factors", () => {
  const ui = { ...pgItemToMongoItem(item, "berts"), portionSize: 8, portionUOM: "oz" };
  expect(mongoItemToPgBody(ui, "berts").base_per_count_unit).toBe("20");
  expect(mongoItemToPgBody(ui, "berts").vendor_skus[0].base_per_purchase_unit).toBe("20");
});
test("new catalog case metadata uses physical pack quantity rather than portion count", () => {
  const ui = { controlNumber: "NEW", unitUOM: "lb", packCount: 4, unitQty: 5, portionSize: 4, portionUOM: "oz", vendorSkus: [] };
  const saved = mongoItemToPgBody(ui, "berts"); expect(saved.base_unit).toBe("lb"); expect(saved.base_per_count_unit).toBe("20");
});
test.each([[4, 80], [8, 40]])("legacy adapter with native flags off retains portion factor for %s oz", (portionSize, expected) => {
  load(false);
  const saved = mongoItemToPgBody({ controlNumber: "LEGACY", unitUOM: "lb", packCount: 4, unitQty: 5, portionSize, portionUOM: "oz", vendorSkus: [] }, "berts");
  expect(saved.base_unit).toBe("oz");
  expect(saved.base_per_count_unit).toBe(String(expected));
});
test("unknown pack quantities and incompatible physical units cannot silently become one", () => {
  expect(() => mongoItemToPgBody({ controlNumber: "NEW", unitUOM: "lb", vendorSkus: [] }, "berts")).toThrow("Confirm a physical pack quantity");
  expect(() => mongoItemToPgBody({ controlNumber: "NEW", baseUnit: "each", unitUOM: "lb", packCount: 4, unitQty: 5, vendorSkus: [] }, "berts")).toThrow("compatible inventory unit");
});

test("supplier description, decimal price and provenance survive ordinary catalog round trips", () => {
  const sku = { ...item.vendorSkus[0], vendorDescription: "  Original food description — 4 / 5 LB  ", price: "12345678901234567890.000000000001", priceSource: "invoice", priceUpdatedAt: "2026-10-01T12:00:00Z" };
  const ui = pgItemToMongoItem({ ...item, lastCountedBy: "Invented counter", vendorSkus: [sku] }, "berts");
  const saved = mongoItemToPgBody(ui, "berts");
  expect(ui.vendorSkus[0].packDescription).toBe(sku.vendorDescription);
  expect(saved.vendor_skus[0].vendor_description).toBe(sku.vendorDescription);
  expect(saved.vendor_skus[0].price).toBe(sku.price);
  expect(ui.vendorSkus[0].priceSource).toBe("invoice"); expect(ui.lastCountedBy).toBe("Invented counter");
});
test.each([null, ""])("unknown supplier price %j stays unknown rather than zero", price => {
  const ui = pgItemToMongoItem({ ...item, vendorSkus: [{ ...item.vendorSkus[0], price, vendorDescription: null, priceSource: null }] }, "berts");
  const saved = mongoItemToPgBody(ui, "berts");
  expect(saved.vendor_skus[0].price).toBeNull(); expect(saved.vendor_skus[0].vendor_description).toBeNull();
  expect(ui.vendorSkus[0].priceSource).toBeNull();
});
test.each(["NaN", "Infinity", "bad", "-1"])("invalid catalog price %s is rejected before JSON can change it to null", value => {
  expect(() => catalogPrice(value)).toThrow("non-negative finite");
});
test.each([[true,false],[false,true],[false,false],[true,true]])("active %s and count participation %s remain independent", (active, countActive) => {
  const saved = mongoItemToPgBody(pgItemToMongoItem({ ...item, active, countActive }, "berts"), "berts");
  expect(saved.active).toBe(active); expect(saved.counted_nightly).toBe(countActive);
});
test("a location alias never replaces the canonical shared product code", () => {
  const ui=pgItemToMongoItem({...item,controlNumber:"R01",sharedStoreCount:2},"rudds");
  expect(ui.controlNumber).toBe("R01");expect(ui.itemCode).toBe("papa_food");expect(ui.sharedStoreCount).toBe(2);
  expect(mongoItemToPgBody(ui,"rudds").code).toBe("papa_food");
});
test.each([true,false])("supplier selection uses an available row and retains unavailable history (native %s)", native => {
  load(native);
  const retired = { ...item.vendorSkus[0], id: "retired", preferred: true, available: false, purchaseUnit: "old-case" };
  const current = { ...item.vendorSkus[0], id: "current", vendorSku: "NEW", preferred: false, available: true, purchaseUnit: "case" };
  const ui = pgItemToMongoItem({ ...item, vendorSkus: [retired,current] }, "berts");
  expect(ui.purchaseUnit).toBe("case"); expect(ui.vendorSkus).toHaveLength(2);
  expect(mongoItemToPgBody(ui,"berts").vendor_skus[0].available).toBe(false);
});
test.each([null, 4])("an explicitly unknown supplier conversion stays unknown with pack count %j", packCount => {
  const source = { ...item, vendorSkus: [{ ...item.vendorSkus[0], basePerPurchaseUnit: null,
    packCount, unitQty: packCount == null ? null : 5 }] };
  const saved = mongoItemToPgBody(pgItemToMongoItem(source, "berts"), "berts");
  expect(saved.vendor_skus[0].base_per_purchase_unit).toBeNull();
  expect(saved.vendor_skus[0].pack_count).toBe(packCount == null ? null : String(packCount));
});
test("a new supplier without a conversion still requires verified physical pack metadata", () => {
  const ui = pgItemToMongoItem(item, "berts");
  ui.vendorSkus = [{ vendor: "PFG", vendorSku: "NEW", packCount: "", unitQty: "", unitUOM: "lb" }];
  expect(() => mongoItemToPgBody(ui, "berts")).toThrow("Confirm a physical pack quantity");
  ui.vendorSkus[0] = { ...ui.vendorSkus[0], packCount: 4, unitQty: 5 };
  expect(mongoItemToPgBody(ui, "berts").vendor_skus[0].base_per_purchase_unit).toBe("20");
});

test.each([true, false])("changing available supplier pack retains stored count conversion (native %s)", native => {
  load(native);
  const ui = pgItemToMongoItem({ ...item, basePerCountUnit: 80, countUnit: "count-case", vendorSkus: [
    { ...item.vendorSkus[0], preferred: true, available: false, basePerPurchaseUnit: 80 },
    { ...item.vendorSkus[0], id: "new", vendorSku: "NEW", preferred: false, available: true, packCount: 8, basePerPurchaseUnit: 40 }
  ] }, "berts");
  const saved = mongoItemToPgBody({ ...ui, portionSize: 8 }, "berts");
  expect(saved.base_per_count_unit).toBe("80"); expect(saved.count_unit).toBe("count-case"); expect(saved.base_unit).toBe("lb");
  expect(saved.vendor_skus.map(sku => sku.base_per_purchase_unit)).toEqual(["80", "40"]);
});
