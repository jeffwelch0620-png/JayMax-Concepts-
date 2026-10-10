import { itemDerived, preferredSku } from "./calc";

test("unavailable historical price cannot drive current planning selection", () => {
  const old = { id: "old", available: false, preferred: true, price: "999", packCount: 4, unitQty: 5, unitUOM: "lb" };
  const available = { ...old, id: "available", available: true, preferred: false, price: "80" };
  const item = { portionSize: 4, portionUOM: "oz", vendorSkus: [old,available] };
  expect(preferredSku(item)).toBe(available); expect(itemDerived(item).costPerPortion).toBe(1);
  expect(item.vendorSkus).toEqual([old,available]);
  expect(preferredSku({vendorSkus:[old]})).toBeNull();
});
test("available preferred supplier wins and legacy missing availability remains usable", () => {
  const first={price:"20"},preferred={price:"30",available:true,preferred:true};
  expect(preferredSku({vendorSkus:[first,preferred]})).toBe(preferred);
  expect(preferredSku({vendorSkus:[first]})).toBe(first);
});
