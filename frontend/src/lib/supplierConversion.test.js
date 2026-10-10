import { supplierPackFactor, supplierConversionMismatch } from "./supplierConversion";
test("comparison converts only compatible physical dimensions and ignores floating representation noise", () => {
  const row = { packCount: 4, unitQty: 5, unitUOM: "lb", basePerPurchaseUnit: 320 };
  expect(supplierPackFactor(row, "oz")).toBeCloseTo(320);
  expect(supplierConversionMismatch(row, "oz")).toBe(false);
  expect(supplierConversionMismatch({...row, basePerPurchaseUnit: 319}, "oz")).toBe(true);
  expect(supplierPackFactor({...row, unitUOM:"gal"}, "lb")).toBeNull();
  expect(supplierConversionMismatch({...row, basePerPurchaseUnit:null}, "oz")).toBe(false);
});
test.each([null, "", 0, -1, "bad", Infinity])("incomplete or invalid pack %s does not imply a conversion", count => {
  expect(supplierPackFactor({packCount:count,unitQty:5,unitUOM:"lb"}, "lb")).toBeNull();
});
